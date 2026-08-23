# `herramientas/costes/` — desglose de coste AWS y estimador de presupuesto (tarea 078)

Herramienta reutilizable para responder, con un solo comando, la pregunta
que en la tarea 078 hizo falta investigar a mano: *¿cuánto está costando
cada job/dataset, y hacia dónde va la tendencia?* Nace de una alarma real
de facturación de Glue (39,71 USD vistos en un momento, 70,05 USD al
revisarla más tarde) que, investigada, resultó ser solo el retraso habitual
de la consola de Billing frente al uso real — no una subida repentina. Ver
`doc/078-desglose-costes-estimador-presupuesto.md` para el resumen de esa
investigación y de esta tarea.

## Qué mide y qué NO mide (leer antes de confiar en los números)

**Esto es una estimación por uso, no el dato oficial de Cost Explorer/
Billing.** El rol de esta EC2 no tiene permisos de Cost Explorer
(`ce:GetCostAndUsage`): se intentó dar de alta en esta misma tarea y el
clasificador de seguridad del entorno lo bloqueó (requiere confirmación
explícita de un humano, no concedida). Cada módulo calcula el coste a
partir de métricas de **uso** (DPU-segundos de Glue, invocaciones/duración
de Lambda, tamaño de bucket de S3) multiplicadas por un precio de lista
configurable — no ve descuentos, créditos, Savings Plans, ni el redondeo o
agregación real que aplica Billing. Trátalo como una señal de tendencia y
de "¿qué job es el más caro / cuál está fallando y aun así costando?", no
como sustituto de la factura.

Si en el futuro se decide dar de alta `ce:GetCostAndUsage` (recomendado si
esta herramienta demuestra ser útil y se quiere el dato oficial sin
aproximar), esa es la vía correcta para tener coste exacto por servicio —
no reintentado en esta tarea porque ya se evaluó y se descartó una vez.

| Servicio | Cubierto | Cómo | Qué falta |
|---|---|---|---|
| **Glue** | Completo (objetivo principal) | `glue:GetJobs`/`GetJobRuns` → DPU-segundos reales × precio/DPU-hora | — |
| **Lambda** | Sí (complemento) | `lambda:GetFunctionConfiguration` + CloudWatch `Invocations`/`Duration` → fórmula pública de precio | No descuenta el tramo gratuito (1M peticiones + 400 000 GB-s/mes) — ver `lambda_costes.py` |
| **S3** | Sí, solo almacenamiento (complemento) | CloudWatch `BucketSizeBytes` × precio/GB-mes | No cubre peticiones (`PUT`/`GET`) ni transferencia de salida — CloudWatch no las publica gratis por bucket; medirlas exigiría Server Access Logging o CloudTrail data events (coste propio, no habilitado) |
| **Athena** | No cubierto | — | `list_query_executions` no agrupa por "job" como sí hace Glue; requeriría paginar todo el histórico de ejecuciones y pedir `DataScannedInBytes` una por una (N+1 llamadas) para atribuir coste por dataset. Evaluado y descartado por complejidad desproporcionada frente al resto — el volumen de consultas Athena de este proyecto es bajo (uso puntual desde `grafo/extract.py` y verificaciones manuales), no la causa de ninguna alarma de coste hasta ahora. Recomendado como trabajo futuro solo si se detecta que empieza a pesar. |

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r herramientas/costes/requirements.txt
```

`boto3` ya está instalado en la EC2 de este proyecto (lo usan `ingesta`/
`grafo`); en la EC2 de terraform/despliegue, el rol de instancia
(`madrono-terraform-deployerEC2` a fecha de esta tarea) ya tiene permisos
de solo lectura suficientes (`glue:Get*`, `lambda:Get*`/`List*`,
`s3:ListAllMyBuckets`, `cloudwatch:GetMetricStatistics`) — no hace falta
ninguna credencial ni permiso adicional.

## Uso

```bash
# Solo Glue (objetivo principal de la tarea), tabla en terminal:
python3 -m herramientas.costes.desglose_glue

# Con Lambda y S3 también:
python3 -m herramientas.costes.resumen_costes --incluir-lambda --incluir-s3

