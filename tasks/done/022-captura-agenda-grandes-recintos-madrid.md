---
id: 22
slug: captura-agenda-grandes-recintos-madrid
title: Captura de la agenda de grandes recintos de Madrid (deporte, conciertos, eventos)
  (muestra)
status: done
force: true
allow_infra_apply: false
branch: task/022-captura-agenda-grandes-recintos-madrid
pr_number: 69
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/69
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-13T17:23:43+00:00'
updated_at: '2026-08-14T04:08:45.578067+00:00'
started_at: '2026-08-14T03:52:33.374959+00:00'
submitted_at: '2026-08-14T04:07:38.310959+00:00'
merged_at: '2026-08-14T04:07:42Z'
---

## Contexto

Un partido en el Bernabéu o un concierto en el WiZink Center genera un pico de
afluencia enorme y conocido con antelación — justo el tipo de señal que permite a
Madroño avisar de que una zona va a estar colapsada y **recomendar planes
alternativos** (objetivo general del asistente, memoria apartado 6.7).

**Decisión de diseño (evita perseguir una fuente distinta por tipo de evento)**:
en vez de una API de fútbol + otra de conciertos + otra de boxeo, se captura **por
recinto**: cada gran recinto publica su propia agenda con todo lo que allí ocurre,
sea cual sea el tipo de evento. Esto cubre de una vez fútbol, baloncesto, tenis,
boxeo, hípica y grandes conciertos — incluidos eventos "virales" tipo La Velada del
Año, que se celebran precisamente en uno de estos recintos (el Cívitas
Metropolitano en sus últimas ediciones), sin necesitar una fuente aparte para
"eventos de influencer": la propia agenda del recinto ya lo recoge, y el ruido
social alrededor ya lo captura la tarea 016 (Bluesky).

Recintos a cubrir (investiga la agenda pública de cada uno; si alguno no publica
una agenda accesible sin scraping agresivo o requiere credenciales, documéntalo y
sigue con el resto en vez de bloquear toda la tarea):

- Estadio Santiago Bernabéu (Real Madrid)
- Estadio Cívitas Metropolitano (Atlético de Madrid)
- WiZink Center
- Movistar Arena (antiguo Palacio de Vistalegre)
- IFEMA Madrid (Feria de Madrid)
- Hipódromo de la Zarzuela
- Caja Mágica (Mutua Madrid Open y otros)

## Objetivo

Implementar la captura con **dos modos**, mismo patrón que la tarea 016:

1. **Programada (barrido general)**: recorre los recintos de la lista y captura su
   agenda de próximos eventos — pensada para ejecutarse a diario cuando exista
   scheduling (los calendarios de eventos se anuncian con semanas/meses de
   antelación y cambian poco de un día para otro).
2. **Bajo demanda**: consulta puntual de la agenda de un recinto concreto — la
   usará en el futuro el asistente cuando el usuario pregunte por una zona cercana
   a uno de estos recintos.

## Alcance concreto

1. Crea `ingesta/capturas/agenda_recintos_madrid.py` con:
   - `fetch_venue_agenda(venue_id)`: agenda de un recinto concreto (modo bajo
     demanda).
   - `sweep_all_venues()`: agenda de todos los recintos de la lista (modo
     programado).
   - Normaliza a un esquema mínimo y consistente (recinto, nombre del evento, tipo
     si se puede inferir —deporte/concierto/otro—, fecha/hora, aforo si el recinto
     lo publica).
2. Para cada recinto, investiga primero si existe una fuente estructurada
   (calendario `.ics`, JSON-LD `schema.org/Event`, API pública) antes de asumir
   scraping HTML bruto — prioriza siempre lo más estructurado y estable que
   encuentres.
3. Genera una muestra pequeña real (unos pocos eventos de al menos 2-3 recintos
   distintos) en `ingesta/capturas/samples/`.
4. Añade un test que no dependa de la red real.
5. Documenta en `ingesta/README.md`: qué fuente usaste para cada recinto y por qué,
   cuáles quedaron fuera (si alguno) y por qué.

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente en esta tarea — ambos
  modos se implementan y se prueban, no se despliegan.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2.
- Si algún recinto requiere credenciales o su única fuente es un scraping HTML
  frágil y agresivo, decide con criterio si merece la pena incluirlo o si es mejor
  documentarlo como pendiente — no todos los recintos tienen que quedar cubiertos
  en esta primera versión.

## Criterios de aceptación

- `fetch_venue_agenda` y `sweep_all_venues` funcionan contra fuentes reales para al
  menos 2-3 recintos.
- Muestra real commiteada, con el recinto de origen indicado en cada registro.
- `ingesta/README.md` documenta la fuente elegida por recinto y las decisiones de
  alcance.
