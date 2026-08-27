# 100 — Normalizar EOL con `.gitattributes`: el drift que quedó tras la 098 es CRLF/LF, no un apply incompleto

## Contexto

Esta misma sesión de QA (ver la nota añadida al final de
`doc/098-reconciliar-drift-terraform-y-aforos-gold.md`) detectó que, pese a
que la tarea 098 documentó un `terraform plan` final en
`5 to add, 0 to change, 0 to destroy`, repetirlo hoy desde esta EC2 (mismo
rol IAM, `madrono-terraform-deployerEC2`) volvía a dar `55 to add, 64 to
change, 50 to destroy` — casi idéntico al plan "roto" que la 098 dice haber
corregido. Verificado byte a byte que la causa es puramente de finales de
línea: el objeto real desplegado en S3 para, p. ej.,
`glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py`,
tras quitarle los `\r` (`tr -d '\r'`), es **idéntico byte a byte** al fichero
real en `main`. El contenido lógico ya está correctamente desplegado (el fix
de la tarea 090 sí está en producción); solo cambia el EOL, y como la clave
S3 incluye un hash MD5 del contenido (`file()`/`filemd5()` de Terraform),
un EOL distinto entre el checkout que hizo `apply` (CRLF) y cualquier
checkout que luego planifica (LF, como esta EC2) produce un "replace" falso
en cascada.

## Causa raíz

El repositorio no tenía `.gitattributes`. Sin él, cada checkout normaliza
los finales de línea según su propia configuración local de
`core.autocrlf` (o ninguna, como en esta EC2, donde nunca se detectó CRLF
en ningún fichero trackeado). Quien ejecutó el `apply` real de la tarea 098
lo hizo desde un entorno que normalizó a CRLF; cualquier `plan`/`apply`
posterior desde un checkout LF calculará hashes distintos para el mismo
fichero, viendo drift perpetuo y falso indefinidamente entre entornos.

## Qué se hizo

1. **`.gitattributes`** en la raíz: `* text=auto eol=lf` (criterio amplio,
   detección automática de texto vs. binario por Git, forzando LF en lo
   detectado como texto) más `*.docx binary` / `*.nc binary` explícitos
   para los dos binarios conocidos del repositorio
   (`documents/Memoria_TFM FV.docx`,
   `ingesta/tests/fixtures/cams_forecast_sample.nc`) como salvaguarda
   adicional, aunque `text=auto` ya los habría detectado correctamente.
   Se prefirió el criterio amplio a listar extensión por extensión (`*.py`,
   `*.tf`...) porque es más robusto ante ficheros de texto con extensiones
   no previstas y no requiere mantenimiento al añadir nuevos tipos.
2. **`git add --renormalize .`**: confirmado que **no cambia ningún
   fichero** en este checkout (`git status --short` tras el renormalize
   solo mostraba el propio `.gitattributes` como nuevo) — este checkout ya
   estaba en LF de partida (`git grep -Il $'\r' -- .` → 0 resultados antes
   de tocar nada), así que el commit de esta tarea es puramente preventivo
   para futuros checkouts/entornos (p. ej. Windows), no una corrección de
   contenido existente en `main`.

## Verificación del `terraform plan` (paso 3 del ticket) — resultado real, no el esperado

Con `.gitattributes` ya en el árbol de trabajo, se repitió `terraform plan`
sin acotar desde este mismo checkout (backend/tfvars reconstruidos
localmente a partir de los `.example` — ninguno de los dos se commitea,
`infra/terraform/.gitignore`):

```
Plan: 55 to add, 64 to change, 50 to destroy.
```

**El plan no cambia** respecto a antes de añadir `.gitattributes`, y es el
resultado correcto y esperado, no un fallo de esta tarea:
`.gitattributes` solo normaliza cómo Git escribe los ficheros en *futuros*
checkouts (`checkout`/`clone`/`add --renormalize`) — no reescribe con
retroactividad los objetos ya subidos a S3 por un `apply` anterior desde un
entorno CRLF. Verificado explícitamente descargando de nuevo el objeto real
(`aws s3api get-object`) y comparándolo: sigue siendo CRLF, y su versión sin
`\r` sigue siendo idéntica byte a byte al fichero real en `main` — mismo
diagnóstico que la auditoría previa, confirmado una segunda vez.

