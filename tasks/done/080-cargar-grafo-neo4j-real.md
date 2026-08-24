---
id: 80
slug: cargar-grafo-neo4j-real
title: Completar la carga real del grafo urbano en Neo4j AuraDB Free
status: done
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 2
next_retry_at: null
last_error: null
created_at: '2026-08-24T20:30:00+00:00'
updated_at: '2026-08-24T22:10:00+00:00'
started_at: '2026-08-24T21:21:43.971454+00:00'
submitted_at: '2026-08-24T22:10:00+00:00'
merged_at: '2026-08-24T22:10:00+00:00'
---

## Contexto

**Un primer intento de esta tarea terminó sin comitear nada, pero sí
ejecutó `grafo/cargar_grafo.py` contra la instancia real de Neo4j** —
verificado directamente con el driver oficial `neo4j` (fuera de la sesión
de `claude`, con una consulta Cypher real):

```
EstacionMedida: 4738 nodos
ParadaTransporte: 681 nodos
Lugar: 26 nodos
Distrito: 0 nodos      <- falta
Barrio: 0 nodos        <- falta
TOTAL: 5445 nodos

PROXIMO_A: 4024 relaciones
PERTENECE_A: 0          <- falta
UBICADO_EN: 0            <- falta
CONECTADO_CON: 0          <- falta
```

**Causa raíz, ya diagnosticada, no la reinvestigues**: `grafo/extract.py`
lee `Distrito`/`Barrio` (`fetch_distritos_bronze`/`fetch_barrios_bronze`) y
las rutas CRTM (`fetch_paradas_crtm_bronze`) directamente del bucket Bronze
real en S3. Pero **estos tres datasets nunca se han subido al Bronze
real** — confirmado con `aws s3 ls` (0 objetos en
`s3://madrono-tfm-dev-bronze-222234418587/{barrios_distritos_madrid_distritos,
barrios_distritos_madrid_barrios,poi_madrid,crtm_red_transporte_madrid}/`).
El propio docstring de `_read_bronze_records` en `grafo/extract.py` ya
avisaba de esto ("caso real a fecha de esta tarea... solo se han capturado
como muestra local, nunca subidos al bucket Bronze real"), pero el primer
intento de esta tarea no lo tuvo en cuenta antes de ejecutar la carga.

Los productores correspondientes (`ingesta/capturas/barrios_distritos_madrid.py`,
`poi_madrid.py`, `crtm_red_transporte_madrid.py`) son de **carga puntual,
no programada** por diseño (documentado en su propio `--help`: "no admite
ejecución en bucle ni programada" — son datos de referencia que cambian muy
rara vez), y hoy solo escriben a fichero local (`capture_sample(...,
out_path)`), nunca a S3 — nunca se han conectado a `BronzeWriter`.

**Ya verificado, no lo repitas**: toda la carga de `grafo/cypher.py` usa
`MERGE` (no `CREATE`) sobre la clave única de cada label/relación —
**relanzar `grafo/cargar_grafo.py` completo es idempotente y seguro**, no
duplicará lo ya cargado (`EstacionMedida`/`ParadaTransporte`/`Lugar`/
`PROXIMO_A`).

Credenciales en SSM (`/madrono-tfm/dev/secrets/neo4j-{uri,username,password,database}`),
mismas que la tarea anterior — sigue sin hacer falta ningún cambio ahí.

**`force: false` deliberado**: sigue siendo la primera carga completa de
datos de producción en un sistema nuevo.

## Objetivo

Backfill puntual de los tres datasets de referencia estática al Bronze
real (una sola vez, sin programar nada), y completar la carga del grafo
relanzando `grafo/cargar_grafo.py`.

## Alcance concreto

1. **Backfill de Bronze real** (una sola vez, sin dejar nada programado —
   mismo criterio que cualquier tarea de captura de este proyecto sin
   infraestructura de scheduling detrás): para cada uno de
   `barrios_distritos_madrid` (distritos + barrios, dos datasets),
   `poi_madrid`, `crtm_red_transporte_madrid`, reutiliza las funciones
   `fetch_*`/`normalize_*` ya existentes en su módulo de `ingesta/capturas/`
   (no las reimplementes) para obtener los registros reales, y escríbelos al
   Bronze real con `ingesta.capturas.bronze.BronzeWriter("s3://madrono-tfm-dev-bronze-222234418587",
   "<dataset>")` — el mismo nombre de `dataset` que ya usa
   `grafo/extract.py::fetch_*_bronze` (`barrios_distritos_madrid_distritos`,
   `barrios_distritos_madrid_barrios`, `poi_madrid`,
   `crtm_red_transporte_madrid`).
2. Confirma con `aws s3 ls` que los 4 prefijos tienen ahora objetos reales.
3. Relanza `python3 -m grafo.cargar_grafo` completo (credenciales de SSM en
   tiempo de ejecución, como la tarea anterior) — es idempotente, no hace
   falta borrar nada antes.
4. Verifica con Cypher real que ahora existen `Distrito`/`Barrio` (con
   conteos coherentes con `doc/010` — 21 distritos, ~131 barrios) y las 4
   relaciones (`PERTENECE_A`, `UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`,
   todas con conteo > 0). Verifica también al menos una consulta de ejemplo
   con sentido de negocio (p. ej. el barrio al que pertenece una estación
   concreta, o paradas conectadas entre sí por una línea real de CRTM).
5. Documenta en `doc/080-cargar-grafo-neo4j-real.md` el diagnóstico
   completo (por qué faltaban esos nodos/relaciones), el backfill
   realizado, y los conteos finales reales de nodos/relaciones tras
   completar la carga.

## Restricciones

- El backfill de Bronze es una carga puntual, no dejes nada programado
  (cron, systemd timer, bucle) — mismo criterio que el resto de este
  proyecto para datos de referencia estática.
- NO modifiques `ingesta/capturas/{barrios_distritos_madrid,poi_madrid,
  crtm_red_transporte_madrid}.py` para añadirles soporte de `BronzeWriter`
  de forma permanente salvo que sea claramente la forma más simple de
  hacer el backfill — si lo haces, hazlo de forma consistente con el resto
  de `ingesta/` (mismo patrón que otros productores que sí escriben a
  Bronze) y documenta la decisión; si prefieres un script aparte de un
  solo uso, esa es una opción igual de válida.
- NO escribas ninguna credencial de Neo4j en el repositorio.
- NO modifiques la lógica de `grafo/nodos.py`/`relaciones.py`/`cypher.py`
  salvo que encuentres un error real al completar la carga.
- NO toques `infra/terraform/`.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/080-...md`, aunque el backfill o la carga no sean perfectos.

## Criterios de aceptación

- Los 4 prefijos de Bronze real tienen datos.
- El grafo tiene los 5 tipos de nodo (`Distrito`, `Barrio`,
  `EstacionMedida`, `ParadaTransporte`, `Lugar`) y las 4 relaciones
  cargados, verificado con Cypher real (conteos + al menos una consulta
  con sentido de negocio).
- `doc/080-cargar-grafo-neo4j-real.md` documenta el diagnóstico, el
  backfill, y los conteos finales reales.
- Hay un commit real con estos cambios.
