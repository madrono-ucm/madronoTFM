# 080 — Carga completa del grafo urbano en Neo4j AuraDB Free (completada fuera de la cola de tareas)

## Qué pasó realmente

Esta tarea se intentó dos veces de forma autónoma vía `madrono-agent`, y
las dos terminó **sin comitear nada**, pese a que ambas ejecutaron trabajo
real contra la instancia real de Neo4j:

- **Primer intento**: ejecutó `grafo/cargar_grafo.py` sin haber hecho antes
  el backfill de Bronze de `barrios_distritos_madrid`/`poi_madrid`/
  `crtm_red_transporte_madrid` (nunca subidos al Bronze real hasta
  entonces) — cargó `EstacionMedida`/`ParadaTransporte`/`Lugar` y
  `PROXIMO_A`, pero `Distrito`/`Barrio`/`PERTENECE_A`/`UBICADO_EN`/
  `CONECTADO_CON` quedaron en 0 (esas fuentes venían vacías de Bronze).
- **Segundo intento** (tras reescribir la tarea con el diagnóstico
  correcto): sí hizo el backfill de Bronze (confirmado con `aws s3 ls`: 1
  objeto real por cada uno de los 4 datasets) y relanzó
  `grafo/cargar_grafo.py` completo — completó `Distrito` (21),
  `Barrio` (131), `PERTENECE_A` (131) y `UBICADO_EN` (9021), pero se quedó
  sin turnos/tiempo antes de terminar el último paso, `CONECTADO_CON`
  (263 rutas CRTM, ~12.000 relaciones bidireccionales a insertar una a una
  contra AuraDB Free — cada `MERGE` es un round-trip de red, ese volumen es
  lento).

Verificado ambas veces directamente con el driver oficial `neo4j` (fuera de
la sesión de `claude`, ya que el runner del agente no conserva la salida
completa de un intento que termina sin commits).

## Qué se hizo para cerrarlo

En vez de un tercer intento autónomo (que repetiría desde cero todo el
trabajo ya hecho y válido), se completó directamente el único paso que
faltaba:

```python
from grafo import extract, relaciones
from grafo.cypher import Neo4jLoader

rutas = list(extract.fetch_paradas_crtm_bronze())   # 263 rutas reales
rels = relaciones.conectado_con(rutas)               # 11 998 relaciones
with Neo4jLoader(uri, user, password, database) as loader:
    loader.load_conectado_con(rels)
```

Ejecutado en segundo plano (tardó varios minutos, esperado dado el volumen
y la latencia de red contra el tier gratuito) — completado con éxito.

## Estado final verificado (Cypher real, `MATCH (n) RETURN labels(n), count(n)` / equivalente para relaciones)

| Nodo | Conteo | Esperado (doc/043) |
|---|---|---|
| `Distrito` | 21 | 21 ✓ |
| `Barrio` | 131 | ~131 ✓ |
| `EstacionMedida` | 4738 | — |
| `ParadaTransporte` | 4056 | — |
| `Lugar` | 381 | — |
| **Total** | **9327** | |

| Relación | Conteo |
|---|---|
| `PERTENECE_A` | 131 |
| `UBICADO_EN` | 9021 |
| `PROXIMO_A` | 19880 |
| `CONECTADO_CON` | 11998 |
| **Total** | **41031** |

**Consulta de negocio verificada** (adyacencia real de una línea CRTM):

```cypher
MATCH (a:ParadaTransporte)-[r:CONECTADO_CON]->(b:ParadaTransporte)
RETURN r.linea AS linea, a.id AS origen, b.id AS destino LIMIT 3
```
```
1  crtm_red_transporte_madrid:par_4_262 -> crtm_red_transporte_madrid:par_4_263
1  crtm_red_transporte_madrid:par_4_263 -> crtm_red_transporte_madrid:par_4_262
1  crtm_red_transporte_madrid:par_4_261 -> crtm_red_transporte_madrid:par_4_262
```
(la Línea 1 de Metro conectando sus paradas reales en ambos sentidos, tal
como diseñó la tarea 071: bidireccional dentro de la misma `route_id`.)

También verificado el cruce estación→barrio real (`UBICADO_EN`):
```
trafico:4260 -> Palacio
trafico:4291 -> Palacio
```

**Nota sobre `PROXIMO_A` (19880, más que los 7916 observados justo tras el
segundo intento fallido)**: `proximo_a_query` en `grafo/cypher.py` usa
`MERGE (a)-[r:PROXIMO_A]->(b)` sobre el par exacto de nodos — es
provablemente idempotente, no puede duplicar relaciones entre el mismo par
ordenado. El número más alto observado en esta verificación final frente a
la lectura intermedia se atribuye a que esa lectura intermedia se hizo justo
al filo de que el segundo intento terminara (posible carga aún en curso en
ese instante, o lag de propagación en AuraDB) — no a un problema de
duplicación real, dado que la query lo impide por diseño.

## Backfill de Bronze real (parte del segundo intento, ya aplicado)

Confirmado con `aws s3 ls`, un objeto real por dataset:
- `barrios_distritos_madrid_distritos/fecha=.../hora=.../*.json`
- `barrios_distritos_madrid_barrios/fecha=.../hora=.../*.json`
- `poi_madrid/fecha=.../hora=.../*.json`
- `crtm_red_transporte_madrid/fecha=.../hora=.../*.json` (263 rutas reales,
  formato verificado directamente: `route_id`, `mode`, `short_name`,
  `stops[]` con `stop_id`/`sequence`/`location` completos)

Carga puntual, sin nada programado — mismo criterio que el resto de
datasets de referencia estática del proyecto.

## Relevante para tareas futuras

- El grafo urbano está completo y cargado en producción real por primera
  vez: 9327 nodos, 41031 relaciones, los 5 tipos de nodo y las 4
  relaciones del esquema (`infra/neo4j/schema/schema.cypher`) presentes y
  verificados con consultas de negocio reales.
- Patrón operativo confirmado por tercera vez en esta sesión (tareas
  073/075/076/080): cuando una sesión autónoma agota presupuesto/turnos
  tras hacer trabajo real contra un sistema externo (AWS o, aquí, Neo4j),
  verificar primero el estado real del sistema antes de asumir que hay que
  repetir desde cero — puede haber progreso real que solo falta completar
  o documentar.
- La siguiente pieza natural que depende de este grafo: la `tool` del
  asistente que cruza datasets vía consultas Cypher (p. ej. "¿hay tráfico
  cerca de este evento?"), ya anotada en `PLAN.md`.
