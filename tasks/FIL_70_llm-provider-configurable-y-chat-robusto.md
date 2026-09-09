---
kind: fil
title: "Proveedor LLM del chat configurable por entorno + subconjunto de tools + reintento (rendimiento / límites)"
owner: Filippos (interactive)
status: in_review
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_62, FIL_69]
---

## Motivación

El chat (`asistente/chat.py`, FIL_62) usa Groq `openai/gpt-oss-120b` en el
tier gratuito: **8K TPM**. Manda las 15 tools MCP en cada llamada → el
`tools=[...]` + los resultados superan el límite → 429 / timeouts. El
usuario pidió "mejor rendimiento, menos errores/timeouts, sin restricción de
tokens", planteando auto-hospedar un modelo pequeño.

**Conclusión de la investigación** (en el hilo de la sesión): un modelo
pequeño auto-hospedado en la EC2 actual (CPU, ~3,7 GiB, ya hace OOM) sería
**más lento y con más errores** de tool-calling, no menos — misma razón por
la que `FIL_62` descartó Ollama en esa caja. La vía correcta es (A) cambiar
a un proveedor hosted con más margen y buen tool-calling (Cerebras / Groq
de pago / Together), y afinar la carga.

## Hecho (opción A)

1. **Proveedor configurable por entorno** — el transporte es
   OpenAI-compatible, así que basta apuntar la URL base:
   - `LLM_MODEL` (por defecto `qwen/qwen3.8-27b` en Groq — ver más abajo el
     porqué del cambio desde `openai/gpt-oss-120b`)
   - `LLM_BASE_URL` (sin definir → Groq; p. ej.
     `https://generativelanguage.googleapis.com/v1beta/openai/` para Gemini,
     una URL de OpenRouter, `http://localhost:11434/v1` para Ollama, la URL
     de un vLLM propio). Si `LLM_BASE_URL` está definida y `openai` está
     instalado se usa `openai.OpenAI`; si no, el SDK de Groq con `base_url`.
   - `LLM_API_KEY` (cae a `GROQ_API_KEY` y luego a SSM
     `/madrono-tfm/dev/secrets/groq-api-key`)
   Cero cambios de código para cambiar de proveedor.

   **Modelo por defecto**: `openai/gpt-oss-120b` alucinaba nombres de tool e
   intentaba llamar herramientas en la ronda de redacción (`400
   tool_use_failed`, respuestas vacías). Se cambió a `qwen/qwen3.8-27b`
   (Groq, tier gratuito, sin alta) que sigue el bucle de tool-calling de
   forma estable. `qwen/qwen3.6-27b` se descartó: es de razonamiento, filtra
   bloques `<think>` a la salida y da 429 con más frecuencia (aun así el
   chat quita `<think>...</think>` defensivamente, `_sin_think`).
2. **Subconjunto de tools para el chat** (`_TOOLS_CHAT`): 8 de las 15
   (`calidad_aire`, `trafico_cercano`, `consulta_grafo`, `contexto_urbano`,
   `ruta_saludable`, `mejor_hora_zona`, `eventos_cercanos`,
   `disponibilidad_aparcamiento`) — fuera las `*_prevista*` / `afluencia_*`
   / `opciones_movilidad` (esquemas grandes, nicho, datos congelados). El
   `tools=[...]` baja a ~la mitad de tokens.
3. **Reintento** (`_completar`): 3 intentos con backoff exponencial corto
   ante 408/409/429/5xx/timeout; un error no reintentable (400, auth) se
   propaga en el primer intento. Las dos llamadas del bucle
   (elegir-tool y redactar) pasan por él.

Tests: `asistente/tests/test_chat.py` nuevo (subconjunto de tools,
reintento, `base_url`/API key del entorno). Verde.

## Cómo cambiar de proveedor

**Por defecto** (nada que configurar): Groq `qwen/qwen3.8-27b`, tier
gratuito, sin alta de tarjeta. Límite 8K TPM — por eso `_TOOLS_CHAT` recorta
a 8 tools y `_completar` reintenta ante 429.

**Google Gemini** (gratuito, tool-calling sólido, cuota más holgada). API
key en `aistudio.google.com`. En la EC2 (o local):

```
export LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
export LLM_MODEL=gemini-2.0-flash
export LLM_API_KEY=AIza...
pip install openai        # el transporte de Gemini va mejor con el SDK openai
```

y reiniciar el asistente.

**OpenRouter**: `LLM_BASE_URL=https://openrouter.ai/api/v1`, un `LLM_MODEL`
que acabe en `:free`, `LLM_API_KEY=sk-or-...`.

**Cerebras** — rápido y con tool-calling real, pero **NO tiene tier
gratuito** (requiere plan de pago). Si se contrata:
`LLM_BASE_URL=https://api.cerebras.ai/v1`, `LLM_MODEL=llama-3.3-70b`,
`LLM_API_KEY=csk-...`.

**Sin dependencia externa** (para la defensa): vLLM + Qwen2.5-7B-Instruct en
una instancia GPU efímera (`g4dn.xlarge` spot), **no** en la EC2 de la app —
fuera del alcance de este ticket (nuevo gasto AWS, lock "zero new AWS").

## Nota — el error `HTTP 501` en el chat del mapa

El panel de chat de `viz/mapa/` hace `POST {API_BASE}/chat`. Si se sirve el
mapa con un `python -m http.server` plano, no existe `/chat` → 501. Hay que:
- **servir el mapa desde el propio asistente** (hecho): `app.mount("/mapa",
  StaticFiles(...))` → `http://<host>/mapa/`, con el chat en el mismo origen, o
- abrir `http://.../index.html?api=http://127.0.0.1:<puerto-asistente>`, o
- en `gh-pages`, `API_BASE` ya apunta a la EC2 pública.
