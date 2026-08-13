---
id: 20
slug: captura-calendario-laboral-madrid
title: "Captura del calendario laboral y festivos de Madrid (carga puntual)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-13T17:23:43+00:00"
updated_at: "2026-08-13T17:23:43+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Un martes festivo se comporta, a efectos de afluencia, como un domingo — sin el
calendario laboral el modelo no puede distinguirlo. El Ayuntamiento de Madrid
publica el calendario laboral oficial (festivos regionales y locales) en
datos.madrid.es (dataset `300082-0-calendario_laboral`, formatos ICS/CSV,
2013-2026, sin autenticación). Es dato de referencia casi estático — igual que las
tareas 009-011, no una serie temporal.

## Objetivo

Capturar el calendario laboral/festivos de Madrid y normalizarlo.

## Alcance concreto

1. Crea `ingesta/capturas/calendario_laboral_madrid.py`: descarga -> normaliza a un
   esquema mínimo y consistente (fecha, tipo de festivo —nacional/regional/local—,
   descripción/nombre del festivo).
2. Documenta explícitamente que esto es una **carga de referencia casi estática**
   (se publica una vez al año, con años completos de antelación) — mismo criterio
   que 009-011, no admite ni necesita scheduling frecuente.
3. Genera una muestra pequeña (puede ser el calendario completo de un único año,
   dado que el dataset entero no es grande — usa tu criterio, documenta cuántos
   años incluyes en la muestra y por qué) en `ingesta/capturas/samples/`.
4. Añade un test que no dependa de la red real.
5. Documenta el módulo en `ingesta/README.md`.

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente.
- No debería hacer falta ninguna credencial.
- Si la fuente no fuera accesible, documenta el problema y deja el código preparado
  con datos de ejemplo.

## Criterios de aceptación

- Muestra real commiteada con el calendario normalizado.
- `ingesta/README.md` documenta el esquema y confirma que es carga de referencia,
  no programable de forma frecuente.
