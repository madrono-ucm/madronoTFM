# 083 — Investigación: Google Maps a coste 0, y salud de la infraestructura desplegada

## Qué se investigó y por qué

Esta tarea nace de un objetivo inicial distinto: retirar la dependencia de
Google Maps Platform del proyecto para garantizar coste 0. Al intentar
ejecutarlo se descubrieron dos hechos que cambiaron el alcance por completo,
y esta tarea documenta la investigación y la decisión resultante en vez de
limitarse a borrar la integración.

## Hallazgo 1 — Google Maps no puede dar datos reales a coste 0 (verificado a nivel de código, no supuesto)

La hipótesis inicial era que se podía evitar la llamada oficial de pago
("Find Place from Text") fijando a mano un puñado de `place_id` de Google ya
conocidos (consultables gratis vía el propio sitio de Google Maps, sin API
key), y dejar que el resto del pipeline (la librería de terceros
`populartimes`, ya usada por `ingesta/capturas/afluencia_lugares_madrid.py`,
tarea 012) funcionase como scraping puro sin coste.

Se verificó leyendo el código fuente real de `m-wrzr/populartimes`
(`crawler.py`) contra el uso real en este repositorio:

- `resolve_place_id()` (`afluencia_lugares_madrid.py`) llama a
  `GET https://maps.googleapis.com/maps/api/place/findplacefromtext/json`
  — esta es la llamada que la hipótesis quería evitar. **No es la que falla
  con clave inválida**: cualquier estado distinto de `"OK"` (incluido
  `REQUEST_DENIED`) se trata como "sin candidato" y solo genera un
  `WARNING`, sin excepción (confirmado en doc/012).
- `populartimes.get_id(api_key, place_id)` es un pipeline fijo de dos pasos,
  no separables desde la API pública de la librería:
  1. `get_populartimes(api_key, place_id)` llama primero a
     `GET .../details/json?placeid=...&key=...` — la API oficial y **de
     pago** "Place Details". Aquí es donde `check_response_code()` lanza
     literalmente la excepción vista en la tarea 012:
     `PopulartimesException('Google Places REQUEST_DENIED', 'Request was
     denied, the API key is invalid.')`.
  2. Solo si ese paso tiene éxito, se llama a
     `get_populartimes_by_detail(api_key, detail)` →
     `get_populartimes_from_search(detail["name"], address)`, que sí es
     scraping puro (`google.de/search?...`, sin `api_key` en la URL) — pero
     es inalcanzable a través de `get_id()` sin pasar antes por el paso 1.

**Conclusión verificada, no supuesta**: fijar `place_id` a mano solo evita
la llamada que ya se ignoraba en caso de fallo (Find Place). La llamada que
realmente bloquea (Place Details) es obligatoria y de pago **siempre**, sin
excepción, dentro de `populartimes.get_id()`. Rodearla exigiría
reimplementar el scraping a mano fuera de la librería — exactamente lo que
la tarea 012 decidió no hacer ("no se reimplementa el scraping"), y lo que
esta tarea tampoco hace, por el mismo criterio.

Adicionalmente (conocimiento general, no verificable con las herramientas
de esta sesión): Google Cloud exige una cuenta de facturación activa
(tarjeta de crédito) para emitir una clave de Google Maps Platform utilizable,
incluso dentro del nivel gratuito mensual — no existe un nivel sin tarjeta.
La nota de `doc/012` sobre "sin necesidad de tarjeta" debería revisarse
como parte de la tarea 084/085.

## Hallazgo 2 — El estado de Terraform ha derivado de `main`, más urgente que Google Maps

Al preparar `terraform plan` para retirar `afluencia_lugares`, el plan
**sin acotar** (contra la configuración sin modificar) devolvió:

```
Plan: 53 to add, 61 to change, 65 to destroy.
```

Desglose verificado línea a línea (con los códigos ANSI del output
limpiados para poder grepear con fiabilidad):

- **48 reemplazos** de `aws_s3_object.glue_script_*` (más
  `procesamiento_source`/`ingesta_source`) — el código Python empaquetado y
  subido a S3 para los jobs de Glue/Lambda está desactualizado respecto al
  `main` actual. Esto implica que **no se puede asumir que las correcciones
  ya fusionadas (p. ej. la serie 072-077 de duplicados, o el fix pendiente
  de `--extra-py-files`) estén realmente desplegadas** — el código fusionado
  y el código en ejecución pueden haber divergido silenciosamente.
