# VIC_30 — secretos en todo el histórico de git con detect-secrets (ronda 5)

**Fecha:** 2026-08-30. `detect-secrets` no estaba instalado — primera vez
que corre sobre este repo. Solo lectura.

## Método

1. **Working tree actual**: `detect-secrets scan --all-files .` desde la
   raíz del repo.
2. **Todo el histórico**: `git log --all -p` no tiene filtro de "solo
   añadidos" fiable entre renombres, así que se extrajeron todas las
   líneas `+` (añadidas) de todos los commits de todas las ramas
   (`git log --all -p | grep '^+' | grep -v '^+++'`) — **214 707 líneas**,
   el conjunto de todo el texto que se ha añadido alguna vez a este repo,
   independientemente de si sigue en el HEAD actual o se borró después.

## Aviso metodológico real (no un hallazgo de seguridad, un hallazgo sobre la herramienta)

`detect-secrets scan <path>` da **`{}` en silencio, sin error ni aviso**,
en dos situaciones que se dieron al preparar este ticket:

- Escaneando un fichero fuera de cualquier repo git (probado con un
  fichero de prueba en `/tmp`, con un `AKIAIOSFODNN7EXAMPLE` de libro):
  cero resultados. Confirmado con `--string` que el plugin sí reconoce el
  valor -- el problema es específico del modo `scan <path>` fuera de un
  repo git.
- Escaneando un único fichero de texto plano dentro del repo pero **muy
  grande** (probado con el fichero de 214 707 líneas de arriba): cero
  resultados, mientras que las primeras 20 000 líneas del mismo fichero sí
  dan resultados correctos (incluida la credencial real conocida, ver
  abajo). No se ha identificado el límite exacto, pero existe.

**Por qué importa para cualquiera que repita esta auditoría en el
futuro**: un "0 resultados" de `detect-secrets` no es prueba de que el
repo esté limpio si el fichero escaneado es grande o si se escanea fuera
de un `.git` -- puede ser este límite silencioso, no una ausencia real de
secretos. Mitigación aplicada aquí: se partió el fichero de 214 707 líneas
en 11 trozos de 20 000 líneas cada uno (dentro del repo, con
`--all-files`) para obtener cobertura real confirmada.

## Resultado

- **Working tree actual**: 40 ficheros con algún hallazgo, ninguno un
  secreto real -- ver detalle abajo.
- **Histórico completo (11 trozos, 214 707 líneas)**: 370 hallazgos, de
  los cuales 18 son `Secret Keyword` (la categoría de mayor señal, valor
  cerca de una palabra como `password`/`token`/`key`); el resto (335 `Hex
  High Entropy String` + 17 `Base64 High Entropy String`) son hashes de
  git/Terraform/MLflow y datos binarios en base64 de fixtures/notebooks,
  ruido esperable de alta entropía sin relación con credenciales.

### Los 18 `Secret Keyword` del histórico, uno a uno

| Línea (contenido) | Veredicto |
|---|---|
| `app_password="pc6y-6s6c-6dar-jgit"` (×2, en el commit original y citado de nuevo en `tasks/FIL_28_...md`) | **Ya conocido — `FIL_28`.** La única credencial real jamás commiteada en este repo. |
| `` `app_password="pc6y-••••-••••-•••• (redactado)"` `` | Cita redactada de la misma credencial, en un doc de seguimiento. |
| `app_password="aaaa-bbbb-cccc-dddd", # ficticio` | El valor de reemplazo tras el fix de `FIL_28` — explícitamente ficticio. |
| `app_password: "Optional[str]"` | Anotación de tipo, sin valor. |
| `"BLUESKY_APP_PASSWORD": "test-pass"` | Placeholder de test. |
| `EMT_API_PASSWORD="tu-contraseña"` (×2) | Placeholder de documentación (`tu-contraseña` = "your password" en español, plantilla de `.env`). |
| `GOOGLE_MAPS_API_KEY="tu-api-key"` | Mismo patrón, otra API. |
| `"CAMS_ADS_API_KEY": "directo"` / `"fake-token"` (×2) / `"AEMET_API_KEY": "fake-key"` / `api_key="token"` / `api_key="fake-token"` | Placeholders de test, todos explícitamente ficticios. |
| `"accessToken": "FAKE-ACCESS-TOKEN-NOT-A-REAL-CREDENTIAL"` | Fixture de test, nombre explícito. |
| `"accessToken": "LEAKED-TOKEN-SHOULD-NOT-APPEAR"` | Valor canario deliberado para probar que un campo **se redacta** correctamente antes de llegar a Silver/Gold -- lo contrario de una fuga real. |

**Ningún hallazgo nuevo.** El único secreto real en todo el histórico de
este repo es el ya conocido y ya gestionado por `FIL_28` (credencial de
Bluesky, propietario notificado, decidió no rotar). Confirma con una
herramienta dedicada (25+ detectores por patrón de vendor + entropía) lo
que `VIC_19` ya había encontrado con `grep` dirigido a mano.

## Dato curioso para la memoria del proyecto

`detect-secrets` **no** marcó `pc6y-6s6c-6dar-jgit` por alta entropía
(`Base64`/`HexHighEntropyString` dieron `False` en la prueba aislada con
`--string`) -- lo encontró únicamente el `KeywordDetector` (por aparecer
junto a la palabra `password`). Un valor así de corto (19 caracteres,
alfanumérico en minúsculas con guiones) queda por debajo del umbral de
entropía de los detectores genéricos: si esa misma credencial se hubiera
escrito sin la palabra `password`/`app_password` al lado (p. ej. en una
variable genérica `x = "pc6y-6s6c-6dar-jgit"`), **ningún detector de este
escáner la habría encontrado**. Este es el motivo real por el que un
`grep` dirigido a mano (`VIC_19`) sigue teniendo valor incluso con un
escáner dedicado: los escáneres de entropía están calibrados para tokens
largos (JWT, claves AWS/Stripe/GitHub), no para contraseñas cortas
legibles como esta.

## Conclusión

**Cero `FIL_*` nuevos.** Confirmado con una segunda herramienta,
independiente del método original, que `FIL_28` sigue siendo el único
secreto real jamás commiteado en este repositorio.
