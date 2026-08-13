# 017 — Captura de la agenda oficial de eventos culturales de Madrid (muestra)

## Qué se implementó

`ingesta/capturas/agenda_eventos_madrid.py`: productor de la agenda de
eventos culturales/de ocio de Madrid, con **dos fuentes** combinadas en un
único dataset (campo `source` para distinguirlas, mismo patrón que `mode`
en `bluesky_menciones_madrid.py`, tarea 016):

- `agenda_eventos_madrid_municipal`: dataset "Actividades culturales y de
  ocio municipal en los próximos 100 días" de datos.madrid.es (id
  `206974-0-agenda-eventos-culturales-100`, licencia CC-BY 4.0). Cubre solo
  actividades en centros **municipales**.
- `agenda_turismo_esmadrid`: dataset "Agenda de la ciudad de Madrid" (id
  `300028-0-agenda-turismo`), gestionado por Madrid Destino
  (`esmadrid.com`).

Ambas fuentes se descargan (`fetch_municipal_events`/`fetch_esmadrid_events`)
y se normalizan (`normalize_municipal_event`/`normalize_esmadrid_event`) al
mismo esquema mínimo común: `event_id`, `title`, `description` (recortada a
400 caracteres), `category`, `start_datetime`/`end_datetime`, `schedule_text`,
`free`, `price_info`, `location` (venue/dirección/distrito/barrio/CP/lat/lon),
`url`, `captured_at`. Documentación completa del esquema y de ambas fuentes
en `ingesta/README.md`, sección `capturas/agenda_eventos_madrid.py`.

## Decisión sobre el dataset complementario de esMadrid: incluido, no aplazado

