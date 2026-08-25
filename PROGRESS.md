# Progreso — sesiones de ingeniería (senior dev / staff platform)

Bitácora de las sesiones de trabajo interactivo (no `madrono-agent`) sobre
este repositorio. Complementa, sin duplicar:

- [`PLAN.md`](PLAN.md) — coordinación humana entre Filippos y Víctor,
  reparto de trabajo, bloqueadores.
- [`doc/README.md`](doc/README.md) — bitácora automática, una entrada por
  tarea de `madrono-agent` completada.
- [`PLATFORM_SCHEMA.md`](PLATFORM_SCHEMA.md) — inventario de plataformas y
  arquitectura, punto en el tiempo.
- [`NEXT_STEPS.md`](NEXT_STEPS.md) — plan priorizado hacia el cierre del
  TFM (17 sept 2026).

Este documento responde a "¿qué se ha hecho en sesiones de ingeniería
directa, y por qué?" — para que una sesión futura (de cualquiera de los
dos, o de un asistente) pueda retomar contexto rápido sin releer todo el
historial de `doc/`.

## 2026-08-25 — Revisión de arquitectura: Google Maps, drift de Terraform, hoja de ruta

**Punto de partida**: petición de actuar como responsable técnico del
proyecto — entender el objetivo final, dejar un documento de progreso,
retirar la dependencia de Google Maps Platform (coste 0), documentar la
arquitectura de plataformas, y planificar los siguientes pasos.

**Lo que cambió sobre la marcha**: el intento inicial de "borrar Google
Maps" se convirtió en una investigación más profunda tras dos hallazgos —
ver [`doc/083-investigacion-google-maps-arquitectura.md`](doc/083-investigacion-google-maps-arquitectura.md)
para el detalle completo:

1. **Google Maps no puede dar datos reales a coste 0**, verificado a nivel
   de código (la librería `populartimes` exige una llamada de pago a la API
   oficial de Google *antes* de poder hacer scraping, sin forma de
   evitarlo). Decisión: sustituir la capacidad de "afluencia" por una señal
   basada en el grafo Neo4j sobre datos ya ingeridos a coste 0, en vez de
   simplemente eliminarla — ver la tarea 086.
2. **El estado de Terraform ha derivado de `main`** — 48 objetos de código
   Glue/Lambda desplegados están desactualizados respecto al repositorio,
   y existe un permiso IAM (`codebuild:BatchGetProjects`) que falta. Más
   urgente que Google Maps; queda como prioridad en `NEXT_STEPS.md`.

**Entregado en esta sesión** (PRs, ver tabla):

| Tarea | Qué | PR |
|---|---|---|
| [083](tasks/083-investigacion-google-maps-arquitectura.md) | Investigación Google Maps + hallazgo de drift de Terraform | _pendiente_ |
| [084](tasks/084-esquema-plataformas.md) | `PLATFORM_SCHEMA.md` — inventario de plataformas/arquitectura | _pendiente_ |
| [085](tasks/085-plan-cierre-tfm.md) | `NEXT_STEPS.md` — plan priorizado hacia el 17 sept 2026 | _pendiente_ |
| [086](tasks/086-afluencia-estimada-grafo.md) | Especificación (sin implementar) de la señal de afluencia basada en grafo | _pendiente_ |

**Ningún cambio real se aplicó en AWS en esta sesión** — dos intentos de
`terraform plan` (uno sin acotar, uno con `-target`) se ejecutaron para
investigar, ambos revertidos sin `apply`. Ver hallazgo 2b en doc/083 sobre
un footgun real de `-target`/`-destroy` descubierto en el proceso.

**Para la próxima sesión**: ver la sección de prioridades de
`NEXT_STEPS.md` — en orden, reconciliar el drift de Terraform (revisado
contigo, resumen completo), decidir si se implementa ya la tarea 086, y
seguir con el resto del roadmap.
