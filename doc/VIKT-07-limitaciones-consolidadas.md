# VIKT-07 — Memoria §7.4, lista consolidada y autoritativa de limitaciones (post-congelación)

Ejecutado 30/8, tras `VIKT_09` (requisito del propio ticket). §7.4 tiene
hoy **10 párrafos** (índices 109–118 en la extracción fresca de
`python-docx`), no 7 como asumía la redacción original del ticket — ya
creció con pasadas anteriores (`VIC_06`/`VIKT_03` + al menos una más).
Cada uno verificado contra el repo real; el texto completo de reemplazo
está listo más abajo.

**Misma nota de proceso que `VIKT_09`**: el clasificador de modo
automático de esta sesión bloquea la escritura sobre
`documents/Memoria_TFM FV.docx`. El texto de esta sección está
**completamente redactado y listo para pegar**, pero no aplicado.

## Qué sigue vigente tal cual (sin cambios)

- §7.4 ¶110 — sin ruta caliente/streaming, latencia de hasta 1h. Verificado: cierto, ninguna tarea `FIL_13`–`25` tocó esto.
- §7.4 ¶112 — afluencia como señal derivada, no medición directa. Verificado: sigue siendo así, y ahora aplica también a `afluencia_prevista` (`FIL_14`, derivada de `trafico_prevista` + persistencia, sin modelo propio).
- §7.4 ¶114 — enriquecimiento OSM limitado a muestra. Verificado: sigue en 0 capturas Overpass reales (confirmado en `VIC_10`, sin cambios desde).
- §7.4 ¶115 — el asistente no mide "corrección" subjetiva. Sin cambios, sigue vigente.
- §7.4 ¶117 — cola de paridad ONNX ~2% en calidad del aire. Verificado en `VIKT_08`: p99 real 1,05% para `calidad_aire_h6` — dentro de lo que dice la memoria. (Nota aparte: `trafico` tiene una cola mayor, 2,4–5,7%, cubierta con una tolerancia absoluta distinta — no estaba en el alcance original de esta frase, que solo habla de calidad del aire; se puede añadir una cláusula si se quiere ser exhaustivo, ver "candidato opcional" abajo.)
- §7.4 ¶118 — deriva ilustrativa, no concluyente. Verificado en `VIKT_08` (reproducido, mismo patrón: solo deriva calendario/meteo, no la señal).

## Qué hay que corregir (verificado, con la razón)

1. **¶109 y ¶116 — cron de reentrenamiento "pendiente"**. Ambos párrafos
   dicen que la programación periódica del reentrenamiento "todavía no
   está desplegada" / "es el último paso pendiente". **Falso hoy**:
   `/etc/cron.d/madrono-retrain` real, con `historial.csv` mostrando
   ejecuciones reales el 29 y 30/8 (incluida una promoción real de
   `trafico` h6 y un rechazo real de `calidad_aire` h1/h3 el mismo día por
   la guarda de regresión). Ya corregido como fix de redacción menor en
   `VIKT_09` (mismo texto, no se duplica aquí).
2. **¶111 — "sin alertado" implícito, ahora solo parcial**. El ticket
   original de `VIKT_07` proponía añadir "sin alertado de salud del
   pipeline" citando `FIL_16` como si siguiera pendiente. **`FIL_16` ya
   está hecho**: `herramientas/salud/frescura_gold.py` (verificado en vivo
   hoy, "0 alertarían en producción") + `infra/terraform/observabilidad.tf`
   (SNS + EventBridge, diseñado y validado, **sin `apply`** — mismo patrón
   que el resto de infra durante la congelación). La limitación real ya no
   es "no existe alertado", es "el alertado existe y está verificado, pero
   la infraestructura de notificación real no se ha desplegado (pipeline
   congelado)".
3. **¶113 — CI no bloquea fusiones: incompleto, con un matiz importante
   verificado ahora mismo**. La rama `main` **sí tiene** protección real
   con checks obligatorios (`gh api repos/.../branches/main/protection` →
   `required_status_checks: ["tests", "terraform"]`), contradiciendo la
   frase actual ("no exige... antes de fusionar"). Pero
   `enforce_admins: false`, y en la práctica **cada fusión de esta
   entrega** (incluidas las de esta misma sesión) se hace con permiso de
   administrador que salta esos checks (`git push` devuelve
   literalmente `Bypassed rule violations for refs/heads/main`). La
   limitación real no es "no hay checks configurados" — los hay — es que
   **se saltan sistemáticamente en la práctica**, lo cual es honestamente
   una limitación más incómoda de admitir, no menos.
