---
kind: fil
title: "afluencia_prevista: decidir vía (modelo propio / derivado / limitación) e implementar"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: [FIL_13]
---

## Contexto

`afluencia` (\"¿merece la pena ir a un lugar?\") es la capacidad estrella de
la memoria (§6.7). Hoy sólo existe `afluencia_estimada` — la señal *actual*
derivada de sensores vía grafo (FIL_06), no una **previsión**. La Gold
derivada (`afluencia_lugares_por_lugar_fecha_hora`) tiene ~1–2 días de
histórico útil (job horario arrancó tarde + huecos por el incidente FIL_09),
demasiado fino para lags de 24h.

## Objetivo

Tomar y ejecutar **una** de estas vías, documentando el porqué:

- **(a) Modelo propio ligero.** LightGBM sobre el panel de `afluencia`
  (target = `nivel_estimado` 0/1/2) con la ventana fina que haya, declarando
  la limitación en §7.4. Riesgo: pocos datos → skill pobre.
- **(b) Derivada de las previsiones.** `afluencia_prevista(lugar, h)` =
  combinar `trafico_prevista` + `calidad_aire_prevista` + `ruido` de los
  sensores `PROXIMO_A` al lugar, con la misma fórmula ponderada que
  `estimada.py`. No entrena nada nuevo; hereda el horizonte de los modelos
  base. **Recomendada** — coherente con el diseño de FIL_06 y con la
  narrativa de \"fusión multi-señal\".
- **(c) Limitación documentada.** `afluencia_prevista` queda como línea
  futura de §7.5; la tool actual (`afluencia_estimada`) es lo que se
  presenta.

## Alcance

1. `doc/FIL-14-...md` con la decisión razonada (volumen real de la Gold,
   skill esperado, esfuerzo).
2. Implementación de la vía elegida (si (a)/(b)): tool + router + modelo de
   respuesta, espejo de las otras `*_prevista`.
3. Verificación en vivo + tests.

## Criterios de aceptación

- Decisión explícita registrada.
- Si (a)/(b): `afluencia_prevista` funcionando y verificada; si (c): frase
  de §7.5 lista para `VIKT_*`.

## Restricciones

- No forzar un modelo con datos insuficientes sin decirlo claramente.
