# Tareas para el agente autónomo

Esta carpeta es la cola de trabajo de `madrono-agent`, el demonio que corre 24/7 en la
EC2 (ver `scripts/`). Cada archivo `.md` de esta carpeta (excepto `README.md` y
`_template.md`) es una tarea. El demonio las procesa **una a una y en orden estricto**,
según el prefijo numérico del nombre de archivo, y no empieza la tarea `NNN+1` hasta que
el Pull Request de la tarea `NNN` esté **fusionado** — por defecto, manualmente por un
humano; si la tarea tiene `force: true`, el propio demonio lo fusiona en cuanto lo crea
(ver [Auto-merge (`force`)](#auto-merge-force)).

## Cómo añadir una tarea

1. Copia `_template.md` a `NNN-slug-descriptivo.md`, donde `NNN` es el siguiente número
   de 3 dígitos libre (`001`, `002`, ...) y `slug-descriptivo` es un nombre corto en
   kebab-case. El número decide el orden de ejecución — es la única forma de expresar
   dependencias entre tareas. Comprueba también [`done/`](#tareas-completadas-done) al
   elegir el número: las tareas ya completadas se archivan ahí y no aparecen sueltas en
   `tasks/`, pero su número sigue "gastado".
2. Rellena el front-matter (`id`, `slug`, `title`) y dejalo con `status: pending`.
3. Escribe el cuerpo del archivo (todo lo que va después del `---` final) como el
   prompt que recibirá `claude`. Sé concreto: qué hay que implementar, criterios de
   aceptación, y cualquier restricción relevante. Además del encabezado con el título
   de la tarea, el demonio le añade automáticamente el contexto acumulado del
   proyecto — ver [`/doc`](../doc/README.md) — así que no hace falta repetir en cada
   tarea decisiones ya documentadas en tareas anteriores.
4. Haz commit y push del archivo normalmente (esto es trabajo interactivo tuyo, no del
   demonio). En su siguiente ciclo, el demonio lo recogerá si es la siguiente tarea en
   orden y todas las anteriores están en `status: done`.

## Formato del front-matter

```yaml
---
id: 1                    # entero, debe coincidir con el prefijo del nombre de archivo
slug: slug-descriptivo
title: "Título legible de la tarea"
status: pending           # pending | in_progress | in_review | blocked | failed | done
force: false               # true = fusiona el PR sin revisión humana (ver más abajo)
branch: null                 # rama creada por el demonio, p.ej. task/001-slug-descriptivo
pr_number: null
pr_url: null
attempts: 0                 # nº de intentos fallidos registrados (se usa para el backoff)
next_retry_at: null          # ISO-8601 UTC; solo se usa en status=blocked
last_error: null              # resumen corto del último fallo, para diagnóstico
created_at: null
updated_at: null
started_at: null               # cuándo pasó a in_progress por primera vez
submitted_at: null              # cuándo se creó el PR
merged_at: null
---
```

El demonio es el único que modifica estos campos una vez la tarea entra en curso; no
edites `status`, `branch`, `pr_number`, etc. a mano salvo para **desatascar** una tarea
en `failed` (vuelve a ponerla en `pending` tras arreglar lo que la bloqueó) — es la
única transición manual soportada.

## Ciclo de vida de una tarea

```
pending ──(el demonio crea rama + PR)──▶ in_review ──(alguien mergea el PR)──▶ done
   │                                         │
   └─(fallo tipo rate-limit/uso agotado)     └─(PR cerrado sin merge)──▶ failed
     blocked ──(pasa el tiempo de backoff)──▶ vuelve a intentarlo
   │
   └─(fallo duro, o terminó sin comitear nada)──▶ failed
```

Si una tarea queda en `failed`, el demonio **detiene toda la cola** (no toca tareas
posteriores) hasta que alguien revise `last_error` y la desatasque manualmente.

## Tareas completadas (`done/`)

En cuanto una tarea pasa a `status: done`, el demonio mueve su archivo de
`tasks/NNN-slug.md` a `tasks/done/NNN-slug.md` en el mismo commit que actualiza el
front-matter (git lo registra como un rename limpio). Así `tasks/` solo muestra lo que
todavía está pendiente o en curso, y `tasks/done/` sirve de archivo histórico — el
`id`/`slug` de una tarea archivada no se debe reutilizar para una tarea nueva.

## Auto-merge (`force`)

Con `force: true`, en cuanto el demonio crea el PR lo fusiona él mismo
(`gh pr merge --squash --delete-branch`) sin esperar a que nadie lo revise — la tarea
pasa de `in_review` a `done` en el siguiente ciclo, sin que la cola se quede parada
esperando una revisión manual. Si el auto-merge falla (por ejemplo, por protección de
rama), el PR se queda igualmente en `in_review` a la espera de un merge manual, como si
`force` no estuviera activo.

Úsalo con cuidado: te saltas la única red de seguridad real del sistema (que nada llega
a `main` sin que un humano lo revise antes). Tiene sentido para las primeras tareas del
proyecto (andamiaje, estructura de carpetas...) o para tareas sueltas sin dependientes
que confíes en revisar después con calma en vez de antes — no para tareas de las que
dependan otras posteriores importantes.

## Qué NO debe hacer una tarea

El demonio ejecuta `claude` con permisos totales y sin supervisión humana en tiempo
real (`--permission-mode bypassPermissions`). La única red de seguridad real es que
**nada llega a `main` sin pasar por un PR que un humano revisa y fusiona a mano**. Por
eso: evita tareas que por su naturaleza necesiten hacer cosas irreversibles o con
efectos fuera del propio repo (borrar infraestructura, rotar credenciales, publicar
paquetes, etc.) — resérvalas para hacerlas tú mismo de forma interactiva.
