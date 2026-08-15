# 040 — Arreglar el timeout de la Lambda de aforos de peatones y bicicletas

## Diagnóstico

La tarea 033 había dejado documentado que `madrono-tfm-dev-aforos_peatones_bicicletas`
se colgaba siempre a los 120.00s exactos (`Sandbox.Timedout`, el `timeout` configurado
entonces en `infra/terraform/lambda.tf`), con el log mostrando solo el `WARNING` inicial
de `check_for_newer_resources` y nada más — ni un solo reintento, ni ningún error de red.

Revisando `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`, la llamada a
`requests.get(url, timeout=config.timeout_seconds)` **sí tenía** un timeout explícito
(mismo patrón que el resto de productores del proyecto) — la hipótesis del enunciado
("llamada a `requests` sin `timeout=`") no se confirmó tal cual. El problema real es más
sutil: un único valor `float` pasado como `timeout=` en `requests` se aplica **por
operación de lectura del socket** (el hueco de inactividad entre dos trozos recibidos),
no como límite del tiempo **total** de la petición. Si el servidor va entregando datos de
forma continua pero lenta — sin que nunca haya un hueco de inactividad mayor que ese
timeout — la descarga completa puede tardar arbitrariamente más que el timeout
configurado sin que `requests` levante ninguna excepción en ningún momento.

Este dataset descarga dos CSV completos por invocación (~17 MB peatones, ~34 MB
bicicletas, ver docstring del módulo). En esta EC2 de desarrollo la descarga tarda unos
segundos (red rápida); en el entorno de red real de Lambda (tarea 033, con
`--cli-read-timeout 120`/`300` y ambas invocaciones agotando el timeout de la propia
Lambda sin ningún error) es coherente que la misma descarga, con throughput más bajo,
tardara sistemáticamente más de 120s sin que ningún trozo individual llegara a tardar
más de 30s (el `HTTP_TIMEOUT_SECONDS` por defecto) — exactamente el escenario "sin
ningún log de fallo hasta que Lambda mata el proceso en seco" que describía la tarea 033.

## Arreglo de código: límite de tiempo total, no solo por lectura

Se añadió `_download` (`ingesta/capturas/aforos_peatones_bicicletas_madrid.py`), que
sustituye la descarga directa (`requests.get(...).content`) por una descarga en
streaming (`stream=True`, `iter_content`) con un límite de tiempo total de pared,
independiente del timeout por lectura ya existente:

- Nuevo campo `CaptureConfig.download_timeout_seconds`, leído de la variable de entorno
  `MADRID_COUNTERS_DOWNLOAD_TIMEOUT_SECONDS` (por defecto **100.0s**).
- `_download` calcula `deadline = time.monotonic() + download_timeout_seconds` antes de
  empezar, y en cada trozo recibido comprueba si ya se ha superado ese plazo; si es así,
  levanta `requests.exceptions.Timeout` explícitamente con un mensaje descriptivo
  (incluye la URL y los bytes ya descargados).
- Al ser una excepción de la jerarquía `requests.RequestException`, ese error entra sin
  ningún cambio adicional en el mismo bucle de reintentos con backoff que ya tenía este
  módulo (`_fetch_with_retries`, sin modificar su lógica) — mismo patrón que el resto de
  productores del proyecto, tal como pedía el enunciado.
- `requests.get(url, timeout=config.timeout_seconds, ...)` se mantiene sin cambios (sigue
  cubriendo el caso de un hueco de inactividad real, p.ej. el servidor deja de responder
  del todo), solo se le añade `stream=True`.

Este cambio convierte un colgado silencioso e indetectable (Lambda mata el proceso sin
que el código llegue a registrar nada) en un error explícito, logueado y con reintento —
incluso en el caso patológico en que la descarga sea realmente demasiado lenta de forma
sostenida, ahora se puede diagnosticar por los logs en vez de depender solo del código de
salida `Sandbox.Timedout`.

## `infra/terraform/lambda.tf`: `timeout`/`memory_mb` ampliados

