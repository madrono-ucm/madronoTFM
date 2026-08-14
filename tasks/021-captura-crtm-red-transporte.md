---
id: 21
slug: captura-crtm-red-transporte
title: Captura de la red estructural de transporte de Madrid (GTFS, CRTM) (muestra)
status: blocked
force: true
allow_infra_apply: false
branch: task/021-captura-crtm-red-transporte
pr_number: null
pr_url: null
attempts: 5
next_retry_at: '2026-08-14T01:24:16.460466+00:00'
last_error: You've hit your session limit · resets 3:10am (UTC)
created_at: '2026-08-13T17:23:43+00:00'
updated_at: '2026-08-14T00:18:06.345892+00:00'
started_at: '2026-08-13T23:01:14.418477+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 003 (llegadas en vivo de EMT) quedó bloqueada: necesita una cuenta
MobilityLabs con email verificado, un paso manual pendiente. El **Consorcio
Regional de Transportes de Madrid (CRTM)** publica en su portal de datos abiertos
(`datos.crtm.es` / `data-crtm.opendata.arcgis.com`) los feeds **GTFS estáticos**
completos de Metro, EMT y Metro Ligero — descarga directa, **sin cuenta ni
verificación por email**. No da llegadas en vivo (para eso sigue haciendo falta
resolver el bloqueo de la 003), pero sí la red completa: líneas, paradas,
horarios programados — contexto estructural de transporte que hoy no tenemos.

## Objetivo

Capturar una muestra pequeña de la red de transporte de Madrid a partir del GTFS
de CRTM, y comprobar si además existe un feed GTFS-RT (tiempo real/alertas de
servicio) accesible sin las credenciales que bloquean a la 003.

## Alcance concreto

1. Investiga en `datos.crtm.es` los feeds GTFS disponibles (Metro, EMT, Metro
   Ligero) y **comprueba explícitamente si además publican GTFS-RT** (alertas de
   servicio, incidencias, retrasos) de forma abierta — si existe y no requiere
   cuenta, es un hallazgo relevante a documentar de cara a la 003.
2. Crea `ingesta/capturas/crtm_red_transporte_madrid.py`: descarga el GTFS estático
   (probablemente un ZIP con varios CSV: `routes.txt`, `stops.txt`, `trips.txt`,
   `stop_times.txt`...) -> normaliza a un esquema mínimo (líneas y sus paradas
   principales, no hace falta modelar el grafo completo de horarios en esta
   tarea — usa tu criterio sobre qué nivel de detalle aporta valor para una
   primera muestra).
3. **No leas el ZIP/CSV completo en el contexto de la sesión** (puede ser grande):
   inspecciónalo con herramientas de línea de comandos antes de decidir qué
   extraer, mismo criterio que en tareas anteriores con datasets grandes (009).
4. Genera una muestra pequeña (unas pocas líneas/paradas, no la red completa) en
   `ingesta/capturas/samples/`.
5. Añade un test que no dependa de la red real.
6. Documenta en `ingesta/README.md`: es dato de referencia (la red cambia pocas
   veces al año, con "cambios de servicio" programados) — igual que 009-011, no una
   serie temporal a programar con frecuencia. Documenta también el hallazgo sobre
   GTFS-RT (exista o no).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente.
- NO leas ficheros GTFS completos en el contexto de la sesión.
- No debería hacer falta ninguna credencial para el GTFS estático.

## Criterios de aceptación

- Muestra real commiteada con la red de transporte normalizada.
- `ingesta/README.md` documenta el esquema, confirma que es dato de referencia, y
  deja constancia explícita de si existe o no un GTFS-RT abierto (relevante para
  desbloquear en el futuro parte de lo que persigue la tarea 003).
