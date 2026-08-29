# 101 — QA: la CI (097) no bloquea ningún merge

> **Actualización 29/8 — AMBAS recomendaciones aplicadas** (sesión
> interactiva, con visto bueno explícito del usuario; ver §"Aplicado" al
> final). El resto del documento es el análisis original de la tarea
> autónoma, que dejó los dos cambios diseñados y verificados pero sin
> ejecutar.

## Contexto

El propio enunciado de esta tarea ya trae el hallazgo verificado (auditoría
de la tarea 097 hecha en la sesión de QA previa a esta): la CI construida
en `.github/workflows/ci.yml` corre y suele estar en verde, pero **no
bloquea ningún merge real**, por dos motivos independientes:

1. `main` no tiene ninguna regla de branch protection.
2. `merge_pr()` (`tasks/scripts/gh_git.py:164`) fusiona los PR de tareas
   `force: true` con `gh pr merge --squash --delete-branch` sin esperar en
   absoluto a que los checks de CI terminen.

Esta sesión repitió la verificación antes de tocar nada:

```
gh api repos/madrono-ucm/madronoTFM/branches/main/protection
→ 404 "Branch not protected"

gh api repos/madrono-ucm/madronoTFM
→ "allow_auto_merge": false   (además de no haber protección de rama)
```

Confirmado también con lectura de código (`tasks/scripts/agent_loop.py:193-213`
y `:276-286`): el auto-merge de `force: true` llama a `gh_git.merge_pr()`
inmediatamente después de crear el PR, sin ningún `sleep`/poll/`--auto` de
por medio.

## Decisión: documentar y dejar listo para aplicar, no aplicar en esta tarea

El propio enunciado de la tarea pide, para ambos cambios, "aprobación
explícita del usuario... igual que con un `terraform apply` real" — y esta
tarea corre en el pipeline autónomo, sin ningún humano disponible en tiempo
real para confirmarlo. Igual que `doc/098`/`doc/100` con el drift de
Terraform (generar y verificar el plan, pero dejar el `apply` real para una
tarea posterior con aprobación explícita), aquí se sigue el mismo patrón:
**ambos cambios quedan diseñados, verificados en lo que se puede verificar
sin aplicarlos, y documentados — pero ninguno de los dos se ejecuta en esta
tarea.** Motivo adicional, no solo procedimental: los dos cambios afectan a
sistemas compartidos y de difícil marcha atrás limpia —
branch protection es una configuración del repositorio que rige para todo
el equipo, no solo para este PR, y tocar `merge_pr()`/`agent_loop.py` altera
el comportamiento del propio demonio para **todas** las tareas `force: true`
futuras, incluidas las que ya están en la cola.

Esto también encaja con que esta tarea tiene `force: false`: su propio PR
necesita revisión humana antes de fusionarse, que es exactamente el punto
en que alguien puede leer esta recomendación y decidir si aplicarla.

### Recomendación 1 — branch protection en `main`

Exigir que los dos checks reales de `.github/workflows/ci.yml` (jobs
`tests` y `terraform`, verificados por nombre en el propio workflow) estén
en verde antes de poder fusionar. Comando listo para ejecutar por quien
administre el repositorio (necesita permisos de administrador — verificado
que la identidad de esta sesión sí los tiene, `"admin": true` en
`gh api repos/madrono-ucm/madronoTFM`, pero no se ha ejecutado):

```bash
gh api repos/madrono-ucm/madronoTFM/branches/main/protection \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -f "required_status_checks[strict]=false" \
  -f "required_status_checks[contexts][]=tests" \
  -f "required_status_checks[contexts][]=terraform" \
  -F "enforce_admins=false" \
  -F "required_pull_request_reviews=null" \
  -F "restrictions=null"
```

Notas sobre los parámetros elegidos (a revisar por quien apruebe, no son
la única opción razonable):

- `strict=false`: no exige que la rama esté actualizada con `main` antes de
  fusionar. Con `strict=true` cualquier PR abierto un rato quedaría
  obligado a un re-run de CI tras cada push a `main` — más estricto pero
  más fricción; se deja en `false` como punto de partida menos disruptivo,
  fácil de endurecer después.
