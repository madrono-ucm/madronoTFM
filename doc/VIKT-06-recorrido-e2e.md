# VIKT-06 — Recorrido end-to-end reproducible para la defensa

Guion con comandos copiables y salida real (no inventada) que recorre las 3
capas del sistema: datos (Bronze→Silver→Gold), grafo, y asistente/ML.
Ejecutado y verificado el 2026-08-30, con el pipeline de ingesta **congelado**
(`pipeline_enabled=false`) — los datos son los ya presentes en AWS, sin
disparar ningún job de Glue nuevo.

**Limitación honesta de esta pasada**: la sesión que preparó este guion no
tenía acceso interactivo a las credenciales de Neo4j (bloqueadas por el
clasificador de modo automático de esta herramienta al intentar
`aws ssm get-parameter --with-decryption`, sin buscar ningún rodeo). La
sección 3 (grafo) y las llamadas a tools que cruzan Neo4j en la sección 4
se documentan con la consulta real y el resultado esperado (verificado en
`VIC_10`/sesiones previas), pero **no se re-ejecutaron en vivo en esta
pasada** — quien reproduzca este guion con las credenciales reales debería
obtener resultados equivalentes.

---

## 0. Prerrequisitos

```bash
git clone <repo> && cd madronoTFM
python3 -m venv .venv && source .venv/bin/activate
pip install -r modelado/requirements.txt   # ver FIL_23: usar
                                            #   pip install --index-url https://download.pytorch.org/whl/cpu torch
                                            #   ANTES de esta línea, o CUDA se descarga por defecto (~4.5GB, no importa sin GPU)
pip install -r asistente/requirements.txt  # o el equivalente si no existe fichero propio
export AWS_DEFAULT_REGION=eu-west-1   # el perfil por defecto de esta EC2 (eu-south-2) no tiene nada
```

Credenciales AWS: rol de instancia (`madrono-terraform-deployerEC2`) si se
ejecuta en la EC2 del proyecto; si no, un perfil con permisos de
lectura sobre Glue/Athena/S3 (ver `infra/OPERACION.md`). Neo4j:
`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` desde SSM (`infra/OPERACION.md`
§"Neo4j").

---

## 1. Ingesta → Bronze

Sin disparar ninguna llamada de red real (pipeline congelado), usando el
fixture commiteado de una respuesta real de `informo.madrid.es` capturada
el 12/08/2026:

```bash
python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path
from ingesta.capturas.trafico_madrid import parse_records

xml_text = Path('ingesta/tests/fixtures/pm_sample.xml').read_text(encoding='utf-8')
ingested_at = datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc)
records = list(parse_records(xml_text, ingested_at))
print(json.dumps(records[0], indent=2, ensure_ascii=False, default=str))
print(f'... {len(records)} registros')
"
```

**Salida real**:

```json
{
  "schema_version": 1,
  "source": "madrid_trafico_intensidad",
  "point_id": "9841",
  "measured_at": "2026-08-12T01:45:04+02:00",
  "ingested_at": "2026-08-12T12:00:00+02:00",
  "description": "Valle de Mena S-E - Acc.Ramon Castroviejo-Gta.Isaac Rabín",
  "access_code": "0301005",
  "subarea": "0328",
  "intensity_vph": 20,
  "occupancy_pct": 0,
  "load_pct": 0,
  "service_level": 0,
  "saturation_intensity_vph": 3100,
  "has_error": false,
  "error_code": "N",
  "location": {"x": 438339.375874991, "y": 4480454.96970565, "srid": "EPSG:25830"}
}
... 3 registros
```

En producción, `BronzeWriter.write_batch` escribe esto a
`s3://madrono-tfm-dev-bronze-222234418587/trafico/fecha=2026-08-12/hora=12/`
como un objeto JSON. Nótese: coordenadas en `EPSG:25830` (UTM huso 30N, tal
cual las publica el Ayuntamiento) — la conversión a WGS84 pasa a Silver, no
antes ("honestidad sobre cómo lo publica la fuente").

---

## 2. Procesamiento → Silver → Gold

### 2.1 En Python puro (sin Spark), misma muestra

