# Contexto acumulado del proyecto

Esta carpeta la mantiene el propio `madrono-agent` (ver `tasks/scripts/`), no se
edita a mano. Por cada tarea de `tasks/` que se completa, `claude` escribe (como
parte de sus propios commits, revisados en el mismo PR que el código) un resumen en
`doc/NNN-slug.md` — el mismo `NNN-slug` que la tarea que lo originó — explicando qué
se implementó, por qué, y cualquier decisión relevante.

Como cada tarea se ejecuta en una sesión de `claude` completamente nueva (sin memoria
de sesiones anteriores), el contenido de esta carpeta es lo que le da continuidad al
proyecto: antes de implementar una tarea nueva, el demonio le pasa a `claude` el
contenido de todos los `doc/*.md` ya mergeados en `main` como contexto acumulado.

No confundir con `/documents`: esa carpeta es para la documentación oficial del TFM
(memoria, propuesta...) escrita por personas; esta (`/doc`) es la bitácora que genera
el propio pipeline automáticamente, una entrada por tarea completada.
