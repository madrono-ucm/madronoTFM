---
id: 26
slug: productores-lambda-handlers
title: Handlers Lambda de captura completa — lote 1/3 (tráfico, EMT, BiciMAD, aparcamientos,
  aire)
status: in_progress
force: true
allow_infra_apply: false
branch: task/026-productores-lambda-handlers
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T15:41:31+00:00'
updated_at: '2026-08-14T16:11:58.347657+00:00'
started_at: '2026-08-14T16:11:58.347634+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Segundo paso hacia producción, tras la 025 (BronzeWriter con soporte S3). Cada
productor (`ingesta/capturas/*.py`) se implementó deliberadamente acotado a una
**muestra pequeña** (tareas 002-024): sin bucle, sin escribir el dataset completo,
por la restricción de disco de esta EC2 que ya no aplica una vez el destino es S3.
Esta tarea prepara el código para ejecutarse como AWS Lambda, haciendo la captura
**completa** (no la muestra) y escribiendo en Bronze real vía `BronzeWriter`
(tarea 025). Todavía no se despliega nada (eso es la tarea 029/030) — es
exclusivamente código Python.

**Nota importante**: un primer intento de hacer esto para los 14 productores de
una sola vez agotó el presupuesto por tarea ($6) sin llegar a comitear nada — el
trabajo se perdió entero. Por eso esta tarea cubre **solo un lote de 5
productores**; el resto está repartido en las tareas 027 y 028 (mismo patrón, sin
depender unas de otras salvo el orden de la cola).

## Objetivo

Añadir un `lambda_handler(event, context)` a cada uno de estos 5 productores:

| Productor | Función |
|---|---|
| `trafico_madrid.py` (002) | ya tiene `capture_once`/bucle — solo falta el wrapper `lambda_handler` |
| `transporte_publico_madrid.py` (003/024) | captura completa (no limitada a `EMT_SAMPLE_SIZE`) |
| `bicimad.py` (004) | captura completa (no limitada a `BICIMAD_SAMPLE_SIZE`) |
| `aparcamientos_madrid.py` (005) | captura completa (no limitada a `MADRID_PARKING_SAMPLE_SIZE`) |
| `calidad_aire_madrid.py` (006) | captura completa |

No toques ningún otro productor — los demás (meteorología, ruido, afluencia,
aforos, bluesky, agenda de eventos, AEMET, CAMS, cartelera de cines) están fuera
del alcance de esta tarea concreta, cubiertos en las tareas 027/028.

## Alcance concreto

1. Para cada uno de los 5 productores, localiza la función que ya hace el
   fetch+normalize **sin** el recorte a "unos pocos registros" (revisa cada
   módulo: en la mayoría el recorte ocurre solo al construir la muestra
   commiteada, no en el fetch en sí — confírmalo caso por caso, no lo asumas para
   todos).
2. Añade `lambda_handler(event, context)` que: llama a esa función de captura
   completa, construye un `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)`,
   y escribe el resultado con `write_batch`. Debe funcionar tanto si
   `BRONZE_BASE_PATH` es local (para poder probarlo en esta EC2 sin tocar S3) como
   `s3://...` (gracias a la tarea 025).
3. Si alguno de los 5 no separaba claramente "captura completa" de "captura
   muestra" y refactorizarlo es más invasivo de lo razonable, hazlo con criterio
   (es exactamente el tipo de refactor que esta tarea espera) — pero si quedara
   bloqueado por algo imprevisto, documenta el motivo en
   `doc/026-productores-lambda-handlers.md` y continúa con el resto de los 5; no
   dejes que uno bloquee toda la tarea.
4. Añade tests para cada `lambda_handler` nuevo (con dobles de red y de
   `BronzeWriter`/`boto3`, sin llamadas reales).
5. Actualiza `ingesta/README.md` señalando, para cada uno de estos 5 productores,
   que ya tiene un `lambda_handler` listo para desplegar.

## Restricciones

- Alcance **estrictamente estos 5 productores** — no adelantes trabajo de las
  tareas 027/028, aunque te parezca poco esfuerzo adicional: mantener el alcance
  pequeño es precisamente lo que evita repetir el fallo por presupuesto agotado.
- NO despliegues nada en AWS en esta tarea (ni Lambda, ni nada) — es solo código.
- NO ejecutes una captura completa real contra las fuentes en vivo si eso implicara
  volumen grande de datos hacia algún sitio (evita escribir localmente el dataset
  completo de fuentes grandes como tráfico; prueba la lógica con dobles/mocks, no
  con una ejecución real de producción).

## Criterios de aceptación

- Los 5 productores de la tabla tienen un `lambda_handler` funcional y probado
  (con dobles, no red real).
- `doc/026-productores-lambda-handlers.md` deja constancia de cualquier productor
  que haya quedado sin resolver del todo, con el motivo.
- Todos los tests del proyecto siguen pasando.
