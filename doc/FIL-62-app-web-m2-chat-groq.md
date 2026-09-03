# FIL_62 (M2) — chat en lenguaje natural (Groq) + frontend en S3/CloudFront

Ejecutado 2026-09-02, sobre el despliegue real de `FIL_63` (M1). Verificado
en vivo contra `https://35-42-164-183.nip.io` (backend, IP real
`35.42.164.183`) y `https://d2obcdu8duk47f.cloudfront.net` (frontend), no
solo en local.

## Qué se hizo

1. **Orquestación de chat** (`asistente/chat.py`): un turno de conversación
   llama a Groq (SDK oficial, API compatible con OpenAI/`tool_use`) con las
   14 tools de `asistente/mcp_agent/tools.py` como `tools=[...]`. Groq elige
   qué tool(s) llamar; se ejecutan en proceso (mismas funciones que usan
   MCP/HTTP, sin pasar por la red) y el resultado vuelve a Groq para
   redactar la respuesta final en prosa. Descripciones cortas por tool
   escritas a mano (para no gastar la mayor parte del presupuesto de TPM del
   tier gratuito en los docstrings completos de MCP, ~2.000
   caracteres/tool), pero el `input_schema` real de cada tool se toma en
   vivo de `mcp.list_tools()` — una sola fuente de verdad para los
   parámetros, sin duplicarlos a mano.
2. **Endpoint** `POST /chat` (`asistente/routers/chat.py`), montado en
   `asistente/main.py`. Recibe `{mensaje, historial}`, devuelve
   `{respuesta, historial}` — el cliente solo guarda y reenvía el
   `historial` tal cual, no necesita entender su estructura interna.
3. **CORS** (`CORSMiddleware` en `asistente/main.py`): necesario porque el
   frontend (S3/CloudFront) y el backend (EC2) viven en orígenes distintos.
   Abierto a cualquier origen — no hay estado de sesión/cookies que
   proteger, el auth real sigue siendo Basic Auth de nginx delante del
   backend (`FIL_63`), reenviado como header real en cada `fetch()` del
   frontend, no un gate cosmético aparte.
4. **Clave de Groq**: leída de SSM `SecureString`
   (`/madrono-tfm/dev/secrets/groq-api-key`, guardada en `FIL_62` inicial),
   con `GROQ_API_KEY` de entorno como prioridad para tests/desarrollo local.
5. **Frontend** (`web/index.html`, HTML/JS vanilla autocontenido, sin build
   step ni framework — mismo criterio ya aplicado en `viz/mapa/`): pantalla
   de login (usuario/contraseña de demo, valida contra `/health` con Basic
   Auth real, guarda en `sessionStorage`) + pantalla de chat (burbujas,
   sugerencias, envío). Subido a S3 (`madrono-tfm-dev-web-222234418587`,
   bucket privado, SSE) y servido por CloudFront
   (`d2obcdu8duk47f.cloudfront.net`) vía **Origin Access Control** (OAC) —
   solo esa distribución concreta puede leer el bucket (`AWS:SourceArn`
   restringido en la bucket policy), sin acceso público directo a S3.

## Tres bugs reales encontrados y arreglados en el camino

- **Modelo de Groq deprecado**: `llama-3.3-70b-versatile` (elegido en el
  encuadre original de `FIL_62`) devolvía `404 model_not_found` en la
  primera llamada real — ya no estaba en el catálogo de Groq. El catálogo
  gratuito de Groq rota; confirmado en vivo con `client.models.list()`
  (activos hoy: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `groq/compound`, `qwen/qwen3.6-27b`, `allam-2-7b`, entre otros). Cambiado
  a `openai/gpt-oss-120b` — mismos límites de tier gratuito, tool-calling
  real. Ver `FIL_62` para la nota de seguimiento.
