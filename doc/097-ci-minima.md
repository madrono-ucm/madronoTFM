# 097 — CI mínima (Prioridad 5)

## Contexto

Con la Prioridad 4 (tools del asistente) completa, siguiente ítem
priorizado en `NEXT_STEPS.md`: no existía ningún `.github/workflows/` —
nada corría los 841 tests reales del proyecto automáticamente, ni
`terraform fmt`/`validate` en cada PR. Explícitamente marcada como
"recomendado no bloqueante", pero barata y de valor real: habría detectado
antes el nit de formato de `lambda.tf` (ver abajo) y sigue sirviendo de red
de seguridad automática que complementa la revisión humana de PRs.

## Qué se hizo

`.github/workflows/ci.yml`, dos jobs independientes, en cada `pull_request`
y `push` a `main`:

- **`tests`**: instala las dependencias reales de `ingesta/`, `procesamiento/`
  (vacío hoy, incluido por si crece), `grafo/`, `asistente/` y
  `herramientas/costes/` (`requirements.txt` de cada uno) y ejecuta
  `pytest` sobre las cinco carpetas -- 841 tests, ninguno necesita
  credenciales ni conexión real (todos mockean Athena/Neo4j/boto3 donde
  hace falta).
- **`terraform`**: `terraform fmt -check -recursive` + `terraform init
  -backend=false` + `terraform validate` -- deliberadamente **sin**
  `terraform plan`: un plan real necesitaría acceso al backend S3/DynamoDB
  y credenciales AWS reales como secreto de este repositorio de GitHub,
  una decisión de quien administra el repositorio (rol/permisos, OIDC vs.
  claves estáticas), no algo que esta tarea deba decidir unilateralmente.
  `-backend=false` evita esa dependencia por completo mientras sigue
  cubriendo sintaxis, tipos y formato.

### Dos arreglos reales encontrados montando la CI

1. `infra/terraform/lambda.tf` no pasaba `terraform fmt -check` -- la
   condición añadida por la tarea `092-terraform-fileset-excluir-pycache`
   (PR #136, `madrono-agent`) tenía la línea de continuación mal indentada.
   Cosmético (`terraform validate` ya pasaba, ningún comportamiento
   afectado), corregido con `terraform fmt -recursive`.
2. 3 tests (`test_callejero_madrid.py` x2, `test_poi_madrid.py` x1) usaban
   `Path.read_text()` sin `encoding="utf-8"` explícito sobre fixtures JSON
   con caracteres no ASCII -- en Windows, `read_text()` sin argumento usa
   la codificación del sistema (`cp1252`, no UTF-8), y fallaban con
   `UnicodeDecodeError` en cualquier sesión de desarrollo local en Windows
   (varias sesiones de esta semana los vieron y los descartaron como "fallo
   preexistente no relacionado" sin arreglarlos). En Linux (y por tanto en
   CI, `ubuntu-latest`) el `encoding` por defecto ya es UTF-8, así que
   nunca habrían fallado ahí -- exactamente el tipo de bug que una sesión
   de desarrollo en un SO distinto al de CI puede no detectar nunca sin
   pasar explícitamente `encoding="utf-8"`. Arreglado en los 3 sitios.

## Verificación

- `python3 -m pytest ingesta/ procesamiento/ grafo/ asistente/ herramientas/`
  → **841 passed, 1 skipped** (0 fallos, primera vez en varias sesiones
  que la suite completa está en verde en Windows).
- `terraform fmt -check -recursive` → limpio.
- `terraform init -backend=false -input=false` + `terraform validate` →
  `Success!`, verificado en local sin ninguna credencial AWS.
- YAML del workflow verificado con `yaml.safe_load` (sintaxis válida,
  2 jobs).

## Restricciones respetadas

- Ningún `terraform apply`/`plan` real, ni credenciales AWS añadidas a
  ningún sitio (ni a este repositorio de GitHub ni a ningún fichero).
- No se ha tocado el resto del drift de Terraform (Prioridad 1, en curso
  por `madrono-agent`, tareas 093/094).

## Relevante para tareas futuras

- Añadir `terraform plan` de solo lectura al job `terraform` cuando quien
  administra el repositorio configure credenciales AWS de solo lectura
  como secreto (recomendado: rol OIDC, no claves estáticas de larga
  duración) -- la Prioridad 5 original ya lo señalaba como parte de la CI
  "completa"; esta tarea entrega la mitad que no depende de esa decisión.
- Cualquier test futuro que lea ficheros con `Path.read_text()`/`open()`
  debe pasar `encoding="utf-8"` explícito -- el comportamiento por defecto
  varía por sistema operativo y el bug solo aparece en desarrollo local en
  Windows, nunca en CI (Linux).
