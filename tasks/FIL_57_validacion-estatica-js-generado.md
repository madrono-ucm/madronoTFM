---
kind: fil
title: "Mapa animado — validación estática del JS generado en el build (node --check + lint del _TEMPLATE)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
depends_on: [FIL_55]
---

## Contexto

El mapa se genera desde un literal de cadena de ~700 líneas
(`_TEMPLATE` en `viz/build_mapa_animado.py`) que contiene todo el JS y el
CSS de la interfaz. **Nada comprueba ese JS**: ni sintaxis, ni variables
sin usar, ni referencias a identificadores inexistentes. Un error de
tecleo en el template produce un `index.html` roto que se publica igual
(los tests solo miran `assertIn` de subcadenas).

## Objetivo

Que el build falle —y por tanto CI— si el JS generado no es válido.

1. En `viz/build_mapa_animado.py::main()` (o un `check()` aparte), tras
   generar el HTML: extraer el bloque `<script>` inline y pasarlo por
   `node --check` (solo sintaxis, sin ejecutar). Si `node` no está
   disponible, avisar y no romper (el build sigue siendo reproducible sin
   node), pero en CI sí exigirlo.
2. Añadir un lint mínimo con una config acotada (p. ej. `eslint` con
   `no-undef`, `no-unused-vars`, `no-undef` sobre los globals de `deck` /
   `maplibregl` declarados) sobre ese mismo bloque. Alternativa sin npm:
   un chequeo casero en Python que verifique que cada `document.getElementById("x")`
   tiene su `id="x"` en el HTML y viceversa (cazaría la clase de bug de
   `FIL_47`, el `onClick` perdido).
3. `tests/test_mapa_animado.py`: un test que invoque ese check sobre el
   `index.html` del repo y falle si el JS no pasa.
4. Job de CI: `node --check` sobre el `index.html` publicado en `viz/mapa/`.

## Criterios de aceptación

- Introducir a mano un error de sintaxis en el `_TEMPLATE` → el build o el
  test lo detecta (no llega a publicarse).
- El chequeo id-HTML ↔ `getElementById` pasa hoy y falla si se borra un
  `id` referenciado.
- CI en verde con el check añadido.

## Restricciones

- El build tiene que seguir funcionando sin `node` instalado (solo avisa);
  la exigencia dura es en CI.
- No reescribir el `_TEMPLATE` para "hacerlo lintable" más allá de lo
  imprescindible.