- **CORS preflight bloqueado por Basic Auth de nginx**: la primera
  verificación real del frontend contra el backend (`OPTIONS /chat` con
  cabeceras `Origin`/`Access-Control-Request-*`, como hace un navegador
  real antes de un `POST` cross-origin) devolvía `401` de nginx —
  `auth_basic` se aplicaba también al preflight, y los navegadores nunca
  envían credenciales en un preflight. Sin arreglar esto, **ningún mensaje
  de chat habría funcionado nunca desde el frontend real** (el `fetch()`
  del navegador falla el preflight antes de intentar el `POST`), pese a que
  el backend en sí funcionaba perfectamente probado con `curl`
  directamente. Arreglado en `/etc/nginx/sites-available/madrono-web` con
  un `map` que desactiva `auth_basic` solo para `OPTIONS`:
  ```nginx
  map $request_method $madrono_auth_basic {
      OPTIONS "off";
      default "Madrono TFM -- acceso demo";
  }
  # ...
  auth_basic $madrono_auth_basic;
  ```
  Así el preflight llega sin auth hasta el `CORSMiddleware` de FastAPI, que
  ya sabe responder un preflight correctamente (cabeceras
  `Access-Control-Allow-*`) — evita duplicar la lógica CORS a mano en
  nginx. El `POST` real (con credenciales) sigue pasando por `auth_basic`
  con normalidad.
- **Certificado autofirmado bloqueaba el login en silencio** (reportado
  por el usuario tras el primer despliegue): el login (`demo`/`demo`) daba
  siempre "usuario o contraseña incorrectos" pese a ser correctas.
  Reproducido con Playwright (Chromium real, headless) contra la URL
  pública de CloudFront: la petición `fetch()` a
  `https://35.42.164.183/health` fallaba con
  `net::ERR_CERT_AUTHORITY_INVALID` — un error de red, no de credenciales,
  que el `catch` del login traducía (incorrectamente) en "usuario o
  contraseña incorrectos". A diferencia de navegar directamente a la IP
  (donde el navegador muestra un aviso clicable para aceptar el
  certificado), un `fetch()` en segundo plano contra un certificado no
  confiable falla sin ninguna forma de que el usuario lo acepte —
  **el bug era inherente a tener el frontend en un origen distinto**, no
  visible al probar M1 con `curl -k` o navegando a la IP directamente.
  Arreglado obteniendo un **certificado real de Let's Encrypt**: como
  Let's Encrypt exige un nombre DNS (no una IP desnuda) y esta EC2 no
  tiene dominio propio, se usó `nip.io` (servicio DNS comodín público y
  gratuito: `35-42-164-183.nip.io` resuelve a `35.42.164.183` sin
  necesidad de configurar nada) — mismo IP, cero coste, cero
  infraestructura nueva. `certbot certonly --webroot` (sin parar nginx,
  con una `location /.well-known/acme-challenge/` añadida al bloque del
  puerto 80) emitió el certificado; `web/index.html` y toda la
  documentación se actualizaron para usar `https://35-42-164-183.nip.io`
  en vez de la IP. Verificado con Playwright tras el fix: login y un
  turno de chat completo funcionan de principio a fin contra la URL
  pública real.

## Verificado en vivo (no solo en local)

- `OPTIONS /chat` con `Origin` de CloudFront → `200`, con
  `access-control-allow-origin`/`-methods`/`-headers` correctos, sin pedir
  credenciales.
- `POST /chat` con `demo:demo` + `Origin` de CloudFront → `200`, respuesta
  real de Groq tras un tool-call real (`trafico_cercano`); degrada con
  elegancia («no he podido obtener datos») cuando la tool subyacente falla
  por la limitación de Neo4j ya documentada en `FIL_63` — a diferencia de
  algunas tools que daban `500` crudo llamadas directamente por HTTP,
  `chat.py` envuelve *toda* ejecución de tool en un `try/except` propio, así
  que el chat nunca revienta aunque la tool sí lo haría por HTTP directo.
- `GET /` sin credenciales → sigue devolviendo `401` (confirma que el
  `map` no debilitó el auth para peticiones normales, solo `OPTIONS`).
- `https://d2obcdu8duk47f.cloudfront.net/` → `200` (frontend real servido
  desde CloudFront).
- Distribución CloudFront confirmada en estado `Deployed` antes de dar la
  verificación por válida (una distribución `InProgress` puede servir
  contenido desactualizado o dar error intermitente).

