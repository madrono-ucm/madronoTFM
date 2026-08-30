# `herramientas/salud/` — chequeos de salud del pipeline (`FIL_16`)

Scripts de operación, mismo estilo que `herramientas/costes/`: leen datos ya
accesibles con los permisos existentes, salida tabla o JSON, código de
salida ≠ 0 si algo va mal. No se despliegan; se corren a mano o por cron.

## `frescura_gold.py`

Comprueba, por cada tabla de la capa Gold, cuánto hace que no recibe dato
nuevo (`max(date)` de la partición, o `max(processed_at)` para las tablas
con partición no temporal), y lo clasifica contra un umbral por cadencia.

Cubre el fallo silencioso tipo `FIL_11`: un job de Glue en `SUCCEEDED` que
escribe 0 filas no lo detecta nada que mire el estado del job; esto sí,
porque mira el dato.

```bash
# desde la raíz del repo, con credenciales AWS (perfil madrono):
AWS_PROFILE=madrono AWS_DEFAULT_REGION=eu-west-1 \
  python -m herramientas.salud.frescura_gold                 # producción: exit 1 si algo estancado
AWS_PROFILE=madrono AWS_DEFAULT_REGION=eu-west-1 \
  python -m herramientas.salud.frescura_gold --pipeline-congelado   # exit 0 salvo anomalía real
AWS_PROFILE=madrono AWS_DEFAULT_REGION=eu-west-1 \
  python -m herramientas.salud.frescura_gold --formato json
```

`--pipeline-congelado` se deduce solo de `PIPELINE_ENABLED=false` en el
entorno. Ver `doc/FIL-16-...md` para el diseño y los umbrales por dataset
(ruido lleva 192 h por su retraso de publicación, `aforos` está
descontinuada, etc.).

Tests: `python -m pytest herramientas/salud/` (sin credenciales, mockea
Athena).

## Alerta de fallos de Glue

La otra mitad de `FIL_16` ("el job falló") es infra:
`infra/terraform/observabilidad.tf` (EventBridge → SNS → email). Diseñada,
sin aplicar todavía (pipeline congelado). Ver `doc/FIL-16-...md`.
