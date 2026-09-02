---
kind: fil
title: "networkx sin pin en requirements — test de FIL_52 falla en esta EC2 (louvain_communities no existe en 2.6.3)"
status: pending
created_at: "2026-09-02"
source: "QA (resumen de estado, suite completa)"
severity: baja (entorno local desactualizado, no CI)
---

## Qué está roto (verificado en vivo)

`env PYTHONPATH=. pytest ingesta/ procesamiento/ grafo/ asistente/
herramientas/ modelado/ tests/` en esta EC2:

```
FAILED modelado/tests/test_grafo_analitica.py::FuncionesTests::test_comunidades_devuelve_ari_nmi
AttributeError: module 'networkx.algorithms.community' has no attribute 'louvain_communities'
```

Causa raíz confirmada: `networkx` instalado en el `.venv` compartido de
esta EC2 es la **2.6.3**; `nx.community.louvain_communities` (usada en
`modelado/grafo_analitica/analisis.py:122`, añadida en `FIL_52`) solo
existe desde `networkx 2.8`. `networkx` **no está pineado en ningún**
`requirements.txt` (`ingesta`/`modelado`/`asistente`/`viz`) — es una
dependencia transitiva/no declarada cuya versión depende de lo que ya
hubiera instalado en cada entorno.

**No es un problema de CI**: los últimos 5 runs de `gh run list` están en
verde (`success`), incluido el commit de `FIL_52` — CI instala
dependencias frescas y se lleva una versión reciente de `networkx` con
`louvain_communities` ya presente. El fallo es específico de este `.venv`
compartido de la EC2, que arrastra una `networkx` vieja de mucho antes de
que existiera `modelado/grafo_analitica/`.

## Por qué importa

Bajo impacto (no bloquea CI ni a nadie con un entorno fresco), pero es un
hueco real de reproducibilidad: cualquiera que reutilice un `.venv`
antiguo (como esta EC2) para trabajar en `modelado/grafo_analitica/` se
encontrará este fallo sin pista de la causa real salvo leer el
`AttributeError` con cuidado. Pinear la versión mínima documenta la
dependencia real del código en vez de dejarla implícita.

## Qué hacer (propuesto, no aplicado aquí)

- Añadir `networkx>=2.8` a `modelado/requirements.txt` (documenta el
  mínimo real que pide `louvain_communities`; `viz/rutas.py` también usa
  `networkx` pero solo API estable desde versiones muy anteriores —
  revisar si conviene el mismo pin en `viz/requirements.txt` por
  consistencia, aunque no lo necesita funcionalmente).
- En esta EC2 en concreto: `pip install -U networkx` en el `.venv`
  compartido para poder ejecutar/verificar `modelado/grafo_analitica/`
  localmente sin este fallo.

## Restricciones

- No se ha aplicado el cambio aquí (ticket de solo lectura).
- No es urgente: no afecta a CI ni a producción, solo a la reproducción
  local en este `.venv` concreto.

## Criterios de aceptación

- `networkx>=2.8` en `modelado/requirements.txt`.
- `pytest modelado/tests/test_grafo_analitica.py` en verde tras
  `pip install -r modelado/requirements.txt` en un `.venv` fresco (y en
  este, tras el `pip install -U` manual).
