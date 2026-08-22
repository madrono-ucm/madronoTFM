---
id: 73
slug: limpieza-duplicados-trafico-bicimad
title: "URGENTE: limpiar los datos duplicados de trafico/bicimad en Silver/Gold"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-22T18:00:00+00:00"
updated_at: "2026-08-22T18:00:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

**Bug de calidad de datos real, confirmado con una consulta Athena real —
prioridad alta, justo detrás de la 072.** La tarea 072 arregló la lectura
incremental de `trafico`/`bicimad` (dejaba de reprocesar todo el histórico
en cada ejecución), pero **no limpió los datos que ya se habían duplicado
en Silver/Gold antes del arreglo**, porque el bug de duplicación se
descubrió después de que 072 se diera por completada.

**Diagnóstico**: antes del arreglo, cada ejecución de `*_bronze_to_silver`/
`*_silver_to_gold` reprocesaba y volvía a escribir con `mode("append")`
**todo** el histórico acumulado, sin ninguna comprobación de "esto ya está
procesado" — así que cada una de las ~47 ejecuciones históricas de cada job
volvió a escribir (casi) todo lo que ya había. Confirmado con una consulta
SQL real contra Athena:

```sql
SELECT point_id, measured_at, COUNT(*) AS n
FROM trafico WHERE fecha='2026-08-15'
GROUP BY point_id, measured_at ORDER BY n DESC LIMIT 5
-- point_id=5524, measured_at=2026-08-15T11:50:14+00:00 -> n = 88
```

Y por número de ficheros (Bronze vs Silver, mismo periodo):

| Dataset | Objetos Bronze | Objetos Silver | Ratio |
|---|---|---|---|
| `trafico` | 2.242 | 36.873 | 16,4× |
| `bicimad` | 2.242 | 117.776 | 52,5× |

Los registros más antiguos están duplicados hasta ~47 veces (una vez por
cada ejecución histórica que reprocesó todo el histórico). Cualquier
`COUNT`/suma/agregación por volumen calculada hasta ahora sobre
`silver.trafico`, `silver.bicimad`, `gold.trafico_por_punto_hora` o
`gold.bicimad_por_estacion_hora` está inflada — no es fiable.

**Bronze no está afectado** (es el crudo, solo se lee, nunca se
sobrescribe) — la limpieza es exclusivamente sobre Silver/Gold de estos dos
datasets, y se puede reconstruir de cero desde Bronze sin perder nada.

**`force: false` deliberado**: borra y reescribe datos de producción reales
— quiero revisar el resultado antes de fusionar.

## Objetivo

Vaciar Silver/Gold de `trafico`/`bicimad` y reconstruirlos desde Bronze
**una sola vez, de forma limpia y deduplicada**, usando ya la lectura
incremental corregida de la tarea 072 para las ejecuciones futuras (no para
esta reconstrucción única, que necesariamente sí debe leer todo Bronze una
vez, correctamente, sin duplicar).

## Alcance concreto

1. Decide e implementa el mecanismo de reconstrucción limpia. Dos opciones
   razonables (elige una, documenta por qué):
   - **(a) Borrar y reprocesar histórico completo una vez**: vacía
     `s3://madrono-tfm-dev-{silver,gold}-.../{trafico,bicimad}*` (con `aws
     s3 rm --recursive`, revisa el prefijo exacto de cada tabla) y ejecuta
     un job (puntual, no el de producción incremental) que procese **todo**
     Bronze de una vez pero escribiendo cada registro **una sola vez**
     (agrupa/deduplica por la clave natural del registro —
     `point_id`+`measured_at` para tráfico, `station_id`+`measured_at` para
     BiciMAD — antes de escribir, o usa `dropDuplicates()` de Spark sobre
     esas columnas).
   - **(b) Deduplicar in situ**: si prefieres no borrar y reprocesar,
     reescribe Silver/Gold aplicando una deduplicación (leer todo,
     `dropDuplicates()`, sobreescribir con `mode("overwrite")`) — más
     simple si el volumen ya no es excesivo tras acotar a estos dos
     datasets, pero revisa que no se dispare el mismo problema de coste que
     motivó la 072 (una lectura completa puntual, una sola vez, está bien;
     el problema era que se repitiera cada hora).
2. Verifica el resultado con la misma consulta Athena del diagnóstico
   (arriba) — debe devolver `n=1` para cualquier combinación
   `point_id`+`measured_at` (o `station_id`+`measured_at`), no más.
3. Confirma que el número de registros tras la limpieza es coherente con el
   volumen real esperado (aprox. nº de objetos Bronze × registros por
   objeto — puedes verificarlo con una muestra), no con el número inflado
   que reportó la tarea 066.
4. Documenta en `doc/073-limpieza-duplicados-trafico-bicimad.md` el
   diagnóstico, el mecanismo de limpieza elegido y por qué, y la
   verificación (antes/después, con números reales).

## Restricciones

- Alcance: solo `trafico`/`bicimad` — el resto de datasets del grupo
  horario/diario puede tener el mismo problema, pero se limpia en las
  tareas 074/075 respectivamente cuando les toque, no lo adelantes aquí.
- NO toques Bronze — es el crudo, no está duplicado, no se toca.
- NO reviertas ni toques el arreglo de lectura incremental de la tarea 072
  (los triggers de `trafico`/`bicimad` ya están reactivados con el código
  correcto — esta tarea es solo sobre los datos históricos ya escritos, no
  sobre el pipeline en marcha).
- Si el proceso de reconstrucción de esta tarea vuelve a disparar un coste
  alto de Glue, es esperable (es una lectura completa de todo el
  histórico, pero una única vez, no recurrente) — documenta el coste real
  de esta limpieza puntual.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/073-...md`.

## Criterios de aceptación

- Silver/Gold de `trafico`/`bicimad` no tiene registros duplicados,
  verificado con una consulta Athena real (mismo tipo que el diagnóstico).
- El volumen de datos tras la limpieza es coherente con el histórico real
  de Bronze, no inflado.
- `doc/073-limpieza-duplicados-trafico-bicimad.md` documenta el
  diagnóstico, el mecanismo elegido, y la verificación con números reales.
- Hay un commit real con estos cambios.
