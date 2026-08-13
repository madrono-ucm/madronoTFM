---
id: 18
slug: captura-aemet-prevision-avisos
title: Captura de previsión meteorológica y avisos de AEMET (muestra)
status: in_progress
force: true
allow_infra_apply: false
branch: task/018-captura-aemet-prevision-avisos
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-13T17:23:43+00:00'
updated_at: '2026-08-13T22:23:14.065349+00:00'
started_at: '2026-08-13T22:23:14.065325+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 008 ya captura el tiempo **actual** en Madrid. Para que Madroño responda
bien a "¿voy esta noche?" hace falta además una **previsión** (no solo el presente)
y avisos de fenómenos adversos. AEMET OpenData (`opendata.aemet.es`) es la fuente
oficial española: API REST gratuita, requiere una API key gratis por email
(registro instantáneo en `opendata.aemet.es/centrodedescargas/altaUsuario`, sin
verificación compleja conocida — compruébalo tú mismo en esta tarea).

## Objetivo

Capturar una muestra pequeña de: (a) predicción por municipio para Madrid capital,
y (b) avisos de fenómenos meteorológicos adversos vigentes para Madrid.

## Alcance concreto

1. Regístrate para obtener una API key de AEMET OpenData (variable de entorno
   `AEMET_API_KEY`, nunca hardcodeada). Si el registro requiriera un paso manual no
   automatizable (verificación de correo sin buzón disponible en esta sesión, igual
   que bloqueó la tarea 003 con EMT), documenta el bloqueo en
   `doc/018-captura-aemet-prevision-avisos.md` y deja el código preparado con datos
   de ejemplo que seguirían exactamente el esquema real.
2. Crea `ingesta/capturas/aemet_prevision_avisos.py` con dos funciones:
   - `fetch_prediccion(municipio_code="28079")`: predicción diaria/horaria para
     Madrid capital (código INE `28079`).
   - `fetch_avisos()`: avisos vigentes para la provincia de Madrid.
   Normaliza ambos a esquemas mínimos y consistentes (municipio/zona, fecha de
   validez, temperatura/precipitación/viento previstos por la predicción; nivel de
   aviso — amarillo/naranja/rojo—, fenómeno, ámbito temporal para los avisos).
3. Genera una muestra pequeña real (unos pocos días de predicción, los avisos
   vigentes en el momento de la captura, aunque estén vacíos) en
   `ingesta/capturas/samples/`.
4. Añade un test que no dependa de la red real.
5. Documenta en `ingesta/README.md`: cómo obtener la API key, los dos esquemas, y
   la cadencia real de publicación que encuentres (investígala: ¿cuántas veces al
   día actualiza AEMET la predicción por municipio? documenta lo que encuentres).

## Restricciones

- NO dejes nada programado: sin cron, sin `--interval-seconds`. Captura puntual con
  muestra pequeña, como el resto.
- La API key se lee de variable de entorno, nunca hardcodeada ni commiteada.
- No implementes reintentos agresivos si AEMET da error de cuota — es un tier
  gratuito con límite; documenta el límite si lo encuentras.

## Criterios de aceptación

- Muestra real (o mock documentado si el registro quedó bloqueado) de predicción y
  avisos, commiteada como fixture.
- `ingesta/README.md` documenta ambos esquemas y la cadencia real de publicación
  encontrada — esto determinará el schedule final cuando exista scheduling.
