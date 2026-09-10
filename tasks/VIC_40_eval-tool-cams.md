---
kind: vic-eval
title: "QA — tool calidad_aire_cams (FIL_80) + contraste en calidad_aire_prevista"
owner: Claude (QA)
status: pending
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
