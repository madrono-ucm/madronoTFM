# 082 — `trafico_cercano` verificada contra la instancia real de Neo4j

## Contexto

La tarea 081 implementó `trafico_cercano` (cruce grafo urbano en Neo4j +
Athena) y verificó la mitad Athena/Gold contra datos reales, pero no pudo
verificar la mitad Neo4j porque las 4 credenciales
(`/madrono-tfm/dev/secrets/neo4j-{uri,username,password,database}`) estaban
guardadas por error en `eu-south-2` en vez de en `eu-west-1` (bug de región
por defecto de esta EC2, ya corregido antes de esta tarea, no en su
alcance). Esta tarea parte de esa corrección ya hecha y solo necesitaba
verificar de extremo a extremo.

## Qué se hizo

1. **Credenciales**: obtenidas en tiempo de ejecución con
   `aws ssm get-parameter --region eu-west-1 --with-decryption` sobre las 4
   claves y exportadas como `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/
   `NEO4J_DATABASE` en el entorno del proceso — nunca escritas en el
   repositorio ni persistidas en disco más allá de un fichero temporal en
   `/tmp` con permisos `600`, borrado al terminar la sesión. Confirmado que
   ahora sí existen en `eu-west-1` (`aws ssm describe-parameters` las lista;
   antes de la corrección solo aparecían en `eu-south-2`).
2. **Conexión directa a Neo4j real** (sin FastAPI de por medio): el driver
   `neo4j` (5.28.4) conecta sin problemas contra `neo4j+s://...` con las
   credenciales de SSM. `MATCH (l:Lugar) RETURN l.nombre, l.id LIMIT 20`
   devolvió nodos reales (`aparcamientos:53 | Plaza de España`,
   `aparcamientos:9 | Paseo de Recoletos`, etc.) — confirma el estado
   cargado en la tarea 080.
3. **Servicio real levantado**: `uvicorn asistente.main:app` con las 4
   variables `NEO4J_*` más `AWS_DEFAULT_REGION=eu-west-1` (necesaria por el
   mismo motivo ya documentado en la tarea 079: el IMDS de esta EC2
   resuelve a `eu-south-2` por defecto). Arrancó sin errores, con el
   `StreamableHTTPSessionManager` del agente MCP iniciado correctamente
   (mismo patrón ya verificado en la tarea 079).
4. **Invocación real de `GET /trafico-cercano`** contra el servicio en
   marcha, con Neo4j y Athena reales (no mockeados) de punta a punta.

## Resultado real de la invocación

**Lugar consultado**: `Plaza de España` (nodo real `aparcamientos:53`,
confirmado antes por el listado de `:Lugar`), con `momento=2026-08-24T12:00:00+02:00`
(una hora con datos ya presentes en `gold.trafico_por_punto_hora`, ver nota
sobre `momento` por defecto más abajo).

```
GET /trafico-cercano?lugar=Plaza%20de%20España&momento=2026-08-24T12:00:00+02:00
```

```json
{
  "veredicto": "favorable",
  "fiabilidad": "media",
  "explicacion": "Tráfico cerca de «Plaza de España» a las 12:00: 23 estación(es) de tráfico a menos de 300m (la más cercana, 4286, a 36m) -- estado general: fluido.",
  "fuentes": [
    {
      "dataset": "neo4j: (:Lugar)-[:PROXIMO_A]-(:EstacionMedida {tipo: 'trafico'})",
      "resumen": "23 estación(es) de tráfico dentro de 300m de «Plaza de España»"
    },
    {
      "dataset": "gold.trafico_por_punto_hora",
      "resumen": "4286: intensidad 932.4, nivel de servicio 1.0 a las 12:00"
    }
  ]
}
```

