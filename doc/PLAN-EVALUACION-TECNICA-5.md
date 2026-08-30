# Plan de evaluación técnica — ronda 5 (análisis estático II: tipos, infra, secretos históricos)

**Fecha:** 2026-08-30 · **Contexto:** la ronda 4 (`VIC_25`-`27`,
`doc/PLAN-EVALUACION-TECNICA-4.md`) cubrió lint (`ruff`), seguridad de
aplicación (`bandit`) y CVEs de dependencias (`pip-audit`) — 2 `FIL_*`
nuevos, ambos de severidad baja. Quedan 3 ángulos de análisis estático
distintos, con herramientas distintas, todavía sin tocar por ninguna
ronda anterior:

1. **Comprobación de tipos** (`mypy`) — `ruff` (ronda 4) solo cubre reglas
   de estilo/patrones sintácticos (familia `pyflakes`), no infiere tipos;
   un `mypy` real puede encontrar una clase de bug que `ruff` no ve
   (pasar un `Optional[X]` donde se espera `X`, una firma de función
   inconsistente entre el llamador y la definición).
2. **Seguridad de infraestructura como código** (`checkov` sobre
   `infra/terraform/`) — las rondas 1-3 leyeron `lambda.tf`/`variables.tf`
   a mano buscando lógica de negocio (productores, IAM, variables
   muertas); ningún ronda corrió un escáner dedicado de malas prácticas
   de seguridad en Terraform (buckets públicos, cifrado en reposo
   ausente, políticas IAM demasiado permisivas).
3. **Secretos en todo el histórico de git** (`detect-secrets scan`) — el
   hallazgo crítico de `VIC_19`/`FIL_28` (credencial de Bluesky) se
   encontró con `git log --all -p | grep`, un método ad-hoc dependiente de
   los patrones de búsqueda elegidos a mano. Un escáner dedicado con
   detectores de entropía + reglas por tipo de credencial (AWS keys,
   tokens JWT, etc.) da más confianza de que no quede ningún otro secreto
   sin encontrar, sin depender de adivinar el patrón correcto.

Herramientas elegidas por ser instalables vía `pip` (auditable, sin
descargar binarios de terceros): `mypy`, `checkov`, `detect-secrets`.
Instaladas solo en el `.venv` compartido de esta EC2 para esta auditoría.

## Tickets

| # | Ticket | Alcance |
|---|---|---|
| `VIC_28` | Comprobación de tipos con `mypy` | Bugs reales de tipos (no solo `Optional` sin manejar — inconsistencias de firma, atributos inexistentes) |
| `VIC_29` | Seguridad de IaC con `checkov` sobre `infra/terraform/` | Malas prácticas reales de seguridad en la infraestructura, no solo el repaso manual de lógica ya hecho en rondas 1-3 |
| `VIC_30` | Secretos en todo el histórico de git con `detect-secrets` | Confirmar (o ampliar) el hallazgo de `VIC_19`/`FIL_28` con un escáner dedicado, no solo `grep` |

Sin cambios de código en ningún ticket (las 3 herramientas son de solo
lectura); hallazgos reales → `FIL_*` nuevo (numeración siguiente: **33**).

## Cierre (30/8) — 3/3 completados

- `VIC_28` (mypy): 97 errores en 28 ficheros, casi todos por patrones de
  tipado dinámico deliberados (bolsas de kwargs, alias de tipo como
  string) o control de flujo que `mypy` no sigue. Un footgun latente real
  (`BronzeWriter.partition_dir()` asume `Path` pero es `str` en modo S3,
  hoy inalcanzable) → `FIL_33` (renumerado a **`FIL_40`** el 30/8, ver
  nota de cierre más abajo).
- `VIC_29` (checkov): 260 hallazgos, ~230 controles enterprise que no
  encajan con la prioridad de coste 0 del proyecto, 4 sobre `kafka.tf`
  (nunca aplicado), 12 sobre decisiones de coste vs. robustez ya tomadas
  a propósito. Ningún `FIL_*`.
- `VIC_30` (detect-secrets, histórico completo): 18 hallazgos
  `Secret Keyword` en las 214 707 líneas jamás añadidas al repo, los 18
  revisados uno a uno — confirma que `FIL_28` sigue siendo el único
  secreto real. Ningún `FIL_*` nuevo, pero sí un aviso metodológico real
  sobre un límite silencioso de la herramienta con ficheros grandes.

**1 `FIL_*` nuevo, severidad baja.** Igual que la ronda 4, el análisis
estático (tipos, IaC, secretos históricos) no encontró ningún bug
funcional ni vulnerabilidad explotable — corrobora, con métodos y
herramientas completamente distintas, la salud ya verificada por las
rondas 1-4.

### Nota (30/8, posterior al cierre): colisión de numeración `FIL_32`/`33`

Misma situación documentada en `doc/PLAN-EVALUACION-TECNICA-4.md`: la
rama sin mergear `feat/fil31-trafico-stgnn-tool` (otra sesión, mapa
animado/grafo canónico) reutiliza `FIL_32`-`38` para tickets propios sin
relación con esta ronda. Renumerado proactivamente el `FIL_33` de esta
ronda a **`FIL_40`**
(`tasks/FIL_40_bronzewriter-partition-dir-type-inconsistente-en-modo-s3.md`,
mismo contenido). **Pendiente de recomprobar cuando esa rama se mergee a
`main`** -- confirmar que `FIL_39`/`FIL_40` no colisionan con lo que
aterrice.
