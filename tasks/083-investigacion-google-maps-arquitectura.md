---
id: 83
slug: investigacion-google-maps-arquitectura
title: "Investigación: Google Maps a coste 0, y salud de la infraestructura desplegada"
status: in_review
force: false
allow_infra_apply: false
branch: task/083-investigacion-google-maps-arquitectura
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-25T00:00:00+00:00'
updated_at: '2026-08-25T00:00:00+00:00'
started_at: '2026-08-25T00:00:00+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Tarea ejecutada de forma interactiva (no por `madrono-agent`) por Filippos
como parte de una revisión de arquitectura: el objetivo inicial era retirar
la dependencia de Google Maps Platform del proyecto (bloqueador de coste
pendiente en `PLAN.md`) para garantizar coste 0. Al ejecutarlo aparecieron
dos hallazgos que cambiaron el alcance — ver `doc/083-investigacion-google-
maps-arquitectura.md` para el detalle completo verificado.

## Qué se hizo

1. Se verificó, leyendo el código fuente real de la librería `populartimes`
   (`m-wrzr/populartimes`, `crawler.py`) contra su uso en
   `ingesta/capturas/afluencia_lugares_madrid.py`, que **no existe ninguna
   forma de obtener datos reales de afluencia a coste 0** a través de esa
   librería: `populartimes.get_id()` llama primero, siempre, a la API
   oficial y de pago "Place Details" antes de poder hacer scraping — no es
   evitable fijando `place_id` a mano.
2. Se ejecutó `terraform plan` (sin acotar) contra la infraestructura real
   (`eu-west-1`, `222234418587`) y se descubrió que el estado desplegado ha
   derivado de forma significativa respecto a `main` (48 objetos de código
   Glue/Lambda desactualizados, infraestructura de Kafka nunca aplicada, un
   permiso IAM que falta) — un riesgo más urgente que Google Maps.
3. Se probó (solo `plan`, nunca `apply`) acotar la retirada de
   `afluencia_lugares` con `-target`, y se documentó un footgun real:
   `terraform plan -destroy -target=...` sobre este dataset arrastraba la
   planificación de destruir los 14 productores Lambda completos por
   políticas IAM compartidas.
4. Se revirtieron todos los cambios de Terraform hechos durante la
   investigación (`git checkout --` sobre los 3 ficheros tocados) — no se
   aplicó ningún cambio real en AWS en ningún momento.
5. Se decidió **sustituir, no borrar**, la capacidad de "afluencia": una
   señal compuesta vía el grafo Neo4j sobre datos ya ingeridos a coste 0
   (ver tarea 086, especificación sin implementar).

## Restricciones respetadas

- Ningún `terraform apply` real ejecutado.
- Ningún dato de los buckets Bronze/Silver/Gold tocado ni en riesgo
  (confirmado: cero acciones `aws_s3_bucket*` en cualquiera de los planes
  generados).
- Ninguna credencial de Google Maps ni de ningún otro secreto expuesta en
  el repositorio.

## Criterios de aceptación

- `doc/083-investigacion-google-maps-arquitectura.md` documenta ambos
  hallazgos con evidencia verificable (citas de código, output de
  `terraform plan`).
- El estado de `infra/terraform/` en este PR es idéntico al de `main`
  (investigación revertida, sin cambios de infraestructura).
- La decisión de sustituir Google Maps por una señal basada en grafo queda
  registrada aquí y detallada en la tarea 086.