# JSON para consumo programático:
python3 -m herramientas.costes.resumen_costes --formato json > costes.json

# Precio por DPU-hora distinto del asumido (0.44 USD, aproximado -- ver más abajo):
python3 -m herramientas.costes.desglose_glue --precio-dpu-hora 0.40
# o, equivalente, variable de entorno:
GLUE_PRICE_PER_DPU_HOUR=0.40 python3 -m herramientas.costes.desglose_glue
```

`desglose_glue.py` es el script principal (ejecutable solo, sin
dependencias de los otros dos); `resumen_costes.py` es el punto de entrada
combinado que además puede traer Lambda/S3 con `--incluir-lambda`/
`--incluir-s3`. Ambos aceptan `--region` (por defecto: `AWS_REGION`/
`AWS_DEFAULT_REGION` del entorno, o `eu-west-1` si ninguna está fijada —
la región real de este proyecto).

## Metodología — Glue (`desglose_glue.py`)

1. Lista todos los jobs de Glue reales de la cuenta (`get_jobs`) y, para
   cada uno, todas sus ejecuciones disponibles (`get_job_runs` — Glue solo
   retiene un histórico limitado, no hay forma de pedir "desde tal
   fecha").
2. Suma `DPUSeconds` (ya calculado por Glue por ejecución: DPUs asignadas ×
   segundos) por job y por dataset (el dataset se deriva del nombre del job
   quitando el prefijo `madrono-tfm-dev-` y el sufijo conocido —
   `-bronze-to-silver`, `-silver-to-gold`, `-silver-backfill-dedup`,
   `-gold-backfill-dedup`).
3. Aplica el precio configurable (`--precio-dpu-hora` / env
   `GLUE_PRICE_PER_DPU_HOUR`, por defecto **0,44 USD/DPU-hora** — precio de
   lista aproximado de Glue 4.0 en `eu-west-1` a fecha de esta tarea, **no**
   el dato oficial de la factura).
4. Señala aparte las ejecuciones `FAILED`/`TIMEOUT`/`ERROR`/`STOPPED` (Glue
   cobra el tiempo consumido igual si falla) como "coste sin resultado
   útil" — la señal más urgente, no solo el total: es exactamente lo que
   motivó esta tarea (jobs en bucle de timeout facturando sin producir
   dato nuevo).
5. Calcula una tendencia simple por job: DPU-segundos medio de las
   primeras 5 ejecuciones completadas vs las últimas 5 (con pocas
   ejecuciones históricas ambas ventanas pueden solaparse — sigue siendo la
   señal más simple razonable, el campo `sample_size_real` deja claro
   cuántas ejecuciones hay detrás).
6. Proyecta coste/día y coste/mes: coste medio de las últimas 5 ejecuciones
   × frecuencia histórica de ejecución (nº de ejecuciones / días entre la
   primera y la última disponible). **Supuesto importante**: asume que el
   job sigue al mismo ritmo que su histórico — si un trigger está pausado
   (`DEACTIVATED`) o es un job de un solo uso (los `*-backfill-dedup`, con
   1-2 ejecuciones muy próximas en el tiempo), la proyección puede salir
   absurdamente alta o `n/d` (menos de 2 ejecuciones completadas). No se
   filtran ni se ocultan esos casos: el número crudo ya deja ver que no es
   fiable para ese job en concreto (frecuencia histórica poco representativa).

## Metodología — Lambda / S3

Ver el docstring de cabecera de `lambda_costes.py`/`s3_costes.py`
respectivamente — misma idea (uso real × precio de lista configurable),
explicado ahí en detalle junto al código que lo calcula.

## Tests

```bash
python3 -m unittest discover -s herramientas/costes/tests -t .
```

Mismo criterio que `grafo/tests/`: clientes de `boto3` fake inyectados
(`FakeGlueClient`, `FakeLambdaClient`, `FakeCloudWatchClient`,
`FakeS3Client`...), **sin ninguna llamada real a AWS ni credenciales**. La
coherencia con datos reales (que el desglose de Glue diera un total
cercano a los ~70 USD ya conocidos en esta sesión) se verificó aparte,
ejecutando el script contra la cuenta real durante el desarrollo de esta
tarea — no forma parte de la suite de tests automática.
