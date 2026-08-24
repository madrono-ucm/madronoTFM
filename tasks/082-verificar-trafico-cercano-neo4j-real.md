---
id: 82
slug: verificar-trafico-cercano-neo4j-real
title: Verificar trafico_cercano contra la instancia real de Neo4j (bug de región
  en SSM corregido)
status: in_progress
force: true
allow_infra_apply: false
branch: task/082-verificar-trafico-cercano-neo4j-real
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-25T10:00:00+00:00'
updated_at: '2026-08-24T22:29:49.573226+00:00'
started_at: '2026-08-24T22:29:49.573202+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 081 implementó `trafico_cercano` (cruce grafo + Athena) y verificó
la mitad Athena/Gold contra datos reales, pero **no pudo verificar la mitad
Neo4j**: buscó las credenciales en SSM (`eu-west-1`, región real del
proyecto) y no las encontró — correctamente, porque no estaban ahí.

**Causa raíz, ya corregida, no la reinvestigues**: al guardar las 4
credenciales de Neo4j en SSM (antes de la tarea 080), se ejecutó
`aws ssm put-parameter` sin `--region` explícito, y esta EC2 tiene un
fallback de región por defecto a `eu-south-2` (bug ya documentado en
sesiones anteriores del proyecto) — así que las 4 credenciales quedaron
guardadas en `eu-south-2`, no en `eu-west-1` donde vive el resto de
secretos del proyecto (`aemet-api-key`, `cams-ads-api-key`, etc.) y donde
la tarea 080 sí las encontró y usó con éxito (esa tarea, al ejecutarse,
aparentemente sí usó/heredó el contexto de región correcto en su momento,
o las credenciales se pasaron de otra forma — no relevante ahora).

**Ya corregido, verificado, no lo repitas**: las 4 credenciales
(`/madrono-tfm/dev/secrets/neo4j-{uri,username,password,database}`) están
ahora en `eu-west-1` (confirmado con `aws ssm get-parameter
--region eu-west-1 --with-decryption` sobre las 4, valores correctos), y
se han borrado las copias duplicadas de `eu-south-2`.

## Objetivo

Verificar `trafico_cercano` de extremo a extremo contra la instancia real
de Neo4j, ahora que las credenciales están accesibles en la región
correcta.

## Alcance concreto

1. Obtén las 4 credenciales de SSM en `eu-west-1` en tiempo de ejecución
   (`aws ssm get-parameter --region eu-west-1 --with-decryption`, o
   `boto3` equivalente con `region_name="eu-west-1"` explícito — no
   dependas del default de región de esta EC2) y expórtalas como
   `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE`.
2. Arranca el servicio del asistente localmente y consulta
   `trafico_cercano` (vía el router HTTP de la tarea 081, o directamente la
   `tool`) con un lugar real ya cargado en el grafo — antes de elegirlo,
   consulta `MATCH (l:Lugar) RETURN l.nombre, l.id LIMIT 20` contra la
   instancia real para confirmar un nombre existente.
3. Confirma que la respuesta combina de verdad una consulta Cypher real
   (nodos `:Lugar`/`:EstacionMedida` y relación `PROXIMO_A` reales, no
   mockeados) con el dato real de Athena ya verificado en la tarea 081.
4. Si `asistente/neo4j_client.py` tiene algún problema real al conectar
   contra la instancia real (más allá del bug de región ya corregido),
   arréglalo y documenta qué era.
5. Documenta en `doc/082-verificar-trafico-cercano-neo4j-real.md` el
   resultado real de la invocación (lugar consultado, estaciones
   encontradas, distancias, datos de tráfico).

## Restricciones

- NO escribas ninguna credencial de Neo4j en el repositorio.
- NO modifiques la lógica de `trafico_cercano`/`neo4j_client.py` salvo que
  encuentres un bug real al conectar contra la instancia real.
- NO toques `grafo/` ni `infra/terraform/`.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/082-...md`.

## Criterios de aceptación

- `trafico_cercano` verificado con al menos una invocación real contra la
  instancia real de Neo4j (no mockeada) y contra Athena real.
- `doc/082-verificar-trafico-cercano-neo4j-real.md` documenta el resultado
  real.
- Hay un commit real con estos cambios.
