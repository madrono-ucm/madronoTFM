---
kind: fil
title: "Web (web/index.html): estados carga/error/vacío reales, endpoint configurable y a11y mínima"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_63, FIL_91]
milestone: "M7"
target: "2026-09-16"
---

## Motivación

**FIL_75 acota su alcance a los dos generadores de `viz/`** (mapa animado +
explorador). La landing `web/index.html` (S3/CloudFront, FIL_62/63) — la
puerta «producto», la que ve un tribunal por el enlace — se queda fuera.
Auditada el 2026-09-10, tiene aristas de acabado impropias de una demo de
entrega:

- **`const API = "https://35-42-164-183.nip.io"` hardcodeado.** No hay
  `?api=` ni variable ni `<meta>`. Si la EC2 cambia de IP hay que editar el
  HTML y re-desplegar a S3. No se puede apuntar a un backend local para
  probar sin tocar el fichero.
- **El chat solo distingue dos casos**: `try` OK y `catch` genérico («No se
  pudo contactar con el asistente…»). Un 500 del backend, un 429 de Groq
  (tier gratuito, 12k TPM — pasa), un timeout y un `{respuesta: null}`
  acaban todos en el mismo texto o en «(sin respuesta)».
- **`demo` / `demo` a la vista** en el formulario, sin decir en la página
  que no es seguridad real (lo dicen la memoria y el README, no la UI que
  ve el usuario).
- **a11y**: el botón de enviar es `➤` sin `aria-label`; `#msgs` no es
  `aria-live`, así que un lector de pantalla no anuncia la respuesta; el
  foco no se gestiona al añadir mensajes; el único estado de «enviando» es
  `input.disabled` (sin texto ni spinner); no hay `:focus-visible`
  consistente.

## Alcance

1. **`API` configurable** — resuelto en orden: `?api=<url>` de la query →
   `<meta name="madrono-api" content="…">` → el valor por defecto actual
   (documentado en comentario). Nada más cambia.
2. **Estados explícitos del chat**, con el **mismo patrón y textos** que
   FIL_75 fijará para `viz/` (coordinar el naming): `enviando` (spinner +
   texto), `error de red`, `error del backend` (muestra el código HTTP +
   botón «Reintentar» que reenvía el último mensaje), `rate-limit` (detecta
   429 → «Vuelve a intentarlo en unos segundos»), `respuesta vacía`. Un
   helper único `estadoMensaje(tipo, detalle)`.
3. **Login** — mensajes distintos para: 401 (usuario/contraseña), backend
   caído / timeout, y fallo de CORS/certificado (`TypeError` de `fetch`).
   Botón deshabilitado + texto «Comprobando…» mientras valida.
4. **Nota de honestidad** bajo el formulario: «Acceso de demostración — no
   es seguridad real (credencial fija). Todos los datos servidos son
   abiertos y sin información personal.»
5. **a11y mínima** (no auditoría completa): `aria-label` en `➤`;
   `role="log"` + `aria-live="polite"` en `#msgs`; mover el foco al último
   mensaje respetando `prefers-reduced-motion`; `:focus-visible` visible en
   todos los controles; contraste AA en textos y placeholders; `<label>`
   asociado a `#u`/`#p`/`#input` (o `aria-label`).
6. **Test** (jsdom, en el `viz/test/` nuevo de FIL_91 o `web/test/`):
   `fetch` mockeado devolviendo 200 / 500 / 429 / rechazo de red → el hilo
   muestra el estado correcto, el botón «Reintentar» reenvía, y la UI nunca
   queda bloqueada (`input.disabled` siempre vuelve a `false`).

## Fuera de alcance

- Framework / router / sesión persistente real / rediseño visual.
- Tocar `asistente/` (el contrato de error del backend es FIL_71/73).
- Autenticación real (sigue siendo Basic `demo`/`demo` en nginx, FIL_63).

## Verificación

- `web/index.html?api=http://localhost:8000` habla con un backend local sin
  editar el fichero.
- Con el backend devolviendo 500, el chat muestra «error del backend (500)»
  + «Reintentar», no «(sin respuesta)».
- Con 429, muestra el texto de rate-limit, no el genérico.
- Recorrido de teclado completo (login → chat → sugerencias → salir) con
  foco visible en cada paso; VoiceOver/NVDA anuncia la respuesta del bot.
- El test nuevo cubre los 4 caminos de red y pasa sin conexión.

## Prioridad

**Media.** La landing funciona hoy para la demo; esto es acabado. Hacer
**después de FIL_74 (publicar) y FIL_71 (contrato de error)** para alinear
los textos de estado con los del backend y con `viz/`.
