# Figuras de la memoria (diagramas Mermaid)

Cada `NN_nombre.mmd` es la fuente Mermaid de una figura embebida en
`documents/Memoria_TFM FV.docx`. Se renderizan a PNG con Chromium headless
(Playwright, ya usado en el proyecto para QA de navegador — ver `VIC_32`)
y `mermaid.js` vía CDN, porque esta instancia no tiene Node/npx para
`mermaid-cli`.

```bash
pip install playwright && playwright install chromium
python -m documents.figuras.mermaid_render documents/figuras/01_arquitectura.mmd documents/figuras/01_arquitectura.png --width 2200
```

| Figura | Fichero | Sección de la memoria |
|---|---|---|
| 1 | `01_arquitectura.mmd` | §5.1 — arquitectura completa del sistema |
| 2 | `02_pipeline_datos.mmd` | §6.3 — flujo Bronze→Silver→Gold |
| 3 | `05_modelo_grafo.mmd` | §6.6 — modelo del grafo urbano (labels/relaciones) |
| 4 | `04_secuencia_consulta.mmd` | §6.7 — secuencia de una consulta al asistente |
| 5 | `07_mcp_chat.mmd` | §6.7 — catálogo de las 19 tools MCP + 3 superficies de chat |
| 6 | `03_pipeline_ml.mmd` | §7.2 — pipeline de `modelado/` |
| 7 | `06_analitica_grafo.mmd` | §7.3 — pipeline de analítica de grafo (centralidad/comunidades/resiliencia) |
| 8 | `grafo_resiliencia.png` (en `modelado/evaluation/artifacts/`, no aquí) | §7.3 — curva de robustez del grafo |

Tras editar un `.mmd`, re-renderizar el PNG y volver a insertarlo en el
`.docx` con `python-docx` (ver el histórico de `git log -- "documents/Memoria_TFM FV.docx"`
para los scripts de edición usados sesión a sesión).