23 estaciones de tráfico reales encontradas por el grafo dentro de 300m
(`trafico:4286` a 36m, `trafico:4284` a 49m, `trafico:4285` a 55m, ...),
cada una con datos reales de Gold para las 12:00 del 2026-08-24 (p.ej.
`4286`: 932.4 veh/h, ocupación 0.109, nivel de servicio 1.0). Confirma que
la consulta Cypher real (`MATCH (l:Lugar) ... MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida
{tipo: 'trafico'})`) y la consulta Athena real sobre
`gold.trafico_por_punto_hora` se combinan correctamente de extremo a
extremo, sin ningún mock.

También verificado con otros lugares reales (`Paseo de Recoletos`: 10
estaciones; `Fuencarral`: 19; `Olavide`: 9) y con un lugar inexistente
(`NoExisteEsteLugarXYZ`: 0 resultados, respuesta `sin_datos` sin excepción,
como diseñó la tarea 081).

## Nota: `momento` por defecto (ahora mismo) no encontró datos — no es un bug

La primera invocación probada usó el valor por defecto de `momento`
(instante actual). Devolvió `resumen="sin_datos"` pese a que el grafo sí
encontró 23 estaciones cercanas a "Plaza de España". Investigado: no es un
bug de conexión ni de la lógica de la tool, sino un desfase esperado entre
el reloj de esta EC2/Madrid (ya en `2026-08-25`, tras la medianoche) y la
última partición cargada en `gold.trafico_por_punto_hora`
(`SELECT date, COUNT(*) FROM trafico_por_punto_hora GROUP BY date ORDER BY
date DESC` → el máximo es `2026-08-24`, sin fila aún para `2026-08-25`,
día que recién empieza) — el pipeline incremental de Silver/Gold aún no ha
procesado el día en curso. Al pedir explícitamente `momento` dentro del
rango con datos (`2026-08-24T12:00:00+02:00`), la respuesta fue completa y
correcta (ver arriba). No se ha modificado ningún código para esto: es el
comportamiento esperado, ya documentado en la tarea 081 ("si Gold no tiene
fila para la hora resuelta, las estaciones se listan igualmente... con sus
campos en `None`" — aquí, como *ninguna* hora del día en curso tiene datos
todavía, el agregado de `resumen` cae a `"sin_datos"`, no por lugar/estación
no encontrados sino por ausencia total de Gold para la fecha).

## `asistente/neo4j_client.py`: sin bugs de conexión

El cliente conectó a la primera contra la instancia real (URI `neo4j+s://`,
autenticación, base de datos, todo correcto tal cual estaba escrito en la
tarea 081) — no hizo falta ningún cambio de código. `run_neo4j_query`,
`lugares_proximos_a_estaciones_trafico_query` y el driver cacheado con
`lru_cache` funcionan como estaba documentado. Los 32 tests existentes
(`python3 -m unittest discover -s asistente/tests -t .`) siguen en verde,
sin ninguna modificación.

## Restricciones respetadas

- Ninguna credencial de Neo4j se ha escrito en el repositorio ni en ningún
  fichero versionado — solo variables de entorno de proceso y un fichero
  temporal en `/tmp` con permisos `600`, borrado al terminar.
- No se ha modificado `asistente/mcp_agent/tools.py` ni
  `asistente/neo4j_client.py` (no se encontró ningún bug real de conexión
  que lo justificara).
- No se ha tocado `grafo/` ni `infra/terraform/`.
- El servicio local (`uvicorn`) se paró y no queda ningún proceso en
  segundo plano.

## Relevante para tareas futuras

- `trafico_cercano` queda verificada de extremo a extremo contra sistemas
  reales (Neo4j real + Athena real) por primera vez — ya no depende de
  mocks para confiar en su comportamiento en producción.
- Al probar `trafico_cercano` (o cualquier tool futura que dependa de Gold)
  con el `momento` por defecto ("ahora"), tener en cuenta que el día en
  curso puede no tener aún datos en Gold hasta que el pipeline incremental
  lo procese — no es un fallo de la tool, conviene probar explícitamente
  con un `momento` de un día ya completado si se quiere ver datos reales
  con seguridad.
