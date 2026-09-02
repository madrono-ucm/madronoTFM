---
kind: fil
title: "App web de Madroño — landing con acceso demo + chat con el asistente (encuadre)"
owner: propuesto por Claude (QA), sin asignar
status: framing
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

## El punto que cambia la conversación de coste del proyecto

Todo Madroño, hasta ahora, mantiene **coste cero real** (Free tier de
AWS/AuraDB, datos abiertos, sin claves de pago). Un chat en lenguaje
natural de verdad necesita un LLM que decida qué tool llamar y redacte la
respuesta — eso **sí tiene coste real por mensaje** (tokens de la API de
Anthropic o equivalente), la primera pieza de todo el proyecto que rompe
esa racha. Conviene decidirlo explícitamente, no que aparezca como
sorpresa:

- **Opción A — LLM real con tool-calling** (Anthropic Messages API +
  `tool_use` sobre las 14 tools ya expuestas por HTTP): la experiencia
  más parecida a "chatear de verdad", coste real pero pequeño con un
  modelo barato (p. ej. Haiku) y uso de demo acotado — hace falta una
  clave de API propia del proyecto (hoy no existe ninguna) y, siguiendo
  el propio patrón de `herramientas/costes/`, un presupuesto/límite duro
  (p. ej. N mensajes/día) para que un uso viral no dispare la factura.
- **Opción B — chat "estructurado" sin LLM**: un front que hace
  coincidencia de intención por palabra clave/plantilla contra las 14
  tools (p. ej. "aire en Sol" → `calidad_aire(zona="Sol")`), sin llamar a
  ningún modelo. Coste marginal cero, pero es un asistente de formulario
  disfrazado de chat, no una conversación real — hay que ser honesto con
  esa limitación si se elige esta vía para la memoria/demo.
- **Opción C — híbrido acotado**: LLM real pero con un tope duro de
  peticiones (por IP/sesión/día) y una alarma de coste en CloudWatch
  Billing, mismo criterio de "barato con freno" que ya usa el proyecto en
  otros sitios (`pipeline_enabled`, límites de Free tier documentados en
  `infra/neo4j/README.md`).

**Recomendación**: si el objetivo es la demo/defensa del TFM, la opción A
acotada (un límite bajo y duro de mensajes) da la mejor experiencia por un
coste predecible y pequeño — pero es una decisión del usuario, no algo
que decidir por defecto.

## Piezas que hacen falta (si se decide seguir adelante)

1. **Desplegar `asistente/main.py` en algún sitio público** — dos rutas
   razonables, ninguna implementada:
   - **EC2 del daemon (ya encendida)**: `systemd` + `uvicorn` +
     `nginx`/Caddy como proxy inverso (TLS + auth Basic ahí mismo, ver
     punto 3). Coste marginal ≈ 0 (la EC2 ya corre); requiere abrir el
     security group a 443 y, si no hay dominio propio, usar un DNS
     dinámico o el IP público de la instancia.
   - **Lambda + API Gateway** (vía Lambda Web Adapter, para servir ASGI/
     FastAPI sin reescribir la app): más "serverless-nativo" y coherente
     con el resto de la infraestructura, pero **riesgo real de
     compatibilidad**: el propio docstring de `asistente/main.py` explica
     que el `lifespan` del servidor MCP (`StreamableHTTPSessionManager`)
     asume un proceso de larga duración — un modelo de una invocación por
     petición de Lambda puede no sostener sesiones MCP igual (los
     routers REST normales sí funcionarían bien). Si se elige esta vía,
     probablemente el chat use solo los routers HTTP, no el MCP montado.
   - Ninguna de las dos tiene ticket de Terraform hoy — hace falta
     escribirlo desde cero en cualquiera de los dos casos.
2. **La capa de chat/orquestación** (nueva, ver opciones A/B/C arriba) —
   endpoint nuevo (p. ej. `POST /chat`) que reciba el mensaje, decida qué
   tool(s) llamar sobre los routers ya existentes, y devuelva una
   respuesta en prosa.
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

- No decide la opción A/B/C de coste — es una decisión del usuario.
- No decide EC2 vs. Lambda para el despliegue.
- No es una implementación — cero código, cero Terraform, cero
  despliegue en este ticket.

## Restricciones

- Ticket de encuadre (`framing`), sin código ni infraestructura
  aplicados.
- Cualquier vía con LLM real necesita una clave de API que hoy no existe
  en el proyecto — gestionarla con el mismo patrón que el resto de
  secretos (`ingesta/capturas/secretos.py`, SSM `SecureString`,
  `FIL_17`), nunca hardcodeada.
- Antes de implementar, decidir explícitamente con el usuario: opción de
  coste del chat (A/B/C) y vía de despliegue (EC2/Lambda).

## Próximo paso propuesto

Si el usuario confirma que quiere seguir adelante: abrir un ticket de
implementación (`M1` — landing + auth Basic + despliegue del backend ya
existente sin chat todavía, para validar el despliegue primero; `M2` —
capa de chat sobre eso) en vez de un único ticket monolítico, siguiendo
el mismo patrón de milestones ya usado en el mapa animado (`FIL_34`→`60`).