El arreglo de código por sí solo convierte el colgado silencioso en un fallo explícito,
pero no garantiza que la descarga + parseo + normalización de ambos CSV completos quepa
siempre en 120s en el entorno de red real de Lambda — que es más lento que esta EC2 (aquí
la captura completa tarda ~10-15s; en Lambda, según la tarea 033, ya agotaba 120s sin
completar). Se subió `local.producers.aforos_peatones_bicicletas` en
`infra/terraform/lambda.tf`:

| Parámetro | Antes | Después | Motivo |
|---|---|---|---|
| `timeout` | 120s | **300s** | Mismo valor que `afluencia_lugares`, la otra función de este proyecto con timeout ya ampliado; da margen de sobra para las descargas + parseo + un reintento, sin ser un valor arbitrariamente alto. |
| `memory_mb` | 256 | **512** | Lambda asigna CPU y ancho de banda de red de forma proporcional a la memoria configurada; doblar la memoria da más capacidad de proceso/red para descargar y parsear los ~51 MB combinados de ambos CSV. |

No se ha tocado la cadencia (`aws_scheduler_schedule.producer["aforos_peatones_bicicletas"]`,
mensual, día 1 a las 06:00 Madrid) ni ningún otro atributo de la función.

## Tests añadidos

`ingesta/tests/test_aforos_peatones_bicicletas_madrid.py` gana dos clases nuevas, ambas
sin red real (sustituyen `requests.get`/`time.monotonic`):

