---
kind: vic-eval
title: "QA — tools meteo_cercana + avisos_meteo (FIL_82): resolución por grafo, orden de niveles, frescura"
owner: Claude (QA)
status: pending
depends_on: [FIL_82]
created_at: "2026-09-10"
---

## Contexto

FIL_82 añade `meteo_cercana` (18.ª) y `avisos_meteo` (19.ª), sobre
`meteorologia_por_estacion_magnitud_hora` y
`aemet_avisos_por_zona_fecha_nivel`.

## Alcance — verificación

1. **Resolución "cerca de"**: `meteo_cercana` usa el grafo
   (`:EstacionMedida{meteo}` `PROXIMO_A`, FIL_65) y sólo cae a haversine
   sobre la Gold si el grafo no responde — verificar el fallback y que no se
   dispara siempre.
2. **Agregación**: última hora disponible por magnitud (no media de todo el
   día); la respuesta lleva estación + hora del dato.
3. **Orden de niveles de aviso**: `rojo > naranja > amarillo > verde`;
   `avisos_meteo` devuelve el más alto y la lista de fenómenos. Test con
   varias zonas/niveles.
4. **Frescura**: sin `fecha`, ambas devuelven el último día con datos y un
   `motivo` (freeze 2026-08-30, contrato FIL_73). Fiabilidad BAJA en ese
   caso, MEDIA si el dato es reciente.
5. **Registro 17→19**: `server.py`, `test_mcp_*` (`_ESPERADAS`,
   `test_list_tools_expone_las_19`), `asistente/README.md` (2 filas + 2
   endpoints), `README.md` raíz, `_INSTRUCCIONES`.
6. **`contexto_urbano`**: incluye el resumen meteo de la estación más
   cercana — que no rompa cuando no hay estación meteo cerca.

## Criterios de aceptación

- Tests FIL_82 verdes (agregación, orden de niveles, degradación).
- `grep -rn "17 tool\|18 tool\|las 17\|las 18"` → 0 obsoletos; queda "19".
- Ambos endpoints documentados en `asistente/README.md`.