Esto es exactamente el escenario que el propio ticket anticipaba en su paso
4 ("si tras el paso 3 sigue habiendo objetos S3 desplegados con CRLF...").

## Por qué esta tarea NO ejecuta el `apply` de reconciliación

`tasks/README.md` (sección `allow_infra_apply`) es explícito: cuando una
tarea de infraestructura necesita un `terraform apply` real, el punto de
control humano solo se mantiene si se parte el trabajo en **tareas
secuenciales separadas** — una que deje ver el plan sin aplicar nada, y
**otra posterior, creada aparte tras revisar ese plan**, la que ya aplique.
Esta tarea (100) tiene `allow_infra_apply` implícitamente en modo
diagnóstico/preparación (así lo pide explícitamente su propio enunciado:
"no lo hagas dentro de esta misma tarea sin aprobación explícita"), así que
se detiene aquí, con el plan ya generado y verificado, documentado para que
una tarea posterior (con `allow_infra_apply: true` y revisión humana previa
del plan) ejecute el `apply` que reemplaza los ~50 objetos S3 con CRLF por
su versión LF.

El propio plan (`terraform plan`, guardado solo efímeramente en
`/tmp/plan100.tfplan` durante la verificación de esta sesión, no
commiteado — igual que `doc/093`) es de bajo riesgo, tal como ya analizó
`doc/098` para el mismo conjunto de recursos: los "50 to destroy" son la
mitad-destrucción de 50 pares de reemplazo de objetos S3 con distinto EOL
pero **contenido lógico idéntico** (verificado aquí de nuevo byte a byte),
no una pérdida de datos ni de infraestructura en uso. Las 5 adiciones
siguen siendo únicamente Kafka (tarea 042, deliberadamente sin aplicar).

## Restricciones respetadas

- Ningún `terraform apply`/`destroy` real ejecutado en esta tarea — solo
  `terraform init`/`plan` (de solo lectura contra el backend S3/DynamoDB
  real, sin modificar ningún recurso).
- No se ha tocado la lógica de ningún script de `procesamiento/`/
  `ingesta/` — el contenido ya era correcto; esta tarea es puramente sobre
  finales de línea y metadatos de Git.
- No se ha reescrito `doc/098-...md`; se le añadió una nota "Actualización
  27/8" (hecha en el commit de auditoría previo a esta tarea) señalando que
  el drift observado era CRLF/LF, no un `apply` incompleto.
- `backend.hcl`/`terraform.tfvars` reconstruidos localmente solo para la
  verificación (ambos gitignored, ninguno se commitea).

## Relevante para tareas futuras

- **Sigue pendiente un `terraform apply` real** para que los ~50 objetos
  S3 (scripts Glue + paquetes Lambda/capas) queden en LF y el `plan` vuelva
  a `5 to add, 0 to change, 0 to destroy` (solo Kafka). Debe ser una tarea
  aparte, con `allow_infra_apply: true` y aprobación humana explícita tras
  revisar el plan — no reutilizar el plan efímero de esta sesión, generar
  uno nuevo en el momento del `apply`.
- A partir de este commit, cualquier checkout nuevo (incluidas máquinas
  Windows) normalizará automáticamente a LF gracias a `.gitattributes` —
  el escenario que causó este drift no debería poder repetirse para
  ficheros ya trackeados en el momento del checkout. Si algún fichero
  binario nuevo se añade al repositorio en el futuro y no es texto,
  márquelo explícitamente como `binary` en `.gitattributes` (o confirme
  que `text=auto` ya lo detecta correctamente) antes de commitearlo.
- Un `terraform plan` con cifras que no cambian tras un fix de código no
  implica necesariamente que el fix esté mal — puede ser, como aquí, un fix
  que solo previene el problema hacia adelante sin corregir
  retroactivamente lo ya desplegado. Verificar explícitamente (byte a byte,
  como se hizo aquí) antes de concluir que un `.gitattributes` "no
  funcionó".