- `DownloadTests`: prueba `_download` directamente — una descarga cuyos trozos llegan
  dentro del plazo total devuelve el contenido concatenado; una descarga cuyos trozos,
  sumados, superan el plazo total configurado levanta `requests.exceptions.Timeout`
  (reproduce en miniatura el escenario diagnosticado: cada trozo individual "llega a
  tiempo", pero el total no).
- `FetchWithRetriesTests`: prueba que un fallo de `_download` (mockeado directamente)
  entra en el bucle de reintentos existente — reintenta y devuelve el contenido si un
  intento posterior tiene éxito, y levanta `RuntimeError` si se agotan los reintentos.

Los tests existentes no necesitaron cambios (ninguno tocaba `_fetch_with_retries`/
`_download`, y la firma de `CaptureConfig` solo gana un campo nuevo con valor por
defecto en `from_env`, no rompe ningún test existente). Suite completa
(`python3 -m unittest discover -s ingesta/tests -t .` desde la raíz del repo):
**258 tests, todos en verde** (254 previos + 4 nuevos), sin regresiones.

## Reempaquetado y despliegue en AWS

Con `allow_infra_apply: true` para esta tarea, se aplicó el cambio contra la cuenta AWS
real (`222234418587`, región `eu-west-1`), mismo mecanismo que las tareas 031/033/039:

1. `backend.hcl`/`terraform.tfvars` regenerados a partir de sus `.example`
   (gitignored), añadiendo el ARN de la Lambda Layer ya publicada
   (`arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1`,
   sin cambios respecto a tareas anteriores).
2. `terraform init -backend-config=backend.hcl`.
3. `terraform plan -var-file=terraform.tfvars -out=tfplan`: **`Plan: 0 to add, 15 to
   change, 0 to destroy`** — las 14 `aws_lambda_function.producer[*]` in-place (nuevo
   `source_code_hash` del `.zip` reempaquetado, único cambio en 13 de las 14; en
   `aforos_peatones_bicicletas` además `timeout: 120 -> 300` y `memory_size: 256 -> 512`),
   más el mismo efecto colateral ya documentado en tareas anteriores sobre
   `aws_iam_policy.scheduler_invoke_lambda` (contenido idéntico, solo recalculado por
   depender de los ARNs de las funciones).
4. `terraform apply tfplan`: aplicado sin error. Un `terraform plan` posterior confirmó
   `No changes. Your infrastructure matches the configuration.` — sin drift residual.
5. Verificado con `aws lambda get-function-configuration`:
   `Timeout: 300`, `MemorySize: 512`, `CodeSha256: 5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=`
   en `madrono-tfm-dev-aforos_peatones_bicicletas`.

No se ha modificado ningún otro recurso ni creado/destruido nada — el único cambio de
infraestructura fuera del contenido del `.zip` (idéntico para las 14 funciones) es
`timeout`/`memory_mb` de esta única función.

### Recursos AWS afectados (referencia auditable)

- **Cuenta**: `222234418587`. **Región**: `eu-west-1`.
- **Modificadas in-place** (código nuevo, mismo ARN/nombre): las 14 funciones
  `aws_lambda_function.producer[*]` (`madrono-tfm-dev-<clave>`).
- **Modificada además en `timeout`/`memory_mb`**: `madrono-tfm-dev-aforos_peatones_bicicletas`
  (120s/256MB → 300s/512MB).
- **Recalculada sin cambio de contenido**: política IAM
  `madrono-tfm-dev-scheduler-invoke-lambda`.
- No se ha creado ni destruido ningún recurso.

## Verificación: invocación manual real

```
aws lambda invoke --function-name madrono-tfm-dev-aforos_peatones_bicicletas \
  --payload '{}' --cli-read-timeout 320 --region eu-west-1 /tmp/aforos_invoke_result.json
```

Resultado: `StatusCode: 200`, completada en **~15.4s** (frente al `Sandbox.Timedout` a los
120.00s de la tarea 033) — muy por debajo del nuevo `timeout` de 300s, sin necesitar
ningún reintento:

```json
{"dataset": "aforos_peatones_bicicletas", "records_written": 1971,
 "location": "s3://madrono-tfm-dev-bronze-222234418587/aforos_peatones_bicicletas/fecha=2026-08-15/hora=19/20260815T194706_fe93f48c.json"}
```

Se leyó el objeto escrito en Bronze y se confirmó que las 1971 filas (30 estaciones de
peatones + 53 de bicicletas x 24h del último día disponible, 2024-06-30) están bien
formadas, con `measured_at`/`ingested_at` en hora de Madrid (`+02:00`, herencia de las
tareas 037/039) y solo uno de `pedestrian_count`/`bicycle_count` relleno por registro,
tal como documenta el propio módulo.

## Restricciones respetadas

- No se ejecutó `terraform destroy` en ningún momento.
- No se cambió la cadencia (mensual, día 1 a las 06:00 Madrid) de esta función.
- El `apply` se limitó exactamente a lo que describía el prompt de esta tarea:
  reempaquetar el código ya corregido y subir `timeout`/`memory_mb` de la única función
  afectada. No se creó ni se destruyó ningún recurso.
- No se dejó nada programado nuevo (cron, systemd timer, bucle) en esta EC2: la
  invocación real fue puntual (`aws lambda invoke` x1), y el `aws_scheduler_schedule` ya
  existente no se ha tocado.
- `terraform.tfvars`, `backend.hcl`, `.terraform/`, `.terraform.lock.hcl` y el
  `__pycache__` generado por las ejecuciones locales del módulo se eliminaron del disco
  al terminar la tarea (nada de esto se commitea).

## Relevante para tareas futuras

- El timeout de esta Lambda quedó resuelto tanto en causa (código: límite de tiempo total
  de descarga, no solo por lectura) como en margen de seguridad (Lambda: `timeout`/
  `memory_mb` ampliados) — no debería volver a colgarse en silencio del mismo modo,
  aunque una descarga excepcionalmente lenta seguiría fallando explícitamente tras
  `download_timeout_seconds` (100s por defecto) x `max_retries` (3) si el problema fuera
  sostenido, en vez de colgarse sin ningún log.
- El patrón `_download` con límite de tiempo total (streaming + `time.monotonic()` +
  deadline) es específico de este módulo por ahora: es el único productor del proyecto
  que descarga ficheros de decenas de MB en una sola petición. Si una tarea futura añade
  otro productor con descargas igual de grandes, este mismo patrón (en vez de un único
  `timeout=` float) sería el punto de partida a reutilizar.
- Cadencia mensual (día 1, 06:00 Madrid): la próxima ejecución programada real será el
  1 de septiembre de 2026 — no se ha forzado ninguna ejecución adicional del `schedule`,
  solo la invocación manual de verificación de esta tarea.
