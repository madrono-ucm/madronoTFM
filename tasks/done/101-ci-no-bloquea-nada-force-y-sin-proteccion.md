---
id: 101
slug: ci-no-bloquea-nada-force-y-sin-proteccion
title: 'QA: la CI (097) corre y suele estar en verde, pero no bloquea ningún merge
  — ni en tareas force:true ni por falta de branch protection'
status: done
force: false
allow_infra_apply: false
branch: task/101-ci-no-bloquea-nada-force-y-sin-proteccion
pr_number: 148
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/148
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-27T21:20:00+00:00'
updated_at: '2026-08-27T22:15:05.806215+00:00'
started_at: '2026-08-27T21:12:54.532935+00:00'
submitted_at: '2026-08-27T21:17:07.149437+00:00'
merged_at: '2026-08-27T22:14:08Z'
---

## Hallazgo de QA (auditoría de la tarea 097, verificado en vivo)

`doc/097-ci-minima.md` describe correctamente lo que la CI hace (`tests` +
`terraform fmt/validate`, `.github/workflows/ci.yml`) y `NEXT_STEPS.md`
(Prioridad 5) la cita como la pieza que da "la posibilidad de review y QA
automática que complementa la revisión humana de PRs ya existente". Ese
objetivo **no se cumple hoy**, verificado por dos motivos independientes,
ninguno de los dos es un fallo de lo que construyó la tarea 097 en sí — es
que nada la conecta al proceso de merge real:

1. **`main` no tiene ninguna regla de branch protection**
   (`gh api repos/.../branches/main/protection` → `404 Branch not
   protected`). Ni PRs revisados por humanos ni el propio GitHub exigen que
   los checks de CI estén en verde antes de fusionar — un merge manual
   (botón verde de GitHub) puede hacerse con CI en rojo sin ningún aviso
   bloqueante.
2. **Las tareas `force: true` (la mayoría de la cola) fusionan el PR sin
   esperar en absoluto a que la CI termine**: `merge_pr()` en
   `tasks/scripts/gh_git.py` (repo `madronoTFM-agent`) llama a
   `gh pr merge --squash --delete-branch` directamente, sin `--auto` ni
   ninguna comprobación de `checks`. Verificado con el histórico real de
   ejecuciones (`gh run list`): ya ha pasado que un `push` a `main`
   (fusión de una tarea `force: true`) queda en **rojo** y permanece así
   hasta que una tarea de seguimiento lo arregla — p. ej. la propia tarea
   097 quedó roja en su primer intento de fusión
   (`32989323815`, `Instalar dependencias` falló por el mismo motivo que
   luego arregló la tarea 099) y estuvo así varias horas hasta el fix.

**Conclusión**: la CI existe, corre, y normalmente está en verde — es útil
como señal para quien revisa un PR `force: false` a mano. Pero para las
tareas `force: true` (que son la mayoría del volumen de la cola autónoma)
es puramente decorativa: el merge ya ha ocurrido, típicamente segundos
después de crear el PR, antes incluso de que los jobs de CI terminen de
ejecutarse (verificado: en varias tareas recientes el PR se fusiona 5-10
segundos después de crearse, mientras que cada job de CI tarda 20-60s).

## Objetivo

Que la CI tenga poder de bloqueo real, al menos para las tareas
`force: false` (revisión humana) y, si se decide, retrasar el auto-merge de
`force: true` hasta que los checks terminen.

## Alcance concreto

1. Activar branch protection en `main` (vía GitHub, no vía Terraform — no
   hay recurso de Terraform para esto en este repo) exigiendo que los
   checks `tests` y `terraform` estén en verde antes de poder fusionar
   cualquier PR — pide confirmación explícita al usuario antes de activarlo
   (cambia el comportamiento del repositorio para todo el equipo, no solo
   código).
2. Para las tareas `force: true`: decide y documenta (con el usuario, es
   una decisión de producto/proceso, no solo técnica) si quieres que
   `merge_pr()` espere a los checks antes de fusionar
   (`gh pr merge --auto --squash` en vez de `--squash` a secas, o un poll
   explícito de `gh pr checks` con timeout) — trade-off: añade
   20-60s de latencia por tarea a cambio de que un `force: true` con CI
   roja no llegue nunca a fusionarse solo.
3. Si se decide esperar los checks, actualiza `merge_pr()` en
   `madronoTFM-agent` (el clon del demonio, no este repo) y
   `tasks/README.md` de este repo para documentar el nuevo comportamiento.
4. Documenta en `doc/101-...md` qué se decidió y qué se aplicó.

## Restricciones

- Activar branch protection y cambiar la lógica de merge del demonio son
  cambios de proceso/infraestructura del propio flujo de trabajo, no solo
  código de la aplicación — pide aprobación explícita del usuario antes de
  aplicar cualquiera de los dos, igual que con un `terraform apply` real.
- No toques `.github/workflows/ci.yml` salvo que el hallazgo de esta
  auditoría requiera un cambio ahí (no debería: el workflow en sí está
  bien construido, el problema es que nada lo conecta al merge).

## Criterios de aceptación

- Decisión documentada (con el usuario) sobre branch protection y sobre si
  `force: true` debe esperar a los checks.
- Si se aplica branch protection, verificado que un PR con CI roja ya no
  se puede fusionar desde la UI de GitHub sin saltárselo explícitamente.
- `doc/101-...md` documenta el hallazgo y la decisión.
- Hay un commit real (aunque sea solo de documentación, si la decisión es
  "no cambiar nada por ahora").
