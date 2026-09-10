---
kind: vic-eval
title: "QA — tool calidad_aire_cams (FIL_80) + contraste en calidad_aire_prevista"
owner: Claude (QA)
status: done
depends_on: [FIL_80]
created_at: "2026-09-10"
---

## Contexto

FIL_80 añade `calidad_aire_cams` (17.ª tool) y un campo `referencia_cams` +
`delta` en `calidad_aire_prevista`.

## Alcance — verificación

1. **Parseo Gold**: `leadtime_hours` es `array<int>` — comprobar que se
   deserializa bien desde Athena (no como string). `avg_value`/`max_value`
   `double`. `fecha_validez` string ISO.
2. **Última fecha**: sin `fecha`, la tool elige la `fecha_validez` máxima
   disponible y lo dice en `motivo` (frescura, freeze 2026-08-30).
3. **Delta bien signado**: `delta = modelo_propio − CAMS` (documentado en el
   docstring y en `asistente/README.md`); un test con valores fijos.
4. **Contaminante**: normalización compartida con FIL_72 (`ozono/o3/o₃`);
   `grep` por que no haya un segundo mapa de alias.
5. **Registro 16→17**: mismos sitios que VIC_39.
6. **No cambia el veredicto** de `calidad_aire_prevista` — `referencia_cams`
   es solo contexto; verificar que el `Veredicto` no depende de CAMS.

## Criterios de aceptación

- Tests FIL_80 verdes; caso de delta con signo explícito.
- `grep -rn "16 tool\|las 16"` → 0 obsoletos.
- `asistente/README.md` documenta `GET /calidad-aire-cams` y el nuevo campo.

## Hecho (2026-09-10, Claude QA)

5/6 puntos sin hallazgos (parseo, frescura, registro ya en 19, veredicto
independiente de CAMS — este último ahora con test explícito). Punto 3
(signo del delta) era correcto en el código pero **sin ninguna cobertura
real**: el `athena_client is None` que se suponía debía desactivar el
contraste CAMS en tests nunca se activaba (ningún test pasa
`athena_client` explícito), así que dos tests preexistentes ejecutaban de
verdad el contraste reutilizando filas de aire mockeadas con forma
distinta a una fila CAMS, sintetizando un `referencia_cams`/`delta_vs_cams`
sin sentido de forma silenciosa (`referencia_cams=40.0` verificado
empíricamente, cuando debía ser `None` o un valor CAMS real). Corregido:
3 tests nuevos que mockean `calidad_aire_cams` directamente (el punto de
inyección correcto) + 2 tests existentes endurecidos + comentario
corregido en `tools.py`. Punto 4: la cita "compartida con FIL_72" en este
ticket (y en el propio `FIL_80`) es un número de ticket equivocado — no
hay ningún duplicado real de normalización de contaminante en el código.
Ningún ticket `FIL_*` nuevo — el hallazgo era un hueco de aislamiento de
tests, sin impacto en producción, corregido directamente.

Detalle completo en
[`doc/VIC-40-eval-tool-cams.md`](../doc/VIC-40-eval-tool-cams.md).
