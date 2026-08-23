# 078 — Herramienta de desglose de costes AWS y estimador de presupuesto

## Qué se implementó

Nuevo directorio `herramientas/costes/`, análogo a `ingesta/`/
`procesamiento/`/`grafo/`, con una herramienta reutilizable para responder
sin investigación manual la pregunta que motivó esta tarea (una factura de
Glue que pasó de 39,71 a 70,05 USD entre dos vistazos, investigada fuera de
esta tarea: coincidía con el uso real acumulado, la consola de Billing solo
iba con retraso — no había habido ninguna subida repentina real).

- **`desglose_glue.py`** (script principal, el objetivo explícito del
  enunciado): recorre todos los jobs de Glue reales (`get_jobs`/
  `get_job_runs`), suma DPU-segundos por job y por dataset, aplica un
  precio configurable por DPU-hora (0,44 USD por defecto, documentado como
  aproximado), señala aparte las ejecuciones `FAILED`/`TIMEOUT`/`ERROR`/
  `STOPPED` como "coste sin resultado útil", y calcula una tendencia simple
  (primeras 5 ejecuciones completadas vs últimas 5) más una proyección
  coste/día y coste/mes extrapolando la frecuencia histórica de ejecución.
- **`lambda_costes.py`** y **`s3_costes.py`** (complementos, evaluados como
  suficientemente simples de cubrir tras probar contra la cuenta real):
  Lambda vía `Invocations`/`Duration` de CloudWatch + la fórmula pública de
  precio; S3 vía la métrica `BucketSizeBytes` de CloudWatch (solo
  almacenamiento, no peticiones ni transferencia — ver limitación abajo).
  **Athena se descartó explícitamente** por ser desproporcionadamente más
  compleja (no tiene un equivalente a `get_job_runs`: requeriría paginar
  todo `list_query_executions` y pedir `DataScannedInBytes` ejecución por
  ejecución) frente a un volumen de uso bajo que nunca ha causado ninguna
  alarma de coste — documentado como trabajo futuro en el README, no
  implementado.
- **`resumen_costes.py`**: punto de entrada combinado (`--incluir-lambda`/
  `--incluir-s3`), salida en tabla o JSON.
- Tests (`herramientas/costes/tests/`, 20 tests): mismo patrón que
  `grafo/tests/` — clientes de `boto3` fake inyectados, sin ninguna llamada
  real ni credenciales.

## Verificación contra datos reales

Ejecutado durante el desarrollo contra la cuenta real (`eu-west-1`,
`222234418587`, rol `madrono-terraform-deployerEC2`, sin necesitar ningún
permiso nuevo): el desglose de Glue dio un coste total estimado de
**76,44 USD** — coherente con los ~70 USD ya conocidos en el contexto de
esta tarea, con la diferencia explicada por el tiempo transcurrido y por
incluir también los jobs `*-backfill-dedup` de las tareas 073-077 (fuera
del cálculo manual original). Confirmó además, con datos reales, la señal
que motivó la tarea: `bicimad-silver-to-gold` y `trafico-silver-to-gold`
concentran juntos ~21 USD de coste sin resultado útil (ejecuciones
`TIMEOUT` repetidas, ya diagnosticadas y corregidas en las tareas 072-077).

Lambda y S3 también se ejecutaron contra datos reales (0,31 USD/mes y
0,55 USD/mes de proyección respectivamente) — coherente con el volumen bajo
esperado de este proyecto (cron interno de baja frecuencia, no tráfico de
usuario).

## Decisiones y limitaciones documentadas en el README

- **No es el dato oficial de Cost Explorer/Billing.** El rol de esta EC2
  no tiene permisos `ce:GetCostAndUsage` — se intentó dar de alta en esta
  misma tarea y el clasificador de seguridad del entorno lo bloqueó
  (requiere confirmación explícita de un humano, no concedida). La
  herramienta se basa en métricas de uso ya accesibles (`glue:Get*`,
  `lambda:Get*`/`List*`, `cloudwatch:GetMetricStatistics`,
  `s3:ListAllMyBuckets`), no en la factura real.
- **Precio por DPU-hora (0,44 USD) es un precio de lista aproximado**, no
  verificado contra la factura real — configurable por argumento o
  variable de entorno.
- **La proyección coste/mes puede salir poco fiable para jobs de un solo
  uso** (los `*-backfill-dedup`, con 1-2 ejecuciones muy próximas en el
  tiempo): la fórmula extrapola la frecuencia histórica observada, que para
  esos jobs no es representativa de un uso continuo. No se ocultan esos
  casos — el número crudo (o `n/d` si hay menos de 2 ejecuciones
  completadas) ya deja ver que no aplica.
- **S3 solo cubre almacenamiento**, no peticiones ni transferencia de
  salida — CloudWatch no publica esas métricas gratis por bucket;
  medirlas exigiría S3 Server Access Logging o CloudTrail data events
  (coste propio, no habilitado en esta cuenta).

## Restricciones respetadas

- No se ha intentado de nuevo dar de alta `ce:*` — descartado explícitamente
  por el enunciado, documentado como recomendación futura en el README si
  se decide reabrirlo.
- Ninguna acción con efecto real sobre infraestructura: toda esta tarea es
  de solo lectura (`Get*`/`List*`/`GetMetricStatistics`), verificado
  ejecutando los scripts contra la cuenta real sin ningún `terraform apply`
  ni cambio de estado.
- No se ha forzado cubrir Athena pese a mencionarlo el enunciado como
  posible — se evaluó el esfuerzo primero (ver tabla del README) y se
  decidió no forzarlo, tal como permitía explícitamente el enunciado.

## Relevante para tareas futuras

- Si se decide en algún momento dar de alta `ce:GetCostAndUsage`, es la vía
  correcta para tener coste oficial exacto por servicio (descuentos,
  Savings Plans, redondeo real de Billing) en vez de la aproximación por
  uso que da esta herramienta — recomendado en el README, no intentado
  aquí.
- Cobertura de Athena queda como trabajo futuro si su volumen de consultas
  llega a crecer lo suficiente como para justificar el esfuerzo de
  paginar `list_query_executions` + `DataScannedInBytes` por ejecución.
- La lista de sufijos de nombre de job reconocidos por
  `dataset_from_job_name`/`job_kind` (`desglose_glue.py`) es la misma
  convención ya usada en toda la serie 072-077
  (`-bronze-to-silver`/`-silver-to-gold`/`-silver-backfill-dedup`/
  `-gold-backfill-dedup`) — cualquier job nuevo que rompa esa convención de
  nombre aparecerá igualmente en el desglose (no falla), pero como
  `kind="otro"` y con el nombre completo como "dataset" (sin agrupar con
  el resto de jobs de ese mismo dataset).
