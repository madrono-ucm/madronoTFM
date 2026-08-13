---
id: 19
slug: captura-cams-calidad-aire-prevista
title: Captura de calidad del aire prevista y validada (Copernicus CAMS) (muestra)
status: in_progress
force: true
allow_infra_apply: false
branch: task/019-captura-cams-calidad-aire-prevista
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-13T17:23:43+00:00'
updated_at: '2026-08-13T22:36:46.935202+00:00'
started_at: '2026-08-13T22:36:46.935180+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La memoria del proyecto (`documents/Memoria_TFM FV.docx`, apartado 6.1) menciona
explícitamente como enriquecimiento planeado: "fuentes europeas de cobertura
continental (calidad del aire validada y observación por satélite)". Todavía no se
había abordado. El servicio **Copernicus Atmosphere Monitoring Service (CAMS)** de
la UE ofrece exactamente esto: previsión de calidad del aire a 4 días vista,
horaria, para toda Europa, validada contra observaciones oficiales (EEA) —
complementa a la tarea 006 (tiempo real, solo Madrid) con una previsión y una
validación de referencia europea.

## Objetivo

Capturar una muestra pequeña de previsión de calidad del aire de CAMS para el área
de Madrid.

## Alcance concreto

1. Regístrate en el Atmosphere Data Store (ADS) de Copernicus (cuenta gratuita) para
   obtener credenciales (variable de entorno, p.ej. `CAMS_ADS_API_KEY` — investiga el
   mecanismo real de autenticación de la ADS API, puede ser distinto de una simple
   API key). Si el registro requiere un paso manual no automatizable, documenta el
   bloqueo en `doc/019-captura-cams-calidad-aire-prevista.md` y deja el código
   preparado con datos de ejemplo, mismo criterio que en tareas anteriores con
   bloqueos similares (003, y posiblemente 018).
2. Crea `ingesta/capturas/cams_calidad_aire_madrid.py` que descargue la previsión de
   NO2/O3/PM2.5/PM10 (los contaminantes validados según la documentación de CAMS,
   no uses variables "experimentales" sin validar) para el área geográfica de Madrid
   y la normalice a un esquema mínimo y consistente (contaminante, valor previsto,
   fecha/hora de validez, fecha de emisión de la previsión, fuente="cams").
3. Genera una muestra pequeña real (unas pocas horas/contaminantes, no la previsión
   horaria completa a 4 días de toda Europa) en `ingesta/capturas/samples/`.
4. Añade un test que no dependa de la red real.
5. Documenta en `ingesta/README.md`: cómo obtener credenciales, el esquema, y con
   qué frecuencia CAMS publica una nueva previsión (investígalo: la documentación
   general dice "una vez al día", confírmalo).

## Restricciones

- NO dejes nada programado: captura puntual con muestra pequeña.
- Usa solo las variables que CAMS documenta como validadas contra observaciones
  reales (NO2, NO, SO2, O3, PM2.5, PM10, polvo) — no captures variables marcadas
  como experimentales/sin validar.
- Credenciales por variable de entorno, nunca hardcodeadas.

## Criterios de aceptación

- Muestra real (o mock documentado si el registro quedó bloqueado) de previsión de
  calidad del aire para Madrid, commiteada como fixture.
- `ingesta/README.md` documenta el esquema y la cadencia real de publicación de CAMS.
