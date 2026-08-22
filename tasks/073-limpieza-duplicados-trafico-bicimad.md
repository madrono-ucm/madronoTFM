---
id: 73
slug: limpieza-duplicados-trafico-bicimad
title: 'URGENTE: limpiar los datos duplicados de bicimad en Silver/Gold (trafico ya
  está arreglado)'
status: in_progress
force: false
allow_infra_apply: true
branch: task/073-limpieza-duplicados-trafico-bicimad
pr_number: null
pr_url: null
attempts: 1
next_retry_at: '2026-08-22T21:09:25.421654+00:00'
last_error: You've hit your session limit · resets 9:10pm (UTC)
created_at: '2026-08-22T18:00:00+00:00'
updated_at: '2026-08-22T21:10:25.646786+00:00'
started_at: '2026-08-22T21:01:52.271006+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Tres intentos previos de esta tarea han terminado sin comitear nada.**
Cada uno dejó progreso real (verificado manualmente fuera de la sesión de
`claude`, con `aws s3 ls` y consultas Athena reales) — **no repitas trabajo
ya hecho**:

- **`trafico` (Silver + Gold): COMPLETO Y VERIFICADO.** Silver:
  `fecha=2026-08-15` a `2026-08-22`, 6.768 objetos, Athena confirma `n=1`
  sin duplicados. Gold: `date=2026-08-15` a `2026-08-22`, 112 objetos,
  datos reales. **No toques `trafico` en esta tarea — ya está cerrado.**
- **`bicimad`: sigue masivamente duplicado, pese a un intento de limpieza
  parcial.** Silver tiene ahora 65.658 objetos (bajó de 117.808, alguna
  compactación ocurrió) pero una consulta Athena real confirma que **sigue
  duplicado**: `station_id=2302`, `measured_at=2026-08-19T03:01:54+02:00`
  aparece **9.768 veces**. La compactación redujo el número de ficheros sin
  deduplicar el contenido — probablemente una reescritura/repartition sin
  `dropDuplicates()` real, o con la clave equivocada. Gold de `bicimad`
  tiene 498 objetos, casi seguro calculado sobre este Silver todavía sucio.

Bronze no está afectado (nunca se sobrescribe, `bicimad` tiene 2.249
objetos intactos).

**Esta es la última pieza que falta de esta serie de tareas — alcance
reducido al mínimo posible para intentar cerrarlo esta vez.**

**`force: false` deliberado**: borra y reescribe datos de producción reales.

## Objetivo

Limpiar Silver y Gold de `bicimad` (solo este dataset) desde cero, de forma
deduplicada, y verificarlo.

## Alcance concreto — sigue estos pasos en este orden exacto

1. Borra con `aws s3 rm --recursive` **todo** el contenido de:
   - `s3://madrono-tfm-dev-silver-222234418587/bicimad/`
   - `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`
2. Reconstruye Silver leyendo **todo** Bronze de `bicimad` (2.249 objetos)
   de una vez, aplicando
   `.dropDuplicates(["station_id", "measured_at"])` **inmediatamente
   después de construir el DataFrame de Silver, antes de escribirlo** — no
   despliegues esta lectura completa como cambio permanente del job de
   producción (que ya está incremental desde la tarea 072), esto es una
   ejecución puntual de reconstrucción.
3. Verifica el resultado de Silver **antes de seguir con Gold** con esta
   consulta Athena exacta:
   ```sql
   SELECT station_id, measured_at, COUNT(*) AS n
   FROM bicimad GROUP BY station_id, measured_at ORDER BY n DESC LIMIT 5
   ```
   El resultado de `n` en la primera fila debe ser `1`. **Si no lo es, no
   sigas con Gold** — revisa por qué la deduplicación no funcionó (¿la
   clave es la correcta? ¿el DataFrame que se escribió es el
   deduplicado o el original?) antes de continuar.
4. Solo si el paso 3 confirma `n=1`: reconstruye Gold desde ese Silver ya
   limpio (agregación normal, sin deduplicar de nuevo, ya no hace falta).
5. Verifica que las fechas de Silver/Gold cubren el mismo rango que Bronze,
   sin huecos.
6. Documenta en `doc/073-limpieza-duplicados-trafico-bicimad.md`: resumen
   de los tres intentos previos (una tabla corta basta, no hace falta
   repetir toda la narrativa), qué hiciste en esta sesión, y la
   verificación final con números reales.

## Restricciones

- Alcance: **solo `bicimad`** — `trafico` ya está cerrado, no lo toques.
- NO toques Bronze.
- NO reviertas ni toques el arreglo de lectura incremental de la tarea 072
  ni sus triggers.
- **Comitea el documento en cuanto termines el paso 3 (verificación de
  Silver), aunque no te dé tiempo a Gold** — así, si esta sesión también se
  queda sin tiempo, al menos queda registrado con certeza si Silver quedó
  bien o mal, en vez de tener que volver a investigarlo manualmente por
  cuarta vez. Si llegas a Gold, actualiza el mismo commit o añade otro.

## Criterios de aceptación

- Silver de `bicimad` sin duplicados, verificado con la consulta Athena
  exacta de arriba (`n=1`).
- Gold de `bicimad` reconstruido desde ese Silver limpio, con fechas sin
  huecos respecto a Bronze.
- `doc/073-limpieza-duplicados-trafico-bicimad.md` documenta el resultado
  final de toda la serie (trafico + bicimad) con números reales.
- Hay un commit real con estos cambios.