## Qué queda pendiente (fuera de alcance de M1/M2)

- Infraestructura de S3/CloudFront/certificado aplicada a mano vía AWS CLI
  y `certbot`, no en Terraform — mismo criterio ya asumido para la EC2 en
  `FIL_63` (esta parte del proyecto no está gestionada por Terraform);
  queda como gap conocido, no bloqueante para la demo. `certbot` sí dejó
  configurada la renovación automática del certificado.
- `nip.io` es un servicio DNS público de terceros fuera del control del
  proyecto — si algún día deja de resolver, el certificado y el `API` del
  frontend habría que moverlos a un dominio propio real.

## Seguimiento (2026-09-03): "el asistente no funciona como se esperaba"

El usuario probó el chat en vivo y reportó dos ejemplos concretos.
Investigado contra el backend real, no supuesto:

1. **"¿Hay alguna actividad interesante en el centro hoy?" → "No he
   podido obtener información de eventos".** Causa real: la limitación de
   Neo4j de `FIL_63` (arriba) seguía sin resolver -- `eventos_cercanos`
   fallaba con `KeyError: 'NEO4J_URI'`. **Arreglado**: el acceso a los
   parámetros SSM de Neo4j (bloqueado en sesiones anteriores) cambió;
   ahora `/opt/start-madrono-web.sh` (en la EC2, no en el repo) los lee de
   SSM `SecureString` en caliente al arrancar `madrono-web.service` y los
   exporta como `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/
   `NEO4J_DATABASE` -- nunca en claro en disco, mismo patrón que
   `groq-api-key`. Verificado con una conexión Neo4j real (586 `:Lugar`,
   4702 `:EstacionMedida{tipo:'trafico'}`, 101.716 relaciones
   `PROXIMO_A`) y con el endpoint real ya sin el `KeyError`.
2. **"¿Qué pelis me recomiendas ver hoy?" → rechazo genérico.** No es un
   bug: Madroño solo tiene tools de tráfico/aire/ruido/movilidad/eventos
   de Madrid, así que declinar es el comportamiento esperado dado el
   `_SYSTEM_PROMPT`. La redacción exacta del rechazo varía entre
   ejecuciones (el modelo no es determinista al 100 % con
   `temperature=0.2`), pero el efecto -- no llamar a ninguna tool y
   explicar que está fuera de alcance -- es correcto.

**Bug real encontrado durante la investigación, no reportado por el
usuario pero descubierto al reproducir el caso 1**: una vez arregladas
las credenciales de Neo4j, `trafico_cercano` seguía respondiendo "no se
ha encontrado ningún lugar" para lugares que **sí existen** en el grafo
(verificado: "Puerta del Sol" resuelve 6 estaciones de tráfico reales a
&lt;300m). Causa: el pipeline de ingesta está deliberadamente congelado
desde `2026-08-30` (verificado contra Athena: `max(date)` de
`gold.trafico_por_punto_hora` para esas estaciones es exactamente esa
fecha), así que una consulta "de hoy" (`2026-09-04`) nunca encuentra fila
en Gold -- comportamiento esperado dado el estado del proyecto. Pero el
router (`asistente/routers/trafico_cercano.py`) usaba el mismo mensaje
para "no se encontró ningún lugar/estación" y para "se encontró el lugar
pero no hay dato para esa fecha", dando a entender (falsamente) que el
lugar no se había reconocido. Arreglado separando ambos casos en mensajes
distintos, con test de regresión
(`test_lugar_con_estaciones_pero_sin_dato_de_gold_no_dice_que_no_encontro_el_lugar`).
Verificado en vivo: con `momento` dentro de la ventana real de datos
(`2026-08-30T09:00:00`), la misma consulta a "Puerta del Sol" devuelve
tráfico real ("fluido", intensidad y nivel de servicio reales de la
estación `10608`).

## Acceso

- Frontend: `https://d2obcdu8duk47f.cloudfront.net` — usuario `demo`,
  contraseña `demo`.
- Backend directo (Swagger, `/docs`): `https://35-42-164-183.nip.io` —
  mismas credenciales, certificado real de Let's Encrypt (sin aviso de
  navegador).