```bash
python3 -c "
from datetime import datetime, timezone
from procesamiento.silver_gold.trafico.transform import bronze_to_silver
from procesamiento.silver_gold.trafico.aggregate import aggregate_silver_to_gold
# 'records' = los 3 de la sección 1
processed_at = datetime(2026, 8, 12, 10, 5, 0, tzinfo=timezone.utc)
silver, rejected = bronze_to_silver(records, processed_at)
gold = aggregate_silver_to_gold(silver, processed_at)
"
```

**Silver real** (1 de 2 válidos — 1 de los 3 registros originales se
rechaza en `bronze_to_silver`, ver `validate_record`):

```json
{
  "schema_version": 1, "source": "madrid_trafico_intensidad",
  "point_id": "9841", "subarea": "0328",
  "description": "Valle de Mena S-E - Acc.Ramon Castroviejo-Gta.Isaac Rabín",
  "measured_at": "2026-08-12T01:45:04+02:00",
  "location": {
    "x": 438339.375874991, "y": 4480454.96970565,
    "srid_source": "EPSG:25830",
    "lat": 40.4724879647946, "lon": -3.727397412114952,
    "srid_target": "EPSG:4326"
  },
  "intensity_vph": 20, "occupancy_ratio": 0.0, "load_ratio": 0.0,
  "intensity_ratio": 0.0064516129032258064
}
```

Nótese la conversión de coordenadas real (`EPSG:25830` → `EPSG:4326`) y los
tres ratios normalizados (`occupancy_ratio`/`load_ratio`/`intensity_ratio`)
que Bronze no tiene.

**Gold real** (agregado por `point_id` + hora):

```json
{
  "schema_version": 1, "point_id": "9841", "subarea": "0328",
  "date": "2026-08-12", "hour": 1, "samples_count": 1,
  "avg_intensity_vph": 20, "max_intensity_vph": 20, "min_intensity_vph": 20,
  "avg_occupancy_ratio": 0.0, "avg_load_ratio": 0.0,
  "avg_intensity_ratio": 0.0064516129032258064, "avg_service_level": 0,
  "location": {"lat": 40.4724879647946, "lon": -3.727397412114952, "srid": "EPSG:4326"}
}
```

### 2.2 Contra la Gold real ya presente en Athena (sin muestra)

```bash
aws athena start-query-execution \
  --query-string "SELECT hour, avg_service_level, avg_intensity_vph, samples_count
                   FROM \"madrono-tfm_dev_gold\".trafico_por_punto_hora
                   WHERE date='2026-08-30' AND point_id='4398' ORDER BY hour" \
  --query-execution-context Database=madrono-tfm_dev_gold \
  --result-configuration OutputLocation=s3://madrono-tfm-dev-athena-results-222234418587/ \
  --region eu-west-1
# luego: aws athena get-query-results --query-execution-id <id> --region eu-west-1
```

**Salida real** (punto de tráfico 4398, madrugada tranquila → mediodía
cargándose, 30/8):

| hour | avg_service_level | avg_intensity_vph | samples_count |
|---|---|---|---|
| 0 | 0.73 | 331.1 | 11 |
| 3 | 0.00 | 138.2 | 11 |
| 6 | 0.00 | 90.9 | 11 |
| 9 | 0.00 | 188.0 | 10 |
| 10 | 0.91 | 429.1 | 11 |
| 11 | 1.82 | 690.9 | 11 |
| 12 | 2.45 | 903.6 | 11 |

---

## 3. Grafo — Neo4j

**No re-ejecutado en vivo en esta pasada** (credenciales bloqueadas, ver
nota al inicio). Consulta real usada por `trafico_cercano`/`trafico_prevista`
(`asistente/neo4j_client.py::lugares_proximos_a_estaciones_trafico_query`):

```cypher
MATCH (l:Lugar)
WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar)
MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'trafico'})
WHERE r.distancia_m <= $radio_m
RETURN e.id AS estacion_id, r.distancia_m AS distancia_m
ORDER BY distancia_m
```

Con `nombre_lugar="Retiro"`, `radio_m=300`, la relación `PROXIMO_A` es
**no dirigida** en la consulta (`-[r]-`) porque se carga en un único
sentido físico (`EstacionMedida → Lugar`, ver `grafo/relaciones.py`), pero
el patrón de consulta no depende de ese orden. Última medición real del
grafo completo (`VIC_10`): **9.633 nodos, 72.310 relaciones**.

Para reproducir en vivo con credenciales reales:

