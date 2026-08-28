# FIL-08 — `cargar_grafo.py` resiliente a cortes de AuraDB Free

## Problema

`grafo/cypher.py::Neo4jLoader._run_all` ejecutaba **una `session.run()` por
nodo y por relación**, secuencial, en una única sesión larga. Con ~9500
nodos + ~67000 relaciones son decenas de miles de idas y vueltas de red al
free tier de AuraDB. El 28/8, en el cierre de `FIL_04` (añadir 203 parques
al grafo), la recarga completa falló **4 veces seguidas**:

- 3× `neo4j.exceptions.SessionExpired: Failed to read from defunct connection`
- 1× `neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information`

Una recarga que sí terminó ese día tardó **51 minutos** — no era fiable.

## Arreglo

`grafo/cypher.py`:

1. **`_to_unwind(query)`**: convierte una sentencia con parámetros `$x` en su
   forma por lotes `UNWIND $rows AS row <query con $x -> row.x>` (regex
   `\$([A-Za-z_]\w*)` -> `row.\1`; seguro aquí, ningún literal de cadena
   contiene `$`).
2. **`_run_all`** ahora agrupa las sentencias por texto (dentro de cada
   `load_*` son idénticas) y las ejecuta en **lotes `UNWIND` de 1000 filas**
   (`_BATCH_SIZE`) en vez de una por una. Con los índices de
   `schema.cypher` aplicados (tarea 094), cada `MERGE` por `id` dentro del
   lote es barato.
3. **`_ejecutar_lote`**: cada lote va en `session.execute_write(...)` (que
   ya reintenta errores transitorios a nivel de transacción) envuelto en un
   bucle externo de hasta `_MAX_REINTENTOS` (5) con backoff lineal y
   **reconexión del driver** (`_reconectar`) ante
   `SessionExpired`/`ServiceUnavailable`/`TransientError`. Los errores no
   transitorios (sintaxis Cypher, etc.) se propagan tal cual.

Sin cambios en `nodos.py`/`relaciones.py` ni en las funciones `*_query()`
(los tests de inspección de cadena siguen valiendo). `MERGE` sigue siendo
todo -> idempotente, una recarga a medias no corrompe nada.

## Tests

`grafo/tests/test_cypher.py` (99 pasan, +4):

- `ToUnwindTests`: la transformación `$x -> row.x` no toca literales.
- `RunAllBatchingTests`: `_run_all` agrupa por sentencia y trocea en lotes
  del tamaño esperado (2500 filas -> 1000/1000/500); ante un error
  transitorio simulado, reintenta y reconecta una vez.

## Recarga real de verificación (28/8)

`python -m grafo.cargar_grafo` contra la instancia real:

- **Duración: ~9 min** (14:30:11 → 14:39:29 UTC), `EXIT=0`. La versión
  anterior (una `session.run` por sentencia) había fallado **4 veces
  seguidas** ese mismo día con `SessionExpired`/`ServiceUnavailable`, y la
  única que terminó tardó 51 min.
- **Sin ningún corte de conexión** — el bucle de reintento/reconexión no
  llegó a activarse.
- **Resultado (Cypher real)**:
  - Total: 9633 nodos / 63118 relaciones (`PROXIMO_A` 50858, `UBICADO_EN`
    9323, `CONECTADO_CON` 11998, `PERTENECE_A` 131).
  - `MATCH (l:Lugar {tipo:"parque"}) RETURN count(l)` → **203**.
  - `...-[:PROXIMO_A]-(e) RETURN count(DISTINCT l)` → **199** (antes 0).
  - `...-[:UBICADO_EN]->(:Barrio)` → **203**.
  - Ejemplo real: "Parque Lineal de Palomeras" → estación de tráfico a 8 m.

Cierra `FIL_04` (relaciones de los parques). Desbloquea `FIL_06` parte 2.

## Nota

El `ImportError: sys.meta_path is None` que aparece al final del log es el
`__del__` del driver `neo4j` durante el apagado del intérprete — cosmético,
`EXIT=0`. No afecta a la carga.
