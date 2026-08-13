---
id: 23
slug: captura-cartelera-cines-madrid
title: "Captura de cartelera y horarios de cines de Madrid (muestra)"
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

Complementa a la tarea 022: ir al cine es uno de los "planes alternativos" que
Madroño podría recomendar (memoria, objetivo del asistente), y a diferencia de un
partido en el Bernabéu, no hay una API oficial de las grandes cadenas (Cinesa,
Yelmo Cines). A diferencia de las capturas de datos.madrid.es, aquí es previsible
que haga falta algún tipo de scraping — pero investiga primero si las páginas de
cartelera exponen datos estructurados para SEO (marcado `schema.org/ScreeningEvent`
o similar en JSON-LD embebido en el HTML) antes de asumir que hay que parsear HTML
a mano: es mucho más robusto y estable si existe.

## Objetivo

Capturar una muestra pequeña de cartelera (películas + horarios) de al menos un
cine de Cinesa y uno de Yelmo en Madrid.

## Alcance concreto

1. Investiga si las páginas de cartelera de Cinesa/Yelmo (o un agregador como
   SensaCine, si resulta más estable/estructurado) exponen JSON-LD
   `schema.org/ScreeningEvent` o similar. Documenta qué encontraste y por qué
   elegiste la fuente final.
2. Crea `ingesta/capturas/cartelera_cines_madrid.py` con:
   - `fetch_cinema_showtimes(cinema_id)`: cartelera de un cine concreto (pensado
     para uso bajo demanda por el asistente).
   - `sweep_premieres()`: estrenos destacados de la semana en Madrid (pensado para
     una captura programada ligera, p.ej. diaria, ya que las carteleras cambian
     semanalmente pero puede haber cambios/cancelaciones puntuales).
   - Normaliza a un esquema mínimo (cine, sala/dirección si está disponible,
     película, horario, fecha).
3. Genera una muestra pequeña real (un cine de cada cadena, unos pocos horarios) en
   `ingesta/capturas/samples/`.
4. Añade un test que no dependa de la red real.
5. Documenta en `ingesta/README.md` la fuente elegida, si usa datos estructurados o
   scraping HTML, y cualquier limitación de términos de uso a tener en cuenta (nivel
   de detalle similar a cómo se documentó la zona gris de la tarea 012, si aplica
   aquí también).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente en esta tarea.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2.
- Si el scraping resultara excesivamente fragil o claramente contrario a los
  términos de uso del sitio, documenta el problema en
  `doc/023-captura-cartelera-cines-madrid.md` en vez de forzarlo, y deja el código
  preparado con datos de ejemplo.

## Criterios de aceptación

- Muestra real (o mock documentado si el acceso resultó bloqueado/problemático) de
  cartelera de al menos dos cadenas distintas.
- `ingesta/README.md` documenta la fuente, el método de extracción, y cualquier
  consideración de términos de uso.
