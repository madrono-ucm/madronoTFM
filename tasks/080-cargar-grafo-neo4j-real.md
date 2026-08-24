---
id: 80
slug: cargar-grafo-neo4j-real
title: "Primera carga real del grafo urbano en Neo4j AuraDB Free"
status: pending
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-24T20:30:00+00:00"
updated_at: "2026-08-24T20:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

El alta manual de AuraDB Free bloqueada desde la tarea 043 ya está resuelta
— existe una instancia real. Sus credenciales están en SSM Parameter Store
(`SecureString`, mismo patrón que `EMT_CLIENT_ID`/`AEMET_API_KEY`/
`CAMS_ADS_API_KEY`):

- `/madrono-tfm/dev/secrets/neo4j-uri`
- `/madrono-tfm/dev/secrets/neo4j-username`
- `/madrono-tfm/dev/secrets/neo4j-password`
- `/madrono-tfm/dev/secrets/neo4j-database`

**Ya verificado fuera de esta tarea, no lo repitas**: conexión real
establecida con el driver oficial `neo4j` (paquete PyPI), `verify_connectivity()`
correcto, una consulta Cypher real (`RETURN 1`) ejecutada con éxito contra la
base de datos real (no la default `neo4j` — la instancia usa un nombre de
base de datos propio, tómalo de `/madrono-tfm/dev/secrets/neo4j-database`,
no asumas `"neo4j"`). La base de datos está vacía (0 nodos) — instancia
recién creada.

`grafo/cargar_grafo.py` (tareas 067-071) ya está escrito, testado, y lee
Silver/Gold vía Athena / Bronze vía S3 con datos reales — no necesita
ningún cambio de lógica, solo ejecutarse. Su función `main()` ya lee
`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE` de variables
de entorno.

**`force: false` deliberado**: primera carga real de datos de producción en
un sistema nuevo — quiero revisar el resultado antes de fusionar.

## Objetivo

Ejecutar `grafo/cargar_grafo.py` contra la instancia real, con las
credenciales obtenidas de SSM en tiempo de ejecución (nunca hardcodeadas ni
commiteadas), y verificar con consultas Cypher reales que el grafo quedó
cargado correctamente.

## Alcance concreto

1. Instala el driver oficial `neo4j` (paquete PyPI) si no está ya
   disponible en este entorno — añádelo a `grafo/requirements.txt` si no
   está ya (revísalo, puede que ya se declarara en una tarea anterior sin
   haberse instalado).
2. Obtén las 4 credenciales de SSM en tiempo de ejecución
   (`aws ssm get-parameter --with-decryption`, o `boto3` equivalente) y
   expórtalas como las variables de entorno que espera
   `grafo/cargar_grafo.py::main()` — no las escribas en ningún fichero del
   repositorio.
3. Ejecuta `python3 -m grafo.cargar_grafo` contra la instancia real.
4. Verifica con consultas Cypher reales (vía el driver, o `cypher-shell` si
   está disponible) que:
   - Existen nodos de los 4 tipos (`:Distrito`, `:Barrio`, `:Lugar`,
     `:EstacionMedida`, `:ParadaTransporte` — revisa el esquema exacto en
     `infra/neo4j/schema/schema.cypher` si el nombre no coincide
     literalmente), con un conteo por tipo.
   - Existen relaciones de los 4 tipos (`PERTENECE_A`, `UBICADO_EN`,
     `PROXIMO_A`, `CONECTADO_CON`), con un conteo por tipo.
   - Al menos una consulta de ejemplo con sentido de negocio funciona (p.ej.
     "estaciones de medida a menos de 300m de un lugar conocido", o el
     barrio al que pertenece una estación concreta) — no solo conteos.
5. Documenta en `doc/080-cargar-grafo-neo4j-real.md` los conteos reales por
   tipo de nodo/relación, el resultado de la consulta de ejemplo, y
   cualquier discrepancia entre lo esperado (según el diseño de las tareas
   067-071) y lo real.

## Restricciones

- NO escribas ninguna credencial de Neo4j en el repositorio, ni siquiera
  temporalmente en un fichero commiteado — solo variables de entorno en el
  proceso de esta sesión.
- NO modifiques la lógica de `grafo/nodos.py`/`relaciones.py`/`cypher.py`/
  `extract.py` salvo que encuentres un error real al ejecutar contra la
  instancia real — si lo haces, documenta por qué.
- NO toques `infra/terraform/` — no hay ningún recurso Terraform para Neo4j
  (SaaS externo a AWS, ver `doc/043-grafo-neo4j.md`).
- Si la carga falla a medias, no la reintentes más de una vez sin entender
  la causa — documenta el error exacto, sería una tarea de seguimiento.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/080-...md`, aunque la carga no haya sido perfecta.

## Criterios de aceptación

- El grafo tiene nodos y relaciones reales cargados en la instancia real de
  AuraDB Free, verificado con consultas Cypher reales (conteos + al menos
  una consulta con sentido de negocio).
- `doc/080-cargar-grafo-neo4j-real.md` documenta los resultados reales.
- Hay un commit real con estos cambios.