- **5 creaciones** de infraestructura de Kafka (`aws_security_group.kafka`
  y relacionados, tarea 042) — esperado: esa infraestructura se dejó
  escrita en código deliberadamente sin aplicar (documentado en el propio
  `kafka.tf`), no es un hallazgo nuevo, solo confirma que nadie ha corrido
  `terraform apply` de principio a fin recientemente.
- Un error real de permisos, no relacionado con el drift: el rol
  `madrono-terraform-deployer` no tiene `codebuild:BatchGetProjects`,
  así que el `plan` sin acotar nunca llega a completarse limpio (aborta al
  intentar leer `aws_codebuild_project.lambda_dependencies_layer`).
- **Cero acciones sobre `aws_s3_bucket*`** en todo el plan — los buckets de
  Bronze/Silver/Gold y sus datos no están en riesgo por este drift.

### Hallazgo 2b — footgun real de `-target` en modo destroy

Al intentar acotar el `apply` solo a los 17 recursos de
`afluencia_lugares`/Google Maps:

- `terraform plan -target=<17 recursos>` (modo normal) sí acotó bien los
  **17 destroys reales**, pero arrastró como efecto colateral el
  redespliegue del código actual a los otros 13 productores (por compartir
  el mismo archivo empaquetado `procesamiento_source`/`ingesta_source`) —
  no destructivo, pero sí un cambio no solicitado sobre infraestructura en
  producción.
- `terraform plan -destroy -target=<mismos 17 recursos>` (probado para
  buscar un aislamiento más limpio) **planeó destruir los 14 Lambda
  productores y sus 20 schedules de EventBridge Scheduler completos**,
  arrastrados por las políticas IAM compartidas (`ingestion_lambda_logs`,
  `scheduler_invoke_lambda`). Verificado solo con `plan`, nunca aplicado.

Ninguno de los dos intentos se aplicó. Se revirtieron los tres ficheros
`.tf` editados (`git checkout --`) antes de terminar esta tarea — el estado
real en AWS no ha cambiado en ningún momento de esta sesión.

## Decisión

1. **No se borra la capacidad de "afluencia"** — se sustituye por una señal
   compuesta vía el grafo (Neo4j `PROXIMO_A`, mismo patrón que
   `trafico_cercano`, tarea 081) construida sobre datos ya ingeridos a coste
   0 (`aforos_peatones_bicicletas` como proxy principal —
   contadores oficiales reales, más preciso que la estimación de Google—,
   `bicimad`/`trafico`/`aparcamientos` como señales secundarias,
   `agenda_eventos` como indicador anticipado). Ver la tarea 086 (spec, sin
   implementar todavía).
2. **La retirada del despliegue en vivo de `afluencia_lugares`/Google Maps
   queda pendiente**, empaquetada junto con la reconciliación general del
   drift de Terraform (hallazgo 2) en vez de aplicarse de forma aislada
   esta noche — ver `NEXT_STEPS.md` (tarea 085).
3. El código de `ingesta/capturas/afluencia_lugares_madrid.py` y el fixture
   mock se mantienen en el repositorio sin cambios: siguen teniendo valor
   documentado para la discusión de "zona gris académica" de la memoria
   (§6.8, ya citada en doc/012).

## Relevante para tareas futuras

- **084** (`PLATFORM_SCHEMA.md`) debe documentar el alcance real de los
  permisos IAM del deployer (`*FullAccess` en 10 servicios) y el hallazgo
  del drift de Terraform como riesgos activos, no solo inventariar servicios.
- **085** (`NEXT_STEPS.md`) debe priorizar la reconciliación de Terraform
  (hallazgo 2) y el permiso `codebuild:BatchGetProjects` por encima de
  trabajo cosmético, y enlazar el footgun de `-target`/`-destroy` (hallazgo
  2b) como advertencia para cualquiera que toque `infra/terraform/` a mano.
- **086** debe especificar la señal de afluencia basada en grafo con
  suficiente detalle para implementarse en una sesión de seguimiento sin
  tener que releer esta investigación.
- Antes de aplicar cualquier cambio de Terraform en este proyecto, correr
  primero un `terraform plan` **sin acotar** y revisar el resumen completo
  — el drift descrito aquí seguirá ahí hasta que alguien lo reconcilie
  explícitamente.
