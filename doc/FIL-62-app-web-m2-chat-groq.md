# FIL_62 (M2) — chat en lenguaje natural (Groq) + frontend en S3/CloudFront

Ejecutado 2026-09-02, sobre el despliegue real de `FIL_63` (M1). Verificado
en vivo contra `https://35.42.164.183` (backend) y
`https://d2obcdu8duk47f.cloudfront.net` (frontend), no solo en local.

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

## Dos bugs reales encontrados y arreglados en el camino

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

- Neo4j sin credenciales en el `systemd` (documentado en `FIL_63`) — sigue
  sin resolverse; afecta a las tools de grafo tanto por HTTP directo como
  por el chat.
- Certificado TLS real (Let's Encrypt) si se decide poner un dominio propio
  — hoy autofirmado en el backend; CloudFront sí sirve con certificado
  válido de AWS en su propio dominio `*.cloudfront.net`.
- Infraestructura de S3/CloudFront aplicada a mano vía AWS CLI, no en
  Terraform — mismo criterio ya asumido para la EC2 en `FIL_63` (esta parte
  del proyecto no está gestionada por Terraform); queda como gap conocido,
  no bloqueante para la demo.

## Acceso

- Frontend: `https://d2obcdu8duk47f.cloudfront.net` — usuario `demo`,
  contraseña `demo`.
- Backend directo (Swagger, `/docs`): `https://35.42.164.183` — mismas
  credenciales, certificado autofirmado (aviso de navegador esperado).
