---
kind: fil
title: "notebooks/demo_madrono.ipynb celda 11 revienta en ejecución real (asyncio.new_event_loop dentro del kernel de Jupyter)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
---

> **Contexto**: encontrado verificando el PR #200 (notebook de demo) en la
> ronda de evaluación técnica `doc/PLAN-EVALUACION-TECNICA-2.md`.

## Qué está roto (verificado en vivo, ejecución real del notebook)

El commit de PR #200 afirma explícitamente: *"Verificado ejecutando las
12 celdas de código en orden."* Reproducido con
`jupyter nbconvert --to notebook --execute notebooks/demo_madrono.ipynb`
(el mismo mecanismo de ejecución que usa un kernel de Jupyter Lab/Notebook
real, no un modo especial de `nbconvert`): **la celda 11 (servidor MCP,
listado de tools) revienta**:

```
RuntimeError: Cannot run the event loop while another loop is running
```

Causa exacta: la celda hace

```python
tools_mcp = asyncio.new_event_loop().run_until_complete(mcp.list_tools())
```

con el comentario "`list_tools` es async; un loop nuevo y aislado
funciona igual en script o en Jupyter" — **esa afirmación es la causa raíz
del bug, no una nota inocua**: el kernel de IPython/Jupyter ya tiene su
propio event loop de `asyncio` corriendo en el hilo actual;
`run_until_complete()` comprueba `asyncio.events._get_running_loop()` del
hilo actual y lanza excepción si hay CUALQUIER loop corriendo, sea o no el
mismo objeto de loop — crear uno "nuevo y aislado" no evita el conflicto,
es exactamente lo que lo causa. En un script plano (sin kernel de asyncio
de por medio) sí funcionaría; en Jupyter, no.

**Impacto real**: si se abre este notebook en Jupyter Lab/Notebook durante
la defensa y se ejecuta la celda 11, revienta en directo delante del
tribunal — es justo la celda que lista las 9 tools del servidor MCP real,
parte central de la demo.

## Fix verificado

Cambiar la línea de la celda 11 a:

```python
tools_mcp = await mcp.list_tools()
```

(Jupyter/IPython soporta `await` de nivel superior en una celda desde
hace varias versiones — no hace falta ningún loop manual.) **Verificado
en esta sesión**: con ese único cambio, `jupyter nbconvert --execute`
sobre una copia del notebook completa las 12 celdas sin error, y la celda
imprime correctamente las 9 tools reales
(`afluencia_estimada`, `afluencia_prevista`, `calidad_aire`,
`calidad_aire_prevista`, `disponibilidad_aparcamiento`,
`eventos_cercanos`, `opciones_movilidad`, `trafico_cercano`,
`trafico_prevista`, todas con `in+out schema`).

## Restricciones

- No se ha tocado `notebooks/demo_madrono.ipynb` en este ticket — el fix
  se verificó contra una copia descartable, nunca contra el fichero real
  del repo.
- Si `build_demo_notebook.py` es el generador real del `.ipynb` (según su
  propio commit, "para diff/regeneración"), el fix debe aplicarse ahí, no
  solo en el `.ipynb` exportado, o la próxima regeneración lo revierte.

## Criterios de aceptación

- La celda 11 (o su equivalente tras regenerar) usa `await` en vez de
  `asyncio.new_event_loop().run_until_complete(...)`.
- Verificado de nuevo con `jupyter nbconvert --to notebook --execute` (no
  solo con una lectura del código) que las 12 celdas completan sin error.
