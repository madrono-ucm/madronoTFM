---
kind: fil
title: "App web de Madroño — landing con acceso demo + chat con el asistente (encuadre)"
owner: propuesto por Claude (QA), sin asignar
status: done
resolved_at: "2026-09-02"
allow_infra_apply: false
created_at: "2026-09-02"
depends_on: []
---

## Qué es

Encuadre técnico a petición del usuario: una app web nueva con (1) un
landing sencillo protegido por usuario/contraseña de demo (`demo`/`demo`)
y (2) dentro, un chat contra el asistente Madroño, responsive
(móvil/escritorio). **No implementado aquí** — solo el encuadre para
decidir con criterio antes de tocar código.

## Lo que ya existe (verificado en el repo, no supuesto)

- **`asistente/main.py`**: app FastAPI real ya construida
  (`create_app()`), con **14 tools** montadas como routers HTTP
  (`asistente/routers/*.py` — un espejo REST 1:1 de las tools MCP:
  `calidad_aire`, `calidad_aire_prevista(_grafo)`, `trafico_cercano`,
  `trafico_prevista(_grafo)`, `ruta_saludable`, `contexto_urbano`,
  `mejor_hora_zona`, `afluencia_estimada/prevista`,
  `disponibilidad_aparcamiento`, `eventos_cercanos`, `opciones_movilidad`,
  `health`) y el propio servidor MCP montado vía `FastAPI.mount()`.
  Probada con tests reales (`asistente/tests/test_app.py`), pero
  **nunca desplegada en ningún sitio público** — no hay ningún
  `infra/terraform/*.tf` que la sirva; solo corre local/en tests.
- **No existe ninguna capa de chat en lenguaje natural**. Las tools
  devuelven respuestas estructuradas (Pydantic), pensadas para que las
  llame un cliente MCP externo (Claude Desktop, Claude API con
  tool-calling) — el propio `asistente/` no decide qué tool llamar a
  partir de una frase libre ni redacta una respuesta en prosa. "Chatear
  con Madroño" en el sentido que pide este ticket requiere **añadir esa
  pieza desde cero**, no está latente en el código actual.
- **No existe ningún frontend**: ni landing, ni HTML de chat, ni auth. El
  único frontend real del proyecto es el mapa animado
  (`viz/mapa/`, estático, sin backend propio, en `gh-pages`).
- **No hay CORS ni autenticación en `asistente/main.py`** hoy — si se
  expusiera tal cual, sería una API abierta.

## Decidido con el usuario (2026-09-02): LLM vía Groq, coste $0

Todo Madroño, hasta ahora, mantiene **coste cero real** (Free tier de
AWS/AuraDB, datos abiertos, sin claves de pago). Un chat en lenguaje
natural de verdad necesita un LLM que decida qué tool llamar y redacte la
respuesta — era la primera pieza del proyecto con riesgo de coste real
por mensaje. Se descartó auto-hospedar (Ollama) sobre la EC2 del daemon:
verificado en vivo que es una `t3.medium` (2 vCPU / 4 GB) con solo ~1,4 GB
libres y ya usando swap — no hay margen para cargar inferencia ahí sin
arriesgar el propio daemon. Se aplica el mismo criterio ya usado para
elegir AuraDB Free sobre Neo4j autogestionado: una API gestionada con
tier gratuito real gana a auto-hospedar cuando existe.

**Elegido: Groq** (`https://console.groq.com`, API compatible con
OpenAI/`tool_use`). Verificado hoy, no supuesto:

- Tier gratuito permanente, **sin tarjeta de crédito**, sin lista de
  espera — alta con email en <60 s.
- Límites reales (por organización, no por API key):
  `llama-3.3-70b-versatile` → 30 RPM / **1.000 peticiones/día** / 12K TPM
  / 100K TPD. Sobra para una demo/defensa de TFM; no hace falta ningún
  presupuesto/freno adicional propio (`herramientas/costes/`-style) más
  allá de manejar con elegancia un `429` si algún día se agota.
- Sin API de *batch* en el tier gratuito — irrelevante aquí, el chat es
  interactivo, no por lotes.
- Modelo propuesto: `llama-3.3-70b-versatile` (tool-calling maduro, buen
  español, dentro del tier gratuito) — cualquier otro Llama del catálogo
  serviría igual de bien para este caso de uso, coherente con "el nivel
  del modelo no importa mucho" ya que el valor real está en los datos y
  las 14 tools, no en el modelo.

**Actualización (2026-09-02): la clave ya existe y está guardada.** El
usuario la generó (`madrono-groq` en la consola de Groq) y se guardó de
inmediato en SSM como `SecureString` en
`/madrono-tfm/dev/secrets/groq-api-key` — mismo patrón exacto que el
resto de secretos del proyecto (`ingesta/capturas/secretos.py`, `FIL_17`),
verificado que no se puede leer en claro sin `--with-decryption`. **Nota
de higiene**: la clave se pegó en texto plano en el chat de esta sesión
antes de guardarse — exposición real, igual de naturaleza que la de
`FIL_28`, aunque no en el repo. Queda a criterio del usuario rotarla en
`console.groq.com/keys` si le preocupa; no se ha hecho aquí. El valor
**no** se ha escrito en ningún fichero de este repositorio.

Cuando se implemente el endpoint de chat, falta añadir la política IAM
de `ssm:GetParameter` para este nuevo ARN al rol que sirva
`asistente/main.py` — mismo patrón que
`madrono-tfm-dev-ingestion-lambda-secrets` (`FIL_17`), ampliada o una
nueva política dedicada.