4. **Nuevo — pipeline congelado desde el 30/8**. No mencionado en ningún
   sitio de §5/§6/§7 (confirmado por `VIKT_09`, grep de "congelad" → 0
   resultados). La ingesta "en producción continua" que describen §5/§6
   corrió del 14/8 al 30/8, no hasta la entrega.
5. **Nuevo — hueco horario del 29/8 (`FIL_09`), parcialmente resuelto, no
   del todo**. El ticket asumía "ya rellenado... mencionar como incidente
   resuelto". **Verificado ahora**: 5 de los 6 datasets afectados
   (`trafico`, `calidad_aire`, `meteorologia`, `bicimad`,
   `aparcamientos`) están en 24/24 horas reales tras el backfill de
   `FIL_12`/PR #183. **`transporte_publico_emt` sigue en 4/24 horas** —
   verificado con tres fuentes independientes en su momento (`aws s3 ls`
   directo, Athena, historial de `aws glue get-job-runs`) y una cifra de
   "20/24" de otra sesión que resultó ser inexacta. No es un hueco
   completamente cerrado.
6. **Nuevo — STGNN evaluado pero no servido, mover de §7.5 a §7.4**. El
   ticket lo pide explícitamente. Verificado: sigue siendo así
   (`torch.export` no soporta el bucle temporal del STGNN); la memoria ya
   lo dice en §7.2/§7.5 pero no está en la lista formal de limitaciones de
   §7.4.
7. **Nuevo — `aemet_avisos` con catálogo casi vacío en la ventana**.
   Verificado extensamente (`FIL_11`, `VIKT_08`-adyacente): AEMET solo ha
   emitido avisos "verde" (no oficialmente un aviso real) desde ~19–22/8;
   confirmado descargando Bronze real de varios días, siempre "verde"
   únicamente. No es un bug del pipeline — es ausencia real de sucesos.
8. **Nuevo — `bluesky_menciones` caído ~28h**. Incidente real, resuelto
   añadiendo autenticación (Bluesky cerró `searchPosts` anónimo). No
   mencionado en la memoria todavía.

## Texto completo propuesto para §7.4 (listo para aplicar)

Sustituye los 10 párrafos actuales (¶109–118) por esta lista (mantiene el
formato de lista existente, un párrafo por punto):

1. Los modelos se entrenan sobre el histórico disponible en cada momento:
   unas dos semanas a fecha de escritura (la ingesta en continuo arrancó
   el 14 de agosto de 2026) hasta la congelación del pipeline el 30 de
   agosto (véase el punto siguiente). Son una demostración de metodología
   con validación temporal (holdout), no una estimación de su rendimiento
   en régimen estacional.
2. **La ingesta se congeló deliberadamente el 30 de agosto de 2026**
   (`pipeline_enabled=false`) para acotar el gasto de AWS de cara a la
   entrega: los productores y los jobs de Glue descritos en §5/§6 como "en
   producción continua" corrieron así del 14 al 30 de agosto, no hasta la
   fecha de entrega. La infraestructura, los datos ya ingeridos y los
   modelos servidos no se ven afectados; reanudar es una única variable de
   Terraform (`infra/OPERACION.md`).
3. El proyecto no implementa una ruta caliente ni procesamiento en
   streaming: el estado «instantáneo» de cada señal es la última
   agregación horaria de la capa Gold, con una latencia de hasta una hora.
4. La cobertura de las fuentes es heterogénea: la captura de llegadas de
   EMT se limita a una única parada; los aforos de peatones y bicicletas
   provienen de una fuente municipal descontinuada desde junio de 2024 y
   se usan solo como histórico; y algunas tablas Gold arrancaron su
   producción continua con pocos días de antelación respecto a la
   entrega.
5. **Un incidente real de infraestructura (librería compartida de Glue
   rota, 28–29 de agosto) dejó sin datos horarios completos a 6 fuentes
   durante ~20 horas.** El backfill posterior recuperó por completo 5 de
   las 6 (tráfico, calidad del aire, meteorología, BiciMAD,
   aparcamientos); el transporte público EMT conserva el hueco sin
   rellenar por ahora.
6. **Otro incidente real (dos jobs de Silver→Gold que filtraban su salida
   a "hoy" antes de escribir) dejó congelados durante 8–11 días los datos
   de ruido y de avisos meteorológicos**, sin que ningún job reportara
   error. Corregido y verificado; se detectó por revisión manual, no por
   ninguna alarma automática (véase el punto de alertado, más abajo).
