---
kind: fil
title: "CI de frontend: job de Node + guard de «ningún control sin handler» en las páginas generadas"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_57]
milestone: "M7"
target: "2026-09-13"
---

## Motivación (pedido del usuario)

El usuario reporta «hay muchos botones que no hacen nada» en la parte de
aplicación. Auditado el código el 2026-09-10: **en el fuente los tres
frontends sí tienen los handlers cableados** (`viz/mapa/index.html`,
`viz/grafo_explorador*.html`, `web/index.html`). El problema real es que
**no hay red de seguridad automática** que lo mantenga así:

- `.github/workflows/ci.yml` solo tiene los jobs `tests` (pytest) y
  `terraform`. **No hay ningún paso de Node.** `viz/test/mapa.test.mjs`
  (jsdom, FIL_69) y el `node --check` del JS generado (FIL_57) **nunca
  corren en CI** — solo si alguien los lanza a mano en local.
- Nada impide que un `<button>` nuevo se quede sin `onclick`, que un
  `getElementById` apunte a un id que ya no existe, o que el JS embebido
  (un string de ~1000 líneas en cada `build_*.py`) deje de parsear.

## Alcance

1. **Job `frontend` nuevo en `ci.yml`**
   - `actions/setup-node@v4` (Node 20), `npm ci` en `viz/` (ya hay
     `package.json` + `package-lock.json`).
   - `node --check` sobre el JS `<script>` inline de `viz/mapa/index.html`,
     `viz/grafo_explorador.html`, `viz/grafo_explorador_live.html` y
     `web/index.html`. **Reutilizar el extractor de FIL_57** (el que ya
     separa el inline del mapa), no duplicarlo — moverlo a
     `viz/test/_extraer_js.mjs` si hace falta y que lo importen ambos.
   - `node --test viz/test/` (recoge `mapa.test.mjs` y los nuevos de abajo).

2. **Guard «sin controles muertos»** — un test jsdom por página
   (`viz/test/mapa.test.mjs` ampliado + `viz/test/explorador.test.mjs` +
   `viz/test/web.test.mjs`):
   - Monta el DOM real de la página y ejecuta su bootstrap
     (`mkControls()/mkChat()/…` en el mapa; `arrancar()` en el explorador;
     el listener de `DOMContentLoaded` en `web/`), con `fetch` mockeado.
   - Para cada `<button>`, `<input>` y `<select>` que tenga `id` **o** esté
     dentro de un contenedor de control conocido (`#controls`, `#rail`,
     `#menu`, `#capas`, `#suggestions`, `#composer`, `#hist-caps`,
     `#chat-sug`): afirma que tiene **al menos un listener** (contador
     sobre `addEventListener` vía shim, o `onclick`/`onchange`/`onsubmit`
     asignado). Si no, el test **falla nombrando el id/selector** del
     control.
   - Los botones creados dinámicamente (`.day`, `.met`, `.pf`, `.hz`,
     `.rp`, capítulos, chips de sugerencia, checkboxes de capas del
     explorador) se comprueban **después** de ejecutar el bootstrap.

3. **Inventario declarativo** — `viz/CONTROLES.md` (tabla) o
   `viz/test/controles.json`: por página, cada control con su **acción
   esperada** en una frase. El guard lo cruza: además de «tiene handler»,
   dispara el control con un `MouseEvent`/`Event` sintético y afirma que
   **no lanza** y que toca el `state`/DOM esperado (p. ej. «`#v3d` deja
   `state.view.pitch > 0`»). Sirve también de documentación viva de la UI.
   Este mismo arnés es donde vive el test de **FIL_94** (recorrer todas las
   combinaciones métrica × escala × representación × perfil sin excepción y
   con un presupuesto de coste por render).

4. **`web/` bajo test** — hoy no lo cubre nada. Con (2)/(3) queda cubierto
   el cableado; el comportamiento de red va en FIL_92.

## Fuera de alcance

- ESLint completo y extracción de módulo JS compartido → **FIL_75**.
- Playwright / navegador real en CI (lento, flaky sin `xvfb`); sigue siendo
  paso manual/local antes de publicar (FIL_74).
- Cambiar la UI: este ticket solo añade la red de seguridad.

## Verificación

- Quitar el `onclick` de cualquier botón de `viz/mapa/index.html` (o de su
  generador) → job `frontend` **en rojo**, con el id del botón en el
  mensaje del test.
- Meter un `}` de más en el JS embebido de un generador → `node --check`
  **en rojo**.
- Renombrar un id en el HTML sin tocar el JS que lo busca → el guard de (3)
  falla al disparar ese control.
- El job `frontend` completo corre en < 2 min y es obligatorio en cada PR.

## Prioridad

**Alta, hacer primero (con FIL_93).** Es barato (~medio día), no depende de
nada y **protege el trabajo de FIL_71/72/73/74/75**: cualquier regresión de
cableado que introduzcan sale en CI en vez de en la demo.