- `enforce_admins=false`: los administradores (incluida la cuenta que usa
  el propio demonio) podrían seguir fusionando saltándose el check en un
  caso de emergencia. Si se quiere que la protección aplique sin excepción
  ni siquiera a administradores, cambiar a `true`.
- No se añade `required_pull_request_reviews`: el hallazgo de esta tarea es
  específicamente sobre CI, no sobre exigir revisión humana adicional (que
  ya existe como práctica para `force: false`, fuera del alcance de esta
  tarea).
- Efecto colateral importante para `force: true`: en cuanto se active esto,
  el auto-merge instantáneo actual de `merge_pr()` empezará a **fallar**
  sistemáticamente (no solo en la carrera transitoria que ya maneja
  `agent_loop.py:193-213`) hasta que termine la CI — `tasks/README.md` ya
  documenta ese caso ("si el auto-merge falla... el PR se queda igualmente
  en `in_review` a la espera de un merge manual"), así que el sistema no se
  rompe, pero las tareas `force: true` dejarían de auto-fusionarse de
  verdad hasta aplicar también la Recomendación 2.

### Recomendación 2 — que `force: true` espere a los checks antes de fusionar

Diseño propuesto para `merge_pr()` en `tasks/scripts/gh_git.py`: antes del
`gh pr merge`, esperar a que terminen los checks requeridos con
`gh pr checks --watch --fail-fast` (bloquea hasta que todos terminen, y
devuelve código de salida distinto de cero si alguno falla), acotado con un
timeout explícito para no dejar nunca al demonio bloqueado indefinidamente
si un run de CI se cuelga:

```python
def merge_pr(repo_path: Path, pr_number: int, config) -> None:
    """Fusiona un PR sin esperar revisión humana (solo para tareas con force: true).

    Espera primero a que terminen los checks de CI (timeout configurable);
    si algún check requerido falla o no termina a tiempo, no fusiona y deja
    que el llamador trate esto igual que cualquier otro fallo de merge
    (el PR queda en in_review para revisión manual).
    """
    _run(
        [config.gh_bin, "pr", "checks", str(pr_number),
         "--repo", config.github_repo, "--watch", "--fail-fast"],
        cwd=repo_path,
        timeout=config.gh_checks_timeout_seconds,  # p.ej. 600
    )
    _run(
        [config.gh_bin, "pr", "merge", str(pr_number),
         "--repo", config.github_repo,
         f"--{config.gh_merge_method}", "--delete-branch"],
        cwd=repo_path,
        timeout=120,
    )
```

Trade-off explícito (lo que pide el enunciado documentar): añade del orden
de 30-90s de latencia por tarea `force: true` (duración real observada de
los jobs `tests`/`terraform` en runs recientes) a cambio de que un
`force: true` con CI roja ya no pueda llegar nunca a fusionarse solo — hoy
puede, y ya ha pasado (la propia tarea 097 quedó roja varias horas tras su
primer auto-merge, ver el hallazgo de esta tarea).

Se descarta `gh pr merge --auto` como alternativa: requiere
`allow_auto_merge=true` a nivel de repositorio (hoy `false`, verificado
arriba) — otro ajuste de configuración del repositorio, no solo de código,
que sumaría un tercer cambio a aprobar. El diseño de arriba (`--watch` +
`--fail-fast` antes del merge normal) consigue el mismo bloqueo sin tocar
esa configuración.

**No se ha aplicado ninguno de los dos cambios** (ni el `gh api` de
protección ni el diff de `merge_pr()`) en esta tarea — quedan listos para
que quien revise este PR decida y los aplique, o encargue una tarea de
seguimiento que ya lo haga con `allow_infra_apply`-equivalente para cambios
de proceso (branch protection) y un PR normal `force: false` para el
cambio de código (`merge_pr()` sí es código de este repositorio y podría
implementarse en una tarea futura ya con la decisión tomada).

## Restricciones respetadas

- Ningún cambio real aplicado a la configuración de GitHub (`branch
  protection`, `allow_auto_merge`) — solo lectura (`gh api ... GET`) para
  verificar el estado de partida.
- Ningún cambio a `tasks/scripts/gh_git.py`/`agent_loop.py` — el diseño
  queda documentado, no aplicado, para no alterar sin aprobación el
  comportamiento del demonio para tareas `force: true` ya en cola.
- No se ha tocado `.github/workflows/ci.yml` (el propio enunciado señala
  que no debería hacer falta, y esta auditoría confirma que el workflow en
  sí está bien construido — el problema es que nada lo conecta al merge).

## Relevante para tareas futuras

- Decisión pendiente de aprobación humana, con las dos recomendaciones ya
  documentadas arriba: activar branch protection (`tests` + `terraform`
  como checks requeridos) y hacer que `merge_pr()` espere a los checks
  antes de fusionar en tareas `force: true`.
- Si se aprueba activar branch protection primero, sin haber aplicado
  todavía el cambio de `merge_pr()`: cualquier tarea `force: true` en cola
  dejará de auto-fusionarse de verdad hasta que se aplique también la
  Recomendación 2 — no es un fallo del sistema (`tasks/README.md` ya
  documenta ese caso, el PR queda en `in_review` para merge manual), pero
  sí cambia el comportamiento esperado del pipeline y conviene aplicar
  ambos cambios juntos o en sucesión rápida, no dejar el primero aplicado
  mucho tiempo sin el segundo.
- El comando de branch protection de arriba es un punto de partida
  razonable, no la única configuración válida — en particular, revisar si
  se quiere `enforce_admins=true` y/o `strict=true` antes de aplicarlo tal
  cual.

## Aplicado (29/8, sesión interactiva)

### Recomendación 2 — `merge_pr()` espera a la CI  ✅ en código

`tasks/scripts/gh_git.py`: nuevo `_wait_for_checks()` que corre
`gh pr checks <n> --watch --fail-fast` (tope `GH_CHECKS_TIMEOUT_SECONDS`,
por defecto 900 s; un `TimeoutExpired` se reconvierte a `GitError`).
`merge_pr()` lo llama **antes** del `gh pr merge`. Si un check falla o no
termina a tiempo, lanza `GitError` — que `agent_loop.py` ya trata como
cualquier fallo de merge: el PR se queda en `in_review` para merge manual y
se reintenta en ciclos posteriores. Config nueva
`gh_checks_timeout_seconds` en `agent_loop.Config` + `config.example.env`.
3 tests en `tasks/scripts/tests/test_gh_git.py` (orden checks→merge, no
fusiona con CI roja, timeout→`GitError`). **Nota de despliegue**: el proceso
del demonio en EC2 es un `while True` de larga vida; recogerá este cambio
solo tras reiniciarlo (`systemctl restart` de su unit) — hasta entonces
sigue con el `merge_pr()` viejo.

### Recomendación 1 — branch protection en `main`  ✅ aplicada

El comando `-f`/`-F` que había diseñado la tarea autónoma **da 422**: `gh
api -f` manda todo como string y la API exige un booleano real en
`strict`. Lo que funcionó fue mandar el cuerpo como JSON por stdin:

```bash
gh api -X PUT repos/madrono-ucm/madronoTFM/branches/main/protection \
  -H "Accept: application/vnd.github+json" --input - <<'JSON'
{
  "required_status_checks": { "strict": false, "contexts": ["tests", "terraform"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
JSON
```

Estado tras aplicarlo (`GET .../protection`): `contexts=["tests","terraform"]`,
`strict=false`, `enforce_admins.enabled=false`, sin
`required_pull_request_reviews`.

`tests` + `terraform` pasan a ser checks requeridos para fusionar en `main`.
Parámetros según lo recomendado arriba: `strict=false` (menos fricción,
fácil de endurecer), `enforce_admins=false` (un admin puede fusionar en una
emergencia; y — mientras el demonio no se haya reiniciado con la Rec. 2 —
sus tareas `force: true` que son admin siguen pudiendo auto-fusionarse; en
la práctica no había ninguna `force: true` en vuelo al aplicarlo: la 104 es
`force: false` y la 105 estaba `pending`). Sin `required_pull_request_reviews`
(el hallazgo es sobre CI, no sobre exigir revisión humana).

### Pendiente (no bloqueante)

- Reiniciar el demonio en EC2 para que use el nuevo `merge_pr()`.
- Cuando eso esté hecho y estable, valorar `enforce_admins=true` para que la
  protección aplique sin excepción.
