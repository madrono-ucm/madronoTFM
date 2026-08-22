---
id: 73
slug: limpieza-duplicados-trafico-bicimad
title: 'URGENTE: limpiar los datos duplicados de trafico/bicimad en Silver/Gold'
status: failed
force: false
allow_infra_apply: true
branch: task/073-limpieza-duplicados-trafico-bicimad
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: claude finalizó sin crear ningún commit
created_at: '2026-08-22T18:00:00+00:00'
updated_at: '2026-08-22T17:33:52.133501+00:00'
started_at: '2026-08-22T17:23:25.844322+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Un primer intento de esta tarea dejó los datos en un estado peor que
antes de empezar, y terminó sin comitear nada.** Verificado manualmente
fuera de la sesión de `claude` (con `aws s3 ls` y consultas Athena reales,
ya que el runner del agente no conserva la salida completa de un intento
que termina sin commits):

- Empezó a borrar Silver de `trafico`: **faltan por completo las
  particiones `fecha=2026-08-15` a `fecha=2026-08-19`** (solo quedan
  `2026-08-20`, `2026-08-21`, `2026-08-22`) — el número de ficheros bajó de
  36.873 a 4.027, pero no por deduplicación limpia, sino porque se borró una
  parte y nunca se reconstruyó.
- Las particiones que sí quedan **siguen masivamente duplicadas**:
  `fecha=2026-08-20` tiene 24.167.740 filas pero solo 533.294 combinaciones
  distintas de `point_id`+`measured_at` (ratio 45×); `fecha=2026-08-21`,
  10.579.951 filas vs 643.675 distintas (ratio 16×).
- **Gold de `trafico` no se tocó**: sigue teniendo las 9 particiones de
  fecha (`2026-08-14` a `2026-08-22`) con las agregaciones viejas
  (calculadas sobre el Silver duplicado, y ahora además huérfanas para los
  días que ya no existen en Silver).
- **`bicimad` no se tocó en absoluto** — sigue exactamente como antes (Silver
  con 117.808 ficheros, mismo problema sin arreglar).

**No intentes entender ni continuar el estado a medias del intento
anterior — es más simple y más seguro partir de cero.** Bronze no está
afectado (nunca se sobrescribe, sigue con sus 2.249 objetos intactos para
cada dataset) — toda la reconstrucción parte de ahí.

**`force: false` deliberado**: borra y reescribe datos de producción reales
— quiero revisar el resultado antes de fusionar.

## Objetivo

Borrar **por completo** Silver y Gold de `trafico`/`bicimad` (todas las
fechas, no solo las duplicadas) y reconstruirlos desde Bronze **una sola
vez, de forma limpia y deduplicada, hasta completar las dos reconstrucciones
enteras** — no dejes ninguna a medias otra vez.

## Alcance concreto

1. Borra con `aws s3 rm --recursive` **todo** el contenido de:
   - `s3://madrono-tfm-dev-silver-222234418587/trafico/`
   - `s3://madrono-tfm-dev-gold-222234418587/trafico_por_punto_hora/`
   - `s3://madrono-tfm-dev-silver-222234418587/bicimad/`
   - `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`
   (revisa el nombre exacto del prefijo Gold de cada uno en `glue.tf` si no
   coincide literalmente).
2. Reconstruye cada uno con un job puntual (no el de producción incremental
   de la tarea 072, que solo procesa la partición de una hora) que lea
   **todo** Bronze de una vez y escriba Silver deduplicado — usa
   `dropDuplicates(["point_id", "measured_at"])` para tráfico,
   `dropDuplicates(["station_id", "measured_at"])` para BiciMAD, antes de
   escribir. Puedes lanzar esto como una ejecución puntual de
   `aws glue start-job-run` sobre el job de producción pasándole como
   `--bronze_path` la raíz completa del dataset en vez de una partición
   concreta (revisa qué argumento espera tras el arreglo de la tarea 072),
   o como un script ad-hoc — elige lo más simple y documenta por qué.
3. Repite el mismo proceso para Silver→Gold (dedup + reconstrucción
   completa desde el Silver ya limpio).
4. **No des la tarea por completa hasta que los CUATRO borrados+
   reconstrucciones (Silver y Gold de trafico y de bicimad) estén
   terminados** — si el presupuesto no llega para los cuatro, prioriza
   terminar uno completo (borrado + reconstrucción + verificación) antes de
   empezar el siguiente, en vez de dejar varios a medias. Un solo dataset
   arreglado del todo es mucho mejor resultado que los cuatro a medias.
5. Verifica cada uno con una consulta Athena real tipo:
   ```sql
   SELECT point_id, measured_at, COUNT(*) AS n
   FROM trafico GROUP BY point_id, measured_at ORDER BY n DESC LIMIT 5
   ```
   (equivalente para `bicimad` con `station_id`) — debe devolver `n=1` en
   la fila con más duplicados, no más. Verifica también que las fechas
   presentes en Silver cubren el mismo rango que Bronze (sin huecos).
6. Documenta en `doc/073-limpieza-duplicados-trafico-bicimad.md` el
   diagnóstico completo (incluido lo que dejó a medias el intento anterior),
   el mecanismo de limpieza elegido, y la verificación (antes/después, con
   números reales) — para cada uno de los cuatro (Silver/Gold ×
   trafico/bicimad) que llegues a completar.

## Restricciones

- Alcance: solo `trafico`/`bicimad` — el resto de datasets se limpia en las
  tareas 074/075 cuando les toque.
- NO toques Bronze.
- NO reviertas ni toques el arreglo de lectura incremental de la tarea 072
  ni sus triggers — esta tarea es solo sobre los datos históricos.
- Si el coste de Glue de esta reconstrucción puntual resulta alto, es
  esperable (lee todo el histórico una vez) — documéntalo, no es motivo
  para dejarlo a medias.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/073-...md`, documentando exactamente qué de los cuatro completaste y
  qué quedó pendiente si no llegaste a los cuatro — un resultado parcial
  pero limpio y documentado es muchísimo mejor que lo que dejó el intento
  anterior (a medias y sin documentar).

## Criterios de aceptación

- Para cada dataset que completes: Silver/Gold sin registros duplicados
  (verificado con Athena) y sin huecos de fecha respecto a Bronze.
- Si no completas los cuatro, el documento dice exactamente cuáles sí y
  cuáles no, con el estado real de cada uno (no "en progreso" ambiguo).
- `doc/073-limpieza-duplicados-trafico-bicimad.md` documenta todo lo
  anterior con números reales.
- Hay un commit real con estos cambios.