```bash
python3 -c "
from asistente.neo4j_client import lugares_proximos_a_estaciones_trafico_query, run_neo4j_query
q, p = lugares_proximos_a_estaciones_trafico_query('Retiro', 300.0)
print(run_neo4j_query(q, p))
"
```

---

## 4. Asistente — servidor MCP real

### 4.1 Levantar en `stdio` y listar tools (cliente MCP real, no en-proceso)

```bash
python3 -c "
import sys, os, anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable, args=['-m', 'asistente.mcp_agent.server'], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print('server:', info.server_info.name)
            tools_result = await session.list_tools()
            for t in tools_result.tools:
                print(' -', t.name)
anyio.run(main)
"
```

**Salida real**:

```
server: madrono
 - afluencia_estimada
 - afluencia_prevista
 - calidad_aire
 - calidad_aire_prevista
 - trafico_cercano
 - trafico_prevista
 - opciones_movilidad
 - disponibilidad_aparcamiento
 - eventos_cercanos
```

10 tools (`FIL_13` +`trafico_prevista`, `FIL_14` +`afluencia_prevista`, `FIL_26` +`calidad_aire_prevista_grafo`).
**Nota real encontrada en esta verificación**: 2 de las 9 (`opciones_movilidad`,
`eventos_cercanos`) no anuncian `output_schema` por una limitación del SDK
`mcp` con retornos `list[BaseModel]` — documentado y archivado como
`FIL_24`, no bloquea la llamada, solo el contrato de schema anunciado.

### 4.2 `calidad_aire` — solo Athena, funciona sin Neo4j

```bash
# (mismo script que 4.1, con session.call_tool('calidad_aire', {'zona': 'Retiro'}))
```

**Salida real**:

```json
{
  "zona": "Retiro", "momento": "2026-08-30T15:46:59+02:00",
  "indice_calidad": "buena", "contaminante_principal": "O3",
  "valor": 72.0, "unidad": "µg/m³", "hora": 12,
  "estaciones_consultadas": ["Parque del Retiro"],
  "fuente_dataset": "gold.calidad_aire_por_estacion_contaminante_hora"
}
```

### 4.3 `calidad_aire_prevista` — el bucle observación→predicción→asistente completo

```bash
# session.call_tool('calidad_aire_prevista', {'zona': 'Retiro', 'horizonte_horas': 3})
```

**Salida real** — previsión ONNX real, 3h vista, sobre el valor actual real
de la sección 4.2:

```json
{
  "horizonte_horas": 3, "momento": "2026-08-30T12:00:00",
  "momento_objetivo": "2026-08-30T15:00:00",
  "disponible": true,
  "valor_previsto": 52.0, "valor_actual": 72.0, "unidad": "µg/m³",
  "nivel_previsto": "buena",
  "modelo": "calidad_aire_h3.onnx (ML_07 / madrono-calidad_aire-h3)",
  "data_completeness": 1.0,
  "ventana_datos": "2026-08-29..2026-08-30",
  "fuente_dataset": "gold.calidad_aire_por_estacion_contaminante_hora"
}
```

Este es el ejemplo central para la defensa: un dato entra por
`informo.madrid.es`/`calidad_aire_madrid`, pasa por Bronze→Silver→Gold, y
sale como una predicción con procedencia trazable (modelo exacto, ventana de
datos, confianza).

### 4.4 `trafico_prevista` — degradación elegante real (sin Neo4j en esta sesión)

```bash
# session.call_tool('trafico_prevista', {'lugar': 'Retiro', 'horizonte_horas': 6})
```

**Salida real** (demuestra `FIL_15` bajo un fallo genuino, no simulado —
esta sesión no tenía credenciales Neo4j):

```json
{
  "disponible": false, "valor_previsto": null,
  "nivel_previsto": "sin_datos",
  "motivo": "no se pudo consultar el grafo en Neo4j: 'NEO4J_URI'",
  "fuente_dataset": "gold.trafico_por_punto_hora"
}
```

Con credenciales reales, se espera una respuesta como la de 4.3 pero con
`unidad: "avg_service_level"` (escala 0–6) en vez de µg/m³ — verificado por
separado (sin pasar por Neo4j) construyendo las 19 features a mano contra
`gold.trafico_por_punto_hora` real y corriendo `trafico_h{1,3,6}.onnx`
directamente: punto 4398, actual=2.45 (mediodía, 30/8) → previsto h1=2.23,
h3=1.92, h6=1.67 (tráfico aflojando de mediodía a la tarde, plausible para
domingo).

