# 084 — Esquema de plataformas y arquitectura

## Qué se implementó

`PLATFORM_SCHEMA.md` en la raíz del repositorio: inventario completo de
servicios AWS (S3, Lambda, EventBridge Scheduler, Glue, Athena, SSM, IAM,
CloudWatch, CodeBuild, Kafka) y plataformas externas (data.madrid.es, EMT,
AEMET, CAMS, Bluesky, Google Maps, Neo4j AuraDB, GitHub, BestTime.app como
referencia no integrada), con un diagrama Mermaid del flujo de datos
completo (fuentes → Lambda → Bronze → Glue → Silver/Gold → Athena/grafo →
asistente).

## Verificación contra datos reales

Todos los recuentos (12.169 objetos Bronze, 17.619 Silver, 1.343 Gold, 13
Lambda, 20 schedules, 46 jobs de Glue, 28 triggers, 9 secretos SSM) se
tomaron de la comprobación en vivo hecha contra la cuenta real
(`eu-west-1`, `222234418587`) al inicio de esta sesión de arquitectura, no
de la documentación histórica — cruzados después contra `doc/001`-`doc/082`
para explicar el porqué de cada pieza.

## Decisiones de esta tarea

- **No es solo un inventario**: incluye una sección "Riesgos activos" que
  documenta explícitamente los hallazgos de la tarea 083 (drift de
  Terraform, alcance de IAM, footgun de `-target`/`-destroy`, 3 tablas Gold
  rotas, sin acceso a Cost Explorer) como estado real de la plataforma, no
  solo como lista de servicios — un inventario sin esto daría una imagen
  incompleta de "qué tan sano está el sistema hoy".
- **Google Maps aparece en la tabla de plataformas externas marcado como
  "Descartado el 25/8"**, no como "pendiente" — para que quien lea este
  documento en el futuro no lo confunda con un bloqueador de credencial
  todavía abierto.
- El diagrama usa Mermaid (soportado nativamente por GitHub al renderizar
  Markdown) en vez de una imagen estática, para que quede versionado como
  texto y sea fácil de mantener cuando cambie la arquitectura.

## Relevante para tareas futuras

- Este documento es un punto en el tiempo (25/8/2026) — no se actualiza
  automáticamente. Debe revisarse cuando se apliquen cambios reales de
  infraestructura (en particular, tras la reconciliación de Terraform de
  la prioridad 1 de `NEXT_STEPS.md`, y tras implementar la tarea 086).
- Si se añade CI (prioridad recomendada en `NEXT_STEPS.md`), sería el lugar
  natural para automatizar parte de esta verificación (p. ej. contar
  recursos reales y contrastarlos contra este documento).