## Decidido con el usuario (2026-09-02): despliegue en la EC2 ya encendida

Se descarta Lambda+API Gateway — se aprovecha la EC2 del daemon,
consistente con el criterio de coste ya aplicado en todo el ticket. Datos
reales de esa instancia, verificados hoy (no supuestos):

- `i-0aa45f0df26b4b7e6`, `t3.medium`, región **`eu-south-2`** (no
  `eu-west-1`, donde vive el resto de la infraestructura del proyecto —
  cruce de región ya conocido de esta EC2, ver notas de entorno de
  sesiones anteriores).
- IP pública real: `35.42.164.183`. Sin dominio propio configurado hoy.
- Un único security group, `sg-0b9b20f616f30216e` (`launch-wizard-1` —
  nombre por defecto de la consola, esta EC2 no se gestiona por
  Terraform). Regla actual: **solo el puerto 22 (SSH) abierto a
  `0.0.0.0/0`** — nada de 80/443 todavía.
- A diferencia de auto-hospedar un LLM (descartado antes en este mismo
  ticket por falta de RAM), `uvicorn`+FastAPI es ligero — no debería
  competir de forma significativa con el daemon existente.

Esto deja el ticket de encuadre completo: **Groq + EC2 existente**, las
dos decisiones de coste/despliegue cerradas. Ver `FIL_63` para el primer
ticket de implementación (M1).

## Piezas que hacen falta (si se decide seguir adelante)

1. **Desplegar `asistente/main.py` en la EC2 del daemon** (decidido
   arriba): `systemd` + `uvicorn` + `nginx`/Caddy como proxy inverso (TLS
   + auth Basic ahí mismo, ver punto 3). Hace falta abrir el security
   group `sg-0b9b20f616f30216e` a 443 (y 80 si se usa Let's Encrypt/ACME
   para el certificado — necesita un dominio propio apuntando al
   `35.42.164.183`, o un certificado autofirmado como alternativa más
   barata pero con aviso del navegador). Ningún `.tf` la sirve hoy —
   como el resto de esta EC2 no está gestionada por Terraform, lo más
   consistente es aplicar el cambio de SG y el `systemd`/`nginx` a mano
   (mismo criterio que el resto de la operación de esta instancia), no
   forzar un `aws_security_group` nuevo por Terraform para un recurso que
   ni siquiera está importado.
2. **La capa de chat/orquestación** (nueva) — endpoint nuevo (p. ej.
   `POST /chat`) que reciba el mensaje, llame a Groq
   (`llama-3.3-70b-versatile`) con `tool_use` sobre las 14 tools ya
   expuestas por HTTP, ejecute la(s) tool(s) que el modelo elija, y
   devuelva la respuesta en prosa que redacte Groq a partir del
   resultado. Cliente Groq vía su SDK Python (compatible con el SDK de
   OpenAI) o llamada HTTP directa — a decidir en el ticket de
   implementación, no aquí.
3. **Autenticación de demo** (`demo`/`demo`): lo más barato y simple es
   **HTTP Basic Auth a nivel del proxy** (nginx/Caddy), cero código en la
   app. Importante dejarlo explícito en la propia UI y en la memoria:
   **esto no es seguridad real** (credencial fija, sin límite de
   intentos, sin cifrado propio más allá de TLS) — aceptable solo porque
   los datos son 100 % abiertos y sin PII, exactamente para mantener
   fuera de un enlace público a buscadores/bots, no para proteger nada
   sensible.
4. **Frontend**: landing + pantalla de chat, responsive. Dado el
   precedente ya sentado por `viz/mapa/` (HTML/JS vanilla autocontenido,
   sin build step, testeado con `tests/test_mapa_animado.py` +
   Playwright para lo interactivo, ver `VIC_32`), lo más consistente con
   el resto del proyecto es la misma vía: sin framework (React/Vue
   añadiría una cadena de build nueva al repo) salvo que se prefiera
   explícitamente lo contrario.
5. **CORS** en `asistente/main.py` si el frontend y el backend no viven
   en el mismo origen.

## Qué NO cubre este encuadre

- No es una implementación — cero código, cero Terraform, cero
  despliegue real aplicado en este ticket. Las dos decisiones que
  bloqueaban el encuadre (coste del LLM → Groq; despliegue → EC2
  existente) quedaron cerradas arriba, con datos reales verificados
  (rate limits de Groq, IP/SG/región reales de la EC2).

## Restricciones

- Ticket de encuadre — sin código ni infraestructura aplicados aquí (la
  clave de Groq sí se guardó en SSM, ver arriba, pero es la única acción
  real de este ticket).
- La clave de API de Groq vive en SSM `SecureString`
  (`/madrono-tfm/dev/secrets/groq-api-key`), nunca hardcodeada.

## Cierre

Encuadre completo, las dos decisiones cerradas con el usuario y datos
reales verificados en ambas. Split en dos tickets de implementación
siguiendo el mismo patrón de milestones ya usado en el mapa animado
(`FIL_34`→`60`), en vez de uno monolítico:

- **`FIL_63`** (M1) — landing + auth Basic + desplegar `asistente/main.py`
  ya existente en la EC2, sin chat todavía (valida el despliegue primero).
- **M2** (chat) — se abrirá tras cerrar `FIL_63`.
