# FIL-18 — Test de integración end-to-end

Hay ~900 tests unitarios pero ninguno recorría el sistema entero. `FIL_18`
añade `tests/integracion/test_e2e_bronze_a_asistente.py`: demuestra que un
registro Bronze acaba siendo una respuesta coherente del asistente, y falla
si se rompe cualquier eslabón.

## La cadena

```
fixture Bronze (inline, realista)
  → procesamiento.silver_gold.<ds>.transform.bronze_to_silver     (puerta de calidad)
  → procesamiento.silver_gold.<ds>.aggregate.aggregate_silver_to_gold
  → _aplanar_gold_<ds>()   (réplica de la proyección .select() del job de Glue)
  → GoldAthenaDouble       (parsea el WHERE de la tool y sirve las filas Gold)
  → [tráfico] Neo4jGraphDouble   (sub-grafo estación ↔ lugar en memoria)
  → tool del asistente
  → aserción
```

Dos datasets / tres tools:

| Dataset | Tool(s) | Qué comprueba |
|---|---|---|
| `calidad_aire` (horario, sin `geo.py`) | `calidad_aire`, `calidad_aire_prevista` | agregación por estación/contaminante/hora, selección de peor caso, clasificación del índice; y que la previsión ONNX se construye desde esas mismas features |
| `trafico` (horario, cruza el grafo) | `trafico_cercano` | resolución `:Lugar`→`:EstacionMedida` por el grafo + join con Gold por `point_id`, filtro por radio |

## Casos

1. **`calidad_aire` Bronze→respuesta**: 31 lecturas horarias de NO2 →
   `contaminante_principal == "NO2"`, `valor` == la media exacta de la hora
   pedida (60 µg/m³), estación en `estaciones_consultadas`, índice
   clasificado.
2. **Puerta de calidad**: una lectura de PM10 con valor negativo →
   `validate_record` la rechaza (`value_negative`) → no hay ninguna fila
   Gold de PM10 → la tool nunca la reporta.
3. **Previsión desde ONNX**: la misma cadena alimenta
   `calidad_aire_prevista` → `disponible`, `valor_previsto` real,
   `data_completeness ≥ 0.8`, `momento_objetivo == momento + horizonte`.
4. **Tráfico cruzando el grafo**: 26 lecturas + 1 de sensor en error
   (rechazada) → el `Neo4jGraphDouble` resuelve `retiro`→`trafico:3001` a
   80 m → `trafico_cercano` devuelve esa estación con su `avg_service_level`
   real y un `resumen` clasificado.
5. **Radio**: la misma estación a 500 m con `radio_m=300` → `sin_datos`.
6. **Eslabón roto** (guardia del propio test): si se sirven filas *Silver*
   sin pasar por `aggregate_silver_to_gold` (sin `avg_value`), la tool cae a
   `indice_calidad == "sin_datos"` — es decir, saltarse un paso de la
   cadena se detecta.

## Qué NO cubre

- **Runtime Spark real** de los jobs de Glue: se usa la lógica Python pura
  equivalente (`transform.py`/`aggregate.py`), que es el proxy ya testeado
  del proyecto (ver `procesamiento/README.md`, "Por qué Python puro para la
  lógica"). El `.select()`/cast de Spark se sustituye por `_aplanar_gold_*`.
- **Athena y Neo4j reales**: dobles en memoria. Las tools sí se verifican en
  vivo por separado (`doc/ML-09`, `doc/FIL-13`, tarea 081).
- **Ingesta** (`ingesta/capturas/*`): la fixture arranca en Bronze ya
  normalizado.

Eso queda como verificación manual / §7.5.

## CI

Se añadió `tests/` al `pytest` del job `tests` en `.github/workflows/ci.yml`
(antes: `ingesta/ procesamiento/ grafo/ asistente/ herramientas/ modelado/`).
6 casos, ~0.5 s.
