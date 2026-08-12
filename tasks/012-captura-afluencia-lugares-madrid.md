---
id: 12
slug: captura-afluencia-lugares-madrid
title: "Captura de afluencia de lugares (popularidad tipo Google, muestra)"
status: pending
force: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-12T23:12:29+00:00"
updated_at: "2026-08-12T23:12:29+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`, apartado 6.1
«Contexto urbano»: afluencia de lugares públicos; y apartado 6.8, que ya reconoce
explícitamente que esta fuente concreta usa «librerías de código abierto» en una
«zona gris» respecto a condiciones de uso de terceros, **admisible únicamente en el
marco académico de este trabajo**; en producción se sustituiría por un proveedor
comercial con licencia — 7.5).

Se investigó a fondo antes de crear esta tarea (ver conversación/resumen en `doc/`
si existe una entrada previa de contexto): no existe ninguna API oficial que venda
este dato concreto («qué tan lleno está un lugar concreto ahora, y habitualmente»).
La única vía conocida y con algo de mantenimiento es la librería
**[`m-wrzr/populartimes`](https://github.com/m-wrzr/populartimes)**: usa la API
oficial de Google Places (de pago, con tier gratuito mensual) solo para localizar el
lugar, y obtiene el dato de popularidad real haciendo scraping de un endpoint interno
no documentado de Google (`google.*/search?tbm=map...`), parseando por posición un
JSON sin contrato — es intrínsecamente frágil (puede romperse sin aviso si Google
cambia su página) y su issue más comentado en GitHub es, literalmente, sobre posible
violación de las condiciones de uso. **No reimplementes el scraping a mano**: úsala
como dependencia externa tal cual.

## Objetivo

Usar `populartimes` para obtener, de una muestra pequeña de lugares conocidos de
Madrid (3-5, p.ej. Puerta del Sol, Parque del Retiro, Mercado de San Miguel...), dos
cosas a la vez (la librería ya las da juntas en una sola consulta):

1. **Popularidad en vivo** (`current_popularity`), si está disponible en el momento
   de la captura.
2. **Patrón típico por hora y día de la semana** (`populartimes`) — esta es la
   «previsión estimada»: no hace falta scrapear en vivo para poder responder algo
   como «¿un viernes a las 21h suele haber mucha gente aquí?», ese patrón habitual ya
   lo da la propia respuesta.

## Alcance concreto

1. Añade `populartimes` (instalado directamente desde
   `git+https://github.com/m-wrzr/populartimes`, no desde PyPI si está desactualizado
   allí — comprueba) a `ingesta/requirements.txt`.
2. Crea `ingesta/capturas/afluencia_lugares_madrid.py` con el mismo patrón de
   descarga -> normaliza que el resto de capturas, pero usando la librería en vez de
   HTTP directo: para cada lugar de la muestra, obtén `current_popularity` (puede ser
   `null`) y `populartimes` (patrón por día/hora), y normalízalos a un esquema mínimo
   y consistente (id/nombre del lugar, timestamp de captura, `live_pct` nullable,
   `typical_by_hour`: estructura día de la semana -> 24 valores de popularidad
   0-100).
3. Necesitarás una **Google Maps API key** gratuita (tier mensual gratuito de Google
   Cloud) — léela de una variable de entorno (`GOOGLE_MAPS_API_KEY`), documenta cómo
   obtenerla, no la hardcodees ni la necesites para que el modo de prueba/tests
   funcione sin red.
4. Documenta explícita y prominentemente en `ingesta/README.md` (sección propia para
   esta fuente): el origen exacto del dato (API oficial + scraping no documentado),
   que es admisible solo en el marco académico de este TFM (cita el apartado 6.8 de
   la memoria), y que en producción se sustituiría por un proveedor con licencia
   (p.ej. BestTime.app o similar — no hace falta integrarlo, solo mencionarlo).
5. Si la librería falla al ejecutarla (es plausible: la técnica es frágil y puede
   llevar tiempo rota sin que nadie la arregle), documenta el fallo concreto en el
   resumen de `doc/` y deja igualmente el código preparado, con una muestra de datos
   de ejemplo (mock) que demuestre el esquema normalizado esperado.
6. Añade un test que no dependa de la red real (con una respuesta de ejemplo de la
   librería, no de la red).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una captura puntual de una muestra
  pequeña, invocada a mano.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2. El
  resultado es una muestra pequeña (3-5 lugares) guardada como fixture versionado en
  el repo — no un bucle de captura. El destino real (S3/BD) llega con la
  infraestructura, que todavía no existe (tarea 001 sin aplicar).
- No uses APIs de pago más allá del tier gratuito de Google Places (unas pocas
  búsquedas para 3-5 lugares están muy por debajo del crédito mensual gratuito).
- No reimplementes el scraping de Google a mano ni intentes "arreglar" técnicas de
  scraping por tu cuenta si `populartimes` falla — documenta y usa datos de ejemplo,
  como se indica arriba.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de 3-5 lugares con `live_pct` y
  `typical_by_hour` normalizados (reales si la librería funciona, de ejemplo si no),
  visible en el PR como fixture pequeño commiteado, sin dejar nada corriendo ni
  programado.
- `ingesta/README.md` documenta el origen del dato, su naturaleza de zona gris
  (citando la memoria), y la alternativa comercial para producción.
- El resumen de `doc/` deja constancia explícita de si la librería funcionó o no en
  el momento de esta captura.