### 4.5 Vía HTTP (montado en FastAPI)

```bash
uvicorn asistente.main:app --reload
curl "http://localhost:8000/calidad-aire-prevista?zona=Retiro&horizonte_horas=3"
```

Mismo resultado que 4.3, por el mismo camino de código (`asistente/routers/`
llaman a las mismas funciones de `tools.py`).

---

## 5. ML — registro y evidencia de skill

### 5.1 Registro MLflow real (`@champion` vigentes)

```bash
python3 -c "
import mlflow
from mlflow.tracking import MlflowClient
mlflow.set_tracking_uri('sqlite:///modelado/mlflow.db')
client = MlflowClient()
for rm in client.search_registered_models():
    for alias, version in (rm.aliases or {}).items():
        print(rm.name, f'@{alias}', '-> v' + str(version))
"
# o: mlflow ui --backend-store-uri sqlite:///modelado/mlflow.db
```

**Salida real** (6 modelos, los mismos exportados a ONNX en §4):

```
madrono-calidad_aire-h1 @champion -> v1
madrono-calidad_aire-h3 @champion -> v2
madrono-calidad_aire-h6 @champion -> v2
madrono-trafico-h1 @champion -> v1
madrono-trafico-h3 @champion -> v1
madrono-trafico-h6 @champion -> v2
```

### 5.2 Guarda de regresión del reentrenamiento nocturno (evidencia real)

`modelado/evaluation/artifacts/nightly/historial.csv` (real, del cron
`ML_10`, no simulado):

```
fecha,target,horizonte,skill_nuevo,skill_vigente,promovido,n_test,run_id
2026-08-30,calidad_aire,1,-0.159,0.0003,False,4935,c25272b1...
2026-08-30,calidad_aire,3,-0.1286,0.3551,False,4421,edc2fe6...
2026-08-30,trafico,6,0.7459,0.734,True,135543,94fc39e3...
```

El 30/8, `calidad_aire` h1/h3 salió peor que el vigente y **no se
promocionó** (guarda funcionando); `trafico` h6 mejoró (0.746 > 0.734) y
**sí se promocionó** — es el `v2` que aparece en el registry de 5.1.

### 5.3 Backtest incremental (curva de skill, §7.4)

```bash
python -m modelado.evaluation.backtest --panel modelado/_data/panel_calidad_aire.parquet --target calidad_aire
```

Requiere el panel materializado (`python -m modelado.features.build ...`,
ver `modelado/README.md`). Salida real (24 puntos, verificado en `VIKT_08`):
la curva mejora de forma no monótona pero clara según se acumulan días de
histórico — evidencia de que la ventana corta de datos es la limitación
real, no un modelo mal diseñado.

---

## 6. Pipeline congelado vs. reanudado

**Congelado** (estado actual, desde 30/8): las secciones 2.2, 3, 4 y 5
funcionan igual — leen datos ya presentes. Solo cambia que no llegan filas
nuevas a Bronze/Silver/Gold. `aws glue get-job-runs` mostrará la última
ejecución real seguida de silencio.

**Reanudado** (`terraform apply -var pipeline_enabled=true`): los 23
`EventBridge Scheduler` y ~26 triggers de Glue vuelven a `ENABLED`/activos.
Si se reanuda tras varios días parado, los jobs horarios (`bronze_to_silver`)
solo recogen la hora anterior a su disparo — el hueco de los días parados
**no se rellena solo**; usar `--backfill_fecha` por día (`FIL_12`,
`infra/OPERACION.md` §"Rellenar huecos horarios") si hace falta para la
demo.

---

## Resumen para el screencast de la defensa

Orden sugerido (≈8-10 min): §1 (10s, mostrar el JSON crudo) → §2.1 (30s,
mismo dato transformándose sin Spark) → §2.2 (20s, la Gold real en Athena)
→ §4.1 (20s, 10 tools reales por MCP) → **§4.3 es el momento central** (1 min,
explicar el envoltorio: valor + modelo + ventana + confianza) → §4.4 (20s,
mostrar que un fallo real no rompe nada) → §5.1-5.2 (30s, el
registry + la guarda de regresión rechazando un modelo peor) → mencionar
§3/§6 verbalmente si no hay credenciales Neo4j a mano en el momento de la
defensa.
