# FIL-14 — `afluencia_prevista`: decisión y ejecución

## Decisión: vía (b) — señal derivada, sin modelo propio

`afluencia` ("¿merece la pena ir a un lugar?") es la capacidad estrella de la
memoria (§6.7). Hasta ahora sólo existía `afluencia_estimada` (`FIL_06`): la
señal **actual** fusionada de sensores vía grafo, no una previsión.

Las tres vías del ticket:

| Vía | Veredicto |
|---|---|
| (a) modelo propio LightGBM sobre el panel de `afluencia` | **Descartada.** `gold.afluencia_lugares_por_lugar_fecha_hora` tiene ~1–2 días de histórico útil (el job horario arrancó tarde y el incidente `FIL_09` dejó huecos), y el pipeline está **congelado** desde el 30/8 — no va a crecer. Entrenar lags de 24 h sobre eso da un modelo sin skill real; forzarlo sería justo lo que la restricción del ticket prohíbe. |
| (b) derivar de las previsiones existentes + persistencia | **Elegida.** No entrena nada; reutiliza `trafico_prevista` (`FIL_13`) y `afluencia_estimada` (`FIL_06`), ya verificadas en vivo. Coherente con la narrativa de "fusión multi-señal" del TFM. |
| (c) limitación documentada, sin tool | Innecesariamente conservadora: (b) es barata y honesta. |

## Qué se implementó

`asistente.mcp_agent.tools.afluencia_prevista(lugar, horizonte_horas=6,
radio_m=300.0, momento=None)` → `AfluenciaPrevista` (subclase de
`RespuestaPrevision`, `FIL_15`).

Mecánica (sin backend propio — compone dos `_impl` ya testados):

1. `_afluencia_estimada_impl(lugar, radio_m, momento)` → nivel **actual**
   multi-señal + lecturas actuales de ruido y BiciMAD.
2. `_trafico_prevista_impl(lugar, horizonte_horas, radio_m, momento)` → la
   **previsión** de `avg_service_level` del peor punto de tráfico cercano
   (único subcomponente con modelo ONNX entrenado).
3. Fusión: severidad 0–2 del **tráfico previsto** (bandas de `trafico_cercano`)
   + severidad 0–2 **actual** de ruido (dB) y BiciMAD (ocupación) por
   **persistencia** — misma fórmula ponderada byte a byte que
   `afluencia_estimada` / `procesamiento/silver_gold/afluencia_lugares/nivel.py`.
   Media → `_SEVERIDAD_A_NIVEL` → `nivel_previsto` ∈ {`bajo`,`medio`,`alto`}.

`valor_previsto` = severidad combinada 0–2; `nivel_actual` = contexto;
`senales_usadas` lista qué entró; `modelo` deja constancia de que es
**derivada** (`"derivada (FIL_14): trafico_h<H>.onnx … + persistencia
ruido/BiciMAD"`); `data_completeness`/`ventana_datos` se heredan de la
previsión de tráfico subyacente.

**Por qué ruido/BiciMAD por persistencia y no previstos:** no tienen modelo.
Ruido (`gold.ruido_por_estacion_periodo_fecha`) es agregado por periodo, no
horario; BiciMAD tiene histórico pero no se entrenó nada. Asumir "seguirá
como ahora" es la hipótesis nula honesta y queda explícita en la respuesta y
en la `explicacion` del router.

## Degradación

`trafico_prevista` es el pivote: si no hay previsión de tráfico (sin puntos
cerca, Gold sin lags, `.onnx` ausente, Athena/Neo4j caídos) →
`disponible=False` + `motivo`, pero se rellena `nivel_actual` para que la
respuesta siga siendo útil. Si `afluencia_estimada` falla pero el tráfico
previsto está, se devuelve la previsión sólo-tráfico (`senales_usadas =
["trafico(previsto)"]`). Nunca excepción hacia el cliente MCP.

## Verificación

- `asistente/tests/test_afluencia_prevista.py` (11 casos): fusión de las tres
  severidades, sólo-tráfico sin persistencia, cada modo de degradación,
  router OK / router sin previsión. Registro (9 tools) en
  `test_mcp_tools.py` y transporte en `test_mcp_transport.py`.
- **En vivo por transitividad.** `afluencia_prevista` no añade ninguna
  interacción nueva con backends: es exactamente `trafico_prevista`
  (verificada en vivo contra Athena + Neo4j reales en `FIL_13`, ver
  `doc/FIL-13-...md` — Retiro/Sol/Atocha devolvieron previsiones reales) +
  `afluencia_estimada` (verificada en vivo en la tarea 089) + una fusión
  aritmética determinista (11 tests). Una comprobación directa por SSM en la
  EC2 quedó bloqueada por el clasificador de la sesión; el comando reproducible
  está en `infra/OPERACION.md` si se quiere repetir a mano
  (`AWS_DEFAULT_REGION=eu-west-1 NEO4J_* .venv/bin/python -c "from asistente.mcp_agent import tools; print(tools.afluencia_prevista('retiro', 3))"`).

## Registro

Tool `afluencia_prevista` en `server.py` (9 tools) + router
`GET /afluencia-prevista` + `asistente/main.py`.

## Pendiente / relacionado

- Si algún día se acumula histórico horario de afluencia con el pipeline
  descongelado, vía (a) (modelo propio) queda como mejora natural — §7.5.
- Ruido/BiciMAD previstos requerirían sus propios modelos (§7.5).
