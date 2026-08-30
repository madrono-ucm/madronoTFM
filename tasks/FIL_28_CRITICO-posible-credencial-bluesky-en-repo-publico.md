---
kind: fil
title: "CRÍTICO — posible credencial real de Bluesky (app password) en un fixture de test, en repo público"
owner: Filippos (interactive)
status: in_progress
allow_infra_apply: false
created_at: "2026-08-30"
priority: critica
---

## Estado (2026-08-30)

**Hecho (código, en HEAD):**
- Fixture `ingesta/tests/test_bluesky_menciones_madrid.py` saneado:
  `identifier="cuenta-test.bsky.social"`, `app_password="aaaa-bbbb-cccc-dddd"`
  (el test mockea `requests.post` — el valor nunca toca la red). 12 tests en
  verde.
- El valor real redactado también en este ticket y en `doc/VIC-19-...md`.
- Confirmado que `pc6y-...` ya **no aparece en el working tree**.
- Ítem 4: `EMT_API_PASSWORD` sólo aparece como **nombre de variable** en
  docs, nunca con valor — es un placeholder de plantilla, sin fuga.

**Pendiente — requiere acción/decisión humana (no automatizable):**
1. **ROTAR ya** la App Password de `madrono97.bsky.social` en Bluesky
   (Configuración → Contraseñas de aplicación → revocar `pc6y-...` → generar
   una nueva) y actualizar el parámetro SSM
   `/madrono-tfm/dev/secrets/bluesky-app-password`
   (`aws ssm put-parameter --name /madrono-tfm/dev/secrets/bluesky-app-password
   --type SecureString --overwrite --value <nueva>`). El valor sigue en el
   historial público (`a1b8f61`), así que sanear HEAD **no** lo neutraliza.
2. **Decidir si se reescribe el historial** de git (`git filter-repo` /
   BFG). Afecta a todo clon/fork del repo público — decisión mayor. Dado que
   la credencial se rota (paso 1), reescribir el historial es defensa en
   profundidad, no urgente; se documenta la decisión aquí.

> **Contexto**: encontrado en `VIC_19` (auditoría de seguridad dedicada,
> `doc/PLAN-EVALUACION-TECNICA-2.md`), haciendo `git log --all -p | grep`
> de patrones de credenciales sobre todo el historial del repo.

## Qué se encontró (verificado, no se ha intentado usar la credencial)

`ingesta/tests/test_bluesky_menciones_madrid.py` (presente en el
**working tree actual**, líneas 137-138 y 177) tiene:

```python
identifier="madrono97.bsky.social",
app_password="pc6y-••••-••••-•••• (redactado)",
```

Dos motivos de alarma:

1. **`madrono97.bsky.social` parece ser la cuenta real de Bluesky del
   propio proyecto** (coincide con el naming del proyecto "Madroño"), no
   un identificador claramente ficticio (`user@example.com`, `test123`, etc).
2. **`pc6y-••••-••••-•••• (redactado)` tiene exactamente el formato real de un "App
   Password" de Bluesky** (4 grupos de 4 caracteres alfanuméricos en
   minúscula separados por guiones — el formato que Bluesky genera de
   verdad para sus App Passwords, distinto de una contraseña de usuario
   normal).

**El repositorio es público** (`gh api repos/madrono-ucm/madronoTFM` →
`"private": false, "visibility": "public"`). Si esta credencial es real y
sigue activa, está expuesta a cualquiera en internet ahora mismo, y lleva
así desde el commit `a1b8f61` (PR #177, "fix(bluesky): autenticar
searchPosts") — ese mismo commit dice explícitamente "Verificado
end-to-end contra Bluesky real: 25 registros", es decir, en algún momento
sí se usó una credencial real de Bluesky para verificar el fix; no está
confirmado si ESTE valor concreto es esa credencial real filtrada por
accidente en el fixture, o un valor inventado con formato realista para
el test (el mismo PR, en su segundo commit, sí dice explícitamente
"env vars ficticias" para *otro* fixture del mismo cambio — no da la
misma garantía para este).

**No se ha intentado autenticar contra la API real de Bluesky con esta
credencial** — sería un uso no autorizado de un servicio de terceros con
una cuenta que no es mía, incluso con fines de verificación, y no es
necesario para reportar el hallazgo.

## Qué hacer — inmediato, independientemente de si se confirma que es real

1. **Rotar la contraseña de aplicación de la cuenta `madrono97.bsky.social`
   en Bluesky ahora mismo** (Configuración → Contraseñas de aplicación →
   revocar la actual → generar una nueva), **sin esperar a confirmar si el
   valor concreto del fixture es el real** — el coste de rotar una
   credencial que resulta no ser la comprometida es cero; el coste de no
   rotar una que sí lo es no lo es.
2. Sustituir el fixture del test por un valor obviamente ficticio (p. ej.
   `identifier="cuenta-test.bsky.social"`, `app_password="aaaa-bbbb-cccc-dddd"`)
   — el test mockea `requests.post`, así que el valor nunca toca la red
   real; no hace falta que tenga un formato válido.
3. **Decidir si hace falta reescribir el historial de git** (el valor
   sigue en los commits `f4548c2`/`a1b8f61` aunque se corrija el HEAD
   actual) — esto es una decisión mayor (afecta a cualquier clon/fork ya
   existente del repo público) que requiere aprobación humana explícita,
   no se hace aquí ni se recomienda sin más contexto sobre quién más tiene
   clones del repo.
4. Revisar si `EMT_API_PASSWORD="tu-contraseña"` (visto en el mismo grep,
   en un fichero de ejemplo/documentación) es solo un placeholder de
   plantilla — parece serlo por el texto literal en español, pero
   confirmarlo de pasada ya que se está revisando esta zona.

## Restricciones

- No se ha tocado ningún fichero de código en este ticket — solo lectura
  (`git log --all -p`, `gh api`).
- No se ha intentado autenticar contra Bluesky con la credencial
  encontrada.

## Criterios de aceptación

- Contraseña de aplicación de `madrono97.bsky.social` rotada.
- Fixture del test reemplazado por un valor ficticio.
- Decisión explícita (documentada) sobre si se reescribe el historial de
  git público.
