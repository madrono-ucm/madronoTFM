---
kind: vic
title: "Memoria §1–§4 — pase de consistencia con la arquitectura real"
owner: Víctor
status: pending
depends_on: [VIC_01, VIC_02, VIC_03, VIC_04, VIC_05, VIC_06]
created_at: "2026-08-28"
---

## Secciones

§1 Resumen · §2 Palabras clave · §3 Introducción · §4 Metodología.

## Objetivo

Hacer el último pase para que la introducción no prometa lo que §5–§7 ya no
dicen. Ligero — son ajustes de frase, no reescritura.

## Cambios concretos

- **§1 Resumen** — la frase *"mediante una arquitectura de ingeniería de
  datos extremo a extremo (Apache Kafka, lakehouse medallón sobre AWS,
  Apache Spark y prácticas MLOps)"* → sustituir "Apache Kafka" por la pila
  real (ingesta serverless programada), mantener "lakehouse medallón sobre
  AWS" (es cierto en capas, aunque no Delta), "Apache Spark" → "AWS Glue
  (Spark gestionado)", mantener "prácticas MLOps" (MLflow/Evidently/ONNX sí
  se usan en `modelado/`).
- **§2 Palabras clave** — "Apache Kafka" y "procesamiento en streaming" →
  quitar o mover a un "se consideró". Mantener "redes neuronales de grafos"
  (el GNN es el elemento central), "MLOps", "grafo urbano", "explicabilidad".
- **§3.2 Objetivos** — el objetivo *"Modelar la ciudad como un grafo y
  entrenar modelos predictivos de afluencia, congestión y calidad del
  aire"* se mantiene tal cual (es lo que hace `modelado/`). El objetivo de
  ingesta *"streaming y de referencia"* → "programada y de referencia".
- **§4.1 Diseño general** — la arquitectura "lambda con ruta caliente y ruta
  fría" → describir solo la ruta batch, o mantener el marco lambda
  admitiendo que la ruta caliente se deja como futura línea. El "bucle
  cerrado observación-decisión-realimentación" se mantiene (lo cierra el
  reentrenamiento nocturno del Tier 4).
- **§4.2 Tabla 1 (fases)** — revisar que las fases 3–5 reflejen el alcance
  real (modelado con GNN + ablaciones, no MLOps productivo completo).

## Aceptación

- Ninguna afirmación de §1–§4 contradice §5–§7 ya reescritas.
- El resumen y las palabras clave no mencionan Kafka/streaming como algo
  entregado.