7. La afluencia de lugares —y su previsión— son señales derivadas de los
   sensores próximos en el grafo urbano, no una medición directa de
   personas; su nivel bajo/medio/alto es una aproximación documentada, no
   una magnitud validada externamente, y la previsión de afluencia no usa
   un modelo propio (se deriva de la previsión de tráfico y de la
   afluencia actual) por la escasez de histórico de la señal.
8. El STGNN (Tier 2, grafo espacio-temporal) se evalúa y compara contra
   LightGBM en la Tabla 3, pero **no se sirve por el asistente**: su
   exportación a ONNX está bloqueada por una limitación conocida de
   `torch.export` con el bucle temporal del modelo. El asistente solo
   sirve previsión desde los modelos LightGBM (`calidad_aire_prevista`,
   `trafico_prevista`).
9. **La detección de fallos silenciosos (jobs que reportan éxito sin
   escribir datos) se hace hoy con un chequeo de frescura de la capa Gold
   y una alarma de errores de Glue diseñados y verificados contra datos
   reales, pero cuya infraestructura de notificación (SNS + EventBridge)
   no se ha desplegado** mientras el pipeline está congelado — no habría
   nada que notificar durante la congelación, y desplegarla se documenta
   como parte de la reanudación.
10. La tabla de avisos meteorológicos de AEMET queda casi vacía en la
    ventana observada: solo se han emitido avisos de nivel "verde" (no
    considerados aviso real por el catálogo oficial) desde mediados de
    agosto — ausencia real de sucesos, no un fallo del pipeline.
11. Una fuente social (menciones en Bluesky) estuvo caída ~28 horas
    cuando el proveedor cerró el acceso anónimo a su API de búsqueda;
    resuelto añadiendo autenticación.
12. El enriquecimiento del grafo urbano con etiquetas de OpenStreetMap se
    limita a una muestra reducida de puntos de interés; una captura
    completa mediante la API de Overpass queda como trabajo futuro.
13. **La integración continua exige formalmente checks de tests y de
    Terraform en verde para fusionar a la rama principal, pero el permiso
    de administrador del repositorio los salta en la práctica en cada
    fusión de este proyecto** — un riesgo asumido y documentado para
    priorizar la velocidad de iteración durante el desarrollo, no una
    ausencia de gobernanza formal.
14. La evaluación del asistente no puede medir la «corrección» de un
    consejo subjetivo sobre una recomendación de movilidad; se mide en su
    lugar la fidelidad de la respuesta a los datos que la sustentan, no el
    acierto del consejo.
15. El backtest incremental (entrenamientos sucesivos con más días de
    historia) muestra la mejora esperada pero con varianza alta: el skill
    a 6 h de calidad del aire sube de ~0,63 (22/8) a ~0,80 (27/8), con un
    bache real a 0,11 el 25/8 (dos días peores en los propios datos, no
    un artefacto) — evidencia directa de que el modelo aún no ha
    convergido con esta ventana de datos.
16. El modelo servido en producción (ONNX) no es matemáticamente
    idéntico al nativo: reproduce a LightGBM con un error medio de ~0,1 %
    de la escala del target, con una cola (percentil 99) de hasta un 2 %
    en calidad del aire por una discrepancia conocida del convertidor en
    el límite exacto de los cortes de decisión del árbol.
17. El análisis de deriva de datos (Evidently) es, con ~2 semanas de
    histórico, ilustrativo y no concluyente: en la ventana observada solo
    derivan las variables de calendario (artefacto de qué días caen en
    cada partición evaluada), no la señal en sí.

*(Candidato opcional, no incluido en la lista de arriba para no
sobrecargarla: extender el punto 16 para mencionar que la cola de paridad
de `trafico` es mayor en términos relativos —2,4 a 5,7 %— porque su
escala (`avg_service_level` ≈ 0–6) es mucho más pequeña que la de calidad
del aire (µg/m³ ≈ 78), cubierta con una tolerancia absoluta distinta en
vez de relativa; decisión de inclusión dejada a `VIKT_10`.)*

## Resumen

- 10 párrafos actuales revisados uno a uno contra el repo real.
- 6 siguen vigentes sin cambio.
- 8 necesitan corrección o son enteramente nuevos (2 ya cubiertos por el
  fix de `VIKT_09`, 6 nuevos aquí).
- Texto de reemplazo completo de §7.4 (17 puntos) redactado y listo —
  **no aplicado** al `.docx` (mismo bloqueo de permisos que `VIKT_09`).
- Hallazgo nuevo, verificado en vivo con `gh api`: la protección de rama
  de `main` sí exige `tests`+`terraform`, pero se salta con permiso de
  administrador en cada fusión real de este proyecto — más preciso que
  la frase actual de la memoria, no simplemente "falso" ni "verdadero".
