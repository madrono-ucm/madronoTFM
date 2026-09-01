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

## 2026-09-01 — Fix del mapa publicado (FIL_55), reanudación del pipeline + FIL_16/17

**Punto de partida**: el usuario ve bugs en el frontend desplegado en
GitHub Pages; arreglarlos y seguir con lo pendiente.

1. **`FIL_55`** (PR #234, mergeado) — el panel de resumen del mapa animado
   (`FIL_49`) lanzaba `TypeError` con las métricas virtuales de `FIL_45`
   (`salud_perfil`/`dosis_*`, no viven en `DATA[dia]`) → cada clic de perfil
   o de dosis congelaba el panel + el pulso de distrito. `_mediaCiudad()`/
   `resumen()` arreglados; además `trig` de nodos += `perfil`/`escala`,
   `ArcLayer.getTargetColor` en `updateTriggers`, `render()` en
   `onViewStateChange`, `mejorHoraPerfil` memoizado. Verificado con arnés
   headless jsdom (51 controles, 0 excepciones). `gh-pages` republicado
   (commit `685bb6d`), sitio en vivo verificado.

2. **Reanudación del pipeline** (`pipeline_enabled=true`, decisión del
   usuario tras 32 días congelado) + **`FIL_16`/`FIL_17`** aplicados con
   `terraform apply -target` (profile `madrono`):
   - **`FIL_17` ✅ aplicado y verificado**: los 4 productores con secreto
     ya no llevan credenciales en claro en el env de la Lambda (sólo
     `*_SSM_PATH`); política `ssm:GetParameter` acotada a los 6 ARNs.
   - **Unfreeze ✅**: ~23 `aws_scheduler_schedule` → `ENABLED`, ~26
     `aws_glue_trigger` → `ACTIVATED`. La ingesta vuelve a acumular dato y
     a gastar (~16 días para la entrega).
   - **`FIL_16` ⚠️ parcial**: la regla EventBridge `glue-job-failed` está
     creada y `ENABLED`, pero el topic SNS falló —
     `madrono-terraform-deployer` no tiene permisos SNS (único servicio sin
     `*FullAccess`). Falta `AmazonSNSFullAccess` en el usuario IAM (el
     clasificador bloqueó adjuntarla) y re-aplicar 3 recursos. Ver
     `doc/FIL-16`.
   - El `apply` full traía además Kafka (deliberadamente sin aplicar) y un
     rebuild de la layer Lambda (drift de `ingesta/requirements.txt` por
     `defusedxml`) → se excluyeron con `-target`.

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
