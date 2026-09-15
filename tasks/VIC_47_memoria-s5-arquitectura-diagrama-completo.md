---
kind: vic-eval
title: "Memoria — §5 Arquitectura: rehacer la Figura 1 con el sistema completo (PRIORIDAD 1 — diagrama más citado del documento)"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: []
---

## Contexto

**Este es el diagrama más importante del documento** — Figura 1 se cita
desde §5.1 y se referencia implícitamente en toda §6-§7. La versión actual
(hecha en algún momento antes de `VIC_01`, nunca rehecha desde entonces)
casi con toda seguridad no incluye: la aplicación web (`FIL_62`/`63`,
landing + chat + Groq, EC2 + S3/CloudFront), la visualización animada del
grafo (`FIL_36`+, GitHub Pages), el explorador del grafo en vivo (`FIL_67`
Parte 3 + refinado en `FIL_69`-`75`), ni la observabilidad MCP (`FIL_73`).
Es decir: probablemente sigue mostrando solo ingesta→lakehouse→grafo→
asistente, sin las tres superficies de explotación que `VIC_38` ya
documentó en prosa (§6.7) pero que el diagrama de arquitectura no ilustra.

## Alcance

1. **Extraer la Figura 1 actual** del `.docx` (`python-docx` permite leer
   la imagen embebida — guardarla a un fichero para inspección visual
   antes de decidir si se rehace desde cero o se extiende).
2. **Verificar el inventario completo de componentes reales** contra el
   código, no de memoria — para cada capa:
   - Ingesta: Lambda + EventBridge Scheduler (23 reglas), por fuente.
   - Almacenamiento: S3 (Bronze/Silver/Gold Parquet), Glue Data Catalog,
     Athena + Partition Projection.
   - Procesamiento: Glue (Spark), Great Expectations.
   - Grafo: Neo4j AuraDB (9812+ nodos, ver `VIC_34`/`FIL_89`).
   - Modelado: `modelado/` (feature store, LightGBM, STGNN, MLflow,
     Evidently, ONNX), `cron` de reentrenamiento nocturno.
   - Explotación (verificar las 3 superficies reales hoy, no solo las
     documentadas en `VIC_38` hace 5 días — pueden haber cambiado con
     `FIL_69`-`99`): asistente FastAPI/MCP (19+ tools, confirmar cifra
     actual), app web (landing+chat, EC2+S3+CloudFront), mapa animado
     (GitHub Pages), explorador del grafo en vivo (con chat incrustado,
     `FIL_68`).
   - Observabilidad: `FIL_16` (regla EventBridge) + `FIL_73` (MCP).
   - Seguridad: SSM SecureString (`FIL_17`).
3. **Diseñar y generar el diagrama nuevo** con `graphviz` (instalado en
   esta sesión: `sudo apt install graphviz` + `pip install graphviz` en
   el `.venv`) — un diagrama de arquitectura por capas/cajas con flechas
   de flujo de datos, estilo C4 "contenedor" o similar (cajas agrupadas
   por capa: Fuentes → Ingesta → Lakehouse → Procesamiento → Grafo/ML →
   Explotación), colores consistentes con el resto de figuras del
   documento (paleta ya usada en `grafo_resiliencia.png`:
   `#d1495b`/`#3d6ce0`/`#edae49`/`#66a182`, o similar). El script generador
   debe quedar commiteado (sugerido `documents/figuras/arquitectura.py` o
   similar — crear la carpeta si no existe, documentar en un `README.md`
   breve de esa carpeta cómo regenerar todas las figuras nuevas de esta
   ronda de tickets `VIC_45`-`53`).
4. **Sustituir Figura 1** en el `.docx` (quitar el `w:drawing` viejo e
   insertar el nuevo, o insertar el nuevo justo después y quitar el
   anterior — verificar con `python-docx` que solo queda una Figura 1 al
   final, no dos).
5. Releer §5.2-§5.5 contra el inventario verificado en el punto 2 — no
   solo la figura, también la prosa: ¿sigue siendo precisa la descripción
   de la capa de explotación tras `FIL_69`-`99`? ¿La cifra de tools sigue
   en 19, o subió más?

## Criterios de aceptación

- Figura 1 nueva refleja el sistema completo verificado hoy (incluidas
  las 3 superficies de explotación + observabilidad + seguridad).
- Script generador de la figura commiteado y ejecutable
  (`python -m documents.figuras.arquitectura` o ruta equivalente).
- §5.2-§5.5 releídas y corregidas si hay drift frente al inventario.
- Solo una Figura 1 en el documento final (verificado contando
  `w:drawing` reales, no coincidencias de subcadena en el XML).