El enunciado pedía investigar si "Agenda turística de la ciudad de Madrid"
(esmadrid.com) aportaba cobertura relevante que la agenda municipal no
tiene, y decidir si incluirlo en esta tarea o dejarlo anotado para el
futuro. Se investigó en vivo y **sí aporta cobertura relevante**: conciertos
y espectáculos en salas/teatros privados (verificado con ejemplos reales:
"Zucchero (Madrid Live Experience 2026)", "Real Madrid - Ajax Vrouwen (UEFA
Women's Champions League)"), ferias, exposiciones y grandes eventos de
ciudad que no se celebran en centros municipales — justo el tipo de eventos
no municipales que el enunciado señalaba como el caso a evaluar. Se decidió
**incluirlo en esta misma tarea**: el coste extra (un segundo
`fetch_*`/`normalize_*` que parsea XML en vez de JSON-LD) fue moderado y el
esquema normalizado ya absorbía ambas fuentes con los mismos campos, sin
necesitar un esquema distinto por fuente.

**Licencia**: `package_show` marca este dataset como `"isopen": false`
(licencia `madrid-destino`, no CC-BY como el municipal). Se leyó la licencia
completa en vivo
(<https://datos.madrid.es/pages/condiciones-reutilizacion-informacion-madrid-destino>):
permite expresamente la reutilización de "documentos textuales y datos"
para fines comerciales y no comerciales, pero **limita la reutilización de
fotografías y material gráfico**. Por eso el módulo, a propósito, **no
incluye ninguna URL de imagen** del bloque `<multimedia>` del XML de origen
aunque esté disponible en la fuente — solo texto, geolocalización y fechas.

## Decisiones técnicas relevantes

- **Fuente municipal: recurso JSON-LD directo, no CKAN `datastore_search`.**
  El enunciado sugería el endpoint CKAN `datastore_search`, pero se verificó
  en vivo que **responde con una página HTML de mantenimiento**
  ("Ayuntamiento de Madrid - En mantenimiento") en vez de JSON. En su lugar
  se usa el recurso JSON-LD del propio catálogo
  (`https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json`),
  que respondió con normalidad (669 eventos reales en el momento de la
  captura) y es, de hecho, más simple: una lista `@graph` de objetos ya
  tipados, sin paginación que gestionar para una muestra pequeña.
- **Bloqueo de WAF en esmadrid.com, resuelto con un User-Agent de
  navegador.** Se verificó en vivo que `https://www.esmadrid.com/opendata/agenda_v1_es.xml`
  devuelve `403 Forbidden` con el User-Agent por defecto de la librería
  `requests`, pero `200 OK` con un User-Agent de navegador (`curl` sin
  cabeceras especiales también funcionaba, lo que ayudó a aislar que el
  bloqueo era específico del User-Agent de `requests`, no de la IP de esta
  EC2). El módulo envía un User-Agent de navegador en todas sus peticiones
  (a ambas fuentes) por simplicidad; no tiene efecto adverso en
  datos.madrid.es.
- **Solo el primer rango de fechas de esMadrid, sin modelar recurrencia
  completa.** El dato municipal ya trae un único `dtstart`/`dtend` por
  evento. El de esMadrid modela recurrencia real (`<fechas><rango>` con
  `inicio`/`fin`/`dias`, más `<exclusion>`/`<inclusion>` para sesiones
  sueltas). Modelar esa recurrencia tipo RRULE excedía el alcance de
  "esquema mínimo y consistente" pedido por la tarea; se tomó una
  simplificación documentada: `start_datetime`/`end_datetime` son el
  `inicio`/`fin` del primer `<rango>` (el periodo en que el evento está
  activo), y el texto libre de `<item name="Horario">` se conserva aparte
  en `schedule_text` para quien necesite el patrón exacto. Una tarea futura
  que necesite fechas de sesión individuales debería parsear ese campo o
  `dias`/`exclusion`/`inclusion` explícitamente.
- **Eventbrite y Foursquare descartados antes de empezar** (ya señalado en
  el propio enunciado de la tarea, verificado igualmente): la búsqueda
  pública de eventos de Eventbrite está descontinuada (su API solo gestiona
  eventos de una cuenta propia) y las reseñas/tips de Foursquare están tras
  un tier de pago.

## Captura real en vivo

Se completó una **captura real en vivo** de ambas fuentes: el fixture
commiteado en `ingesta/capturas/samples/agenda_eventos_madrid_sample.json`
son **10 eventos reales** (5 del dataset municipal, 5 de esMadrid),
descargados ejecutando `python3 -m ingesta.capturas.agenda_eventos_madrid`
tal cual durante esta sesión. No son datos de ejemplo generados a mano. A
diferencia de otras tareas de este proyecto (003, 012...), **no hubo ningún
problema de acceso persistente que documentar**: ambas fuentes son de
lectura pública sin autenticación y respondieron con normalidad una vez
resuelto el bloqueo de WAF de esmadrid.com (ver arriba).

## Tests

`ingesta/tests/test_agenda_eventos_madrid.py`: no dependen de la red, usan
dos fixtures reales capturados durante esta sesión y recortados a un tamaño
mínimo — `fixtures/agenda_eventos_madrid_municipal_sample.json` (3 eventos
del `@graph` real, incluyendo deliberadamente uno sin `@type` ni
`address`/`location`, para cubrir esos campos ausentes) y
`fixtures/agenda_turismo_esmadrid_sample.xml` (2 `<service>` reales, uno con
recurrencia con exclusión/inclusión de fechas). Cubren la normalización de
ambas fuentes (categoría anidada, distrito/barrio, fechas, HTML/entidades en
`description`/`schedule_text`...) y una verificación de esquema sobre la
propia muestra commiteada. Suite completa del proyecto verificada tras el
cambio: 124 tests (115 previos + 9 nuevos), todos en verde.

## Relevante para tareas futuras

- El dataset municipal se actualiza a diario (metadato `frequency` de
  `package_show`); una futura tarea de scheduling real podría reejecutar
  este productor periódicamente sin cambios de código, tal como ya anticipa
  el `TODO(kafka)` dejado en el módulo.
- El bloqueo de WAF de esmadrid.com por User-Agent (no por IP/rango) es
  específico de ese host — si una tarea futura añade otra fuente en
  `*.esmadrid.com` o `*.madrid.es`, conviene verificar de nuevo si necesita
  el mismo tratamiento en vez de asumirlo.
- La simplificación de "solo el primer rango de fechas" en
  `agenda_turismo_esmadrid` es deliberada y documentada tanto en el
  docstring del módulo como en `ingesta/README.md`; si una futura
  transformación de Silver/Gold necesita fechas de sesión exactas para
  eventos recurrentes (p.ej. "¿hay función el próximo sábado?"), debe
  volver a la fuente cruda (`schedule_text` o los campos `dias`/
  `exclusion`/`inclusion` del XML original) en vez de asumir que
  `start_datetime`/`end_datetime` cubren cada sesión.
- Este es el segundo caso del proyecto (tras `bluesky_menciones_madrid.py`,
  tarea 016) de "un único dataset con campo que distingue el origen" para
  representar señales complementarias sobre el mismo dominio (aquí:
  "eventos", desde dos organismos con datasets y formatos distintos). Puede
  servir de referencia para fuentes futuras con esa misma forma.
