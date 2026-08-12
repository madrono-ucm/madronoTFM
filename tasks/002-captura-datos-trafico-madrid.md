---
id: 2
slug: captura-datos-trafico-madrid
title: Captura de datos de tráfico de Madrid (primer productor de ingesta)
status: in_progress
force: true
branch: task/002-captura-datos-trafico-madrid
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-11T23:03:46+00:00'
updated_at: '2026-08-12T00:14:43.965280+00:00'
started_at: '2026-08-11T23:54:42.845221+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Fase 1 del proyecto (Ingesta, ver Tabla 1 y apartado 6.1 de
`documents/Memoria_TFM FV.docx`): «Productores Kafka y lakehouse Bronze/Silver» →
«Pipeline de ingesta operativo». Esta tarea implementa el primer productor de datos:
la fuente de tráfico en tiempo real de Madrid (categoría «Movilidad y transporte», la
primera de las fuentes descritas en la memoria).

## Objetivo

Escribe un script/productor en Python que capture periódicamente los datos abiertos
de intensidad de tráfico de Madrid y los aterrice en la capa Bronze del lakehouse,
sentando el patrón que seguirán los futuros productores de las demás fuentes
(transporte público, bicicleta compartida, calidad del aire, ruido, meteorología).

## Alcance concreto

1. Investiga y usa la fuente de datos abiertos de tráfico del Ayuntamiento de Madrid
   (portal de datos abiertos datos.madrid.es u otra fuente pública equivalente) — son
   datos públicos, no deberían requerir credenciales.
2. Crea un módulo Python (elige una ubicación razonable, p.ej. algo como
   `ingesta/capturas/trafico_madrid.py`; usa tu criterio y documenta por qué en el
   resumen de `doc/`) que:
   - Consulte el estado de intensidad de tráfico.
   - Normalice el resultado a un esquema mínimo y consistente (timestamp, id del
     punto de medida, ubicación, intensidad/velocidad/ocupación tal como venga en la
     fuente).
   - Escriba el resultado en una estructura de carpetas que imite la capa Bronze del
     lakehouse (p.ej. `bronze/trafico/fecha=YYYY-MM-DD/hora=HH/*.json`), **en local
     por ahora** — todavía no hay infraestructura S3 aplicada (ver tarea 001), así
     que debe aterrizar en disco con una ruta base configurable por variable de
     entorno, para poder apuntar a S3 más adelante sin cambiar el código.
3. No hace falta un broker Kafka real todavía: deja un comentario/TODO claro
   marcando dónde se conectaría un productor Kafka cuando la infraestructura de
   streaming esté disponible — no implementes Kafka en esta tarea.
4. Incluye manejo básico de errores de red (reintentos simples) y logging.
5. Documenta cómo ejecutarlo (README breve) y qué variables de entorno usa.
6. Añade una comprobación/test mínimo que no dependa de la red real si es posible
   (con datos de ejemplo), para poder verificar que el parseo/normalización
   funciona sin llamar a la API real en cada ejecución.

## Restricciones

- No necesitas credenciales de AWS ni conexión real a S3 en esta tarea — aterriza en
  disco local con ruta configurable.
- No implementes Kafka todavía, solo la captura de datos y su normalización a
  Bronze.
- Si la fuente pública no fuera accesible desde este entorno (red, firewall...),
  documenta el problema en el resumen de `doc/` y deja igualmente el código
  preparado, con datos de ejemplo/mock para poder probarlo.

## Criterios de aceptación

- Ejecutar el script una vez produce al menos un archivo en la estructura Bronze
  esperada (con datos reales, o con datos mock si la red no estuviera disponible).
- El patrón del código (estructura, normalización, configuración por variables de
  entorno) es reutilizable tal cual para las próximas fuentes de datos.
