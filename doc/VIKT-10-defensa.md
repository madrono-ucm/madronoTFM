# VIKT-10 — Preparación de la defensa + checklist editorial

Preparado 30/8 por Claude (QA), per las restricciones explícitas de este
ticket: **no sustituye la lectura editorial humana** de
`documents/Memoria_TFM FV.docx` — eso lo hacen Víctor y/o Filippos. Esto
cubre la parte que el propio ticket asigna a Claude: la checklist y el
guion de defensa con Q&A.

## 1. Checklist de revisión editorial (para la lectura humana)

No marcada — es la parte que requiere ojos humanos. Puntos concretos a
revisar, derivados de las ediciones con `python-docx` de `VIKT_02`–`05` y
de los 7 fixes de redacción menor que `VIKT_09`/`VIKT_07` dejaron
redactados pero **sin aplicar** (ver más abajo, sección 3):

- [ ] Aplicar los 7 fixes de `VIKT_09` (tool count **10**, no 9 — corregido
      de nuevo tras `FIL_26`; cron desplegado; parques y jardines ya no
      pendiente; el STGNN ya se sirve como tool real, no solo "ya no
      bloqueado") — texto exacto en `doc/VIKT-09-consistencia-final.md`
      §1, **re-verificar el conteo de tools justo antes de aplicar** dado
      el ritmo de cambios de esta ronda (nota al inicio de ese documento).
- [ ] Aplicar el reemplazo completo de §7.4 (17 puntos) de `VIKT_07` —
      texto exacto en `doc/VIKT-07-limitaciones-consolidadas.md`.
- [ ] Decidir y aplicar la corrección de Tabla 3 (`VIKT_05`/`VIKT_09` §2):
      o se re-ejecuta `run_all.py` para refrescar los números, o se anota
      explícitamente que la tabla es de una versión anterior del panel.
      **Alta prioridad** — la diferencia es de 3–5,6x en calidad del aire,
      no un matiz menor.
- [ ] Revisar numeración de tablas/figuras tras cualquier edición — las
      ediciones con `python-docx` no renumeran automáticamente.
- [ ] Verificar que cada tabla/figura referenciada en el texto (Tabla 3,
      figuras de SHAP/importancia de aristas) tiene su pie y su cita
      cruzada correcta.
- [ ] Releer el abstract/resumen ejecutivo contra el §7 real, especialmente
      si se aplica el fix de Tabla 3 (los números del resumen deben
      coincidir con los de la tabla).
- [ ] Bibliografía y formato de plantilla de la universidad (Claude no
      tiene la plantilla oficial para verificar esto).
- [ ] Portada/metadatos (título exacto, autores, tutor, fecha de entrega).
- [ ] Una pasada de estilo/tono para que las 3 rondas de ediciones
      (`VIC_*`, `VIKT_02`–`05`, `VIKT_07`/`09` si se aplican) lean como una
      sola voz.

## 2. Guion de defensa

Apoyado en el recorrido reproducible de `VIKT_06`
(`doc/VIKT-06-recorrido-e2e.md`). Orden sugerido, ~10-12 min de
exposición + preguntas:

1. **El problema** (30s): Madrid publica datos abiertos en tiempo real,
   pero aislados — ninguna plataforma los integra en una decisión
   accionable.
2. **La arquitectura** (1 min): lakehouse medallón (Bronze/Silver/Gold) +
   grafo urbano Neo4j + modelado predictivo + asistente conversacional
   MCP. Mostrar el diagrama de arquitectura (artifact "Arquitectura
   end-to-end" o el `README.md` raíz).
3. **Demo en vivo** (4-5 min, siguiendo `VIKT_06`):
   - un dato real de tráfico entra por Bronze (§1 del recorrido),
   - se transforma y agrega hasta Gold (§2),
   - el asistente responde con `calidad_aire` (§4.2, solo Athena),
   - **momento central**: `calidad_aire_prevista` — previsión ONNX real,
     con el envoltorio completo (valor, modelo, ventana de datos,
     confianza) (§4.3),
   - un fallo real de backend degrada con gracia, no revienta (§4.4).
4. **Los resultados** (2 min): Tabla 3 — LightGBM y STGNN baten a la
   línea base en la mayoría de horizontes; el patrón "más contexto
   espacio-temporal ayuda más cuanto más lejos se mira" es el esperado.
   **Si la Tabla 3 no se refrescó antes de la defensa, decirlo aquí
   explícitamente** en vez de que lo encuentre el tribunal.
5. **Honestidad sobre los límites** (2 min): ventana de datos corta y
   skill volátil día a día, pipeline congelado para la entrega, EMT una
   parada — apoyarse en la lista consolidada de `VIKT_07`.
6. **Cierre** (30s): qué se demuestra (ingeniería de datos + ML +
   producto conversacional end-to-end, verificado contra sistemas reales,
   no simulados) y qué queda para una versión de producción real (§7.5).

## 3. Preguntas anticipadas y respuestas

**¿Por qué no Kafka/Flink/Delta si la memoria los menciona?**
Se diseñaron (`infra/terraform/kafka.tf`, `infra/kafka/`) pero
deliberadamente no se aplicaron: el proyecto tiene coste cero como
restricción de diseño (§5.4), y una ruta caliente con streaming real
tiene un coste de infraestructura permanente que no se justifica para el
volumen y la cadencia de las fuentes de Madrid (mayoría, horaria). Es una
decisión de diseño documentada, no una limitación de tiempo.

**¿Por qué está el pipeline congelado justo antes de la entrega?**
Decisión deliberada el 30/8 (`pipeline_enabled=false`) para dejar de
acumular gasto de AWS mientras se termina la memoria y se prepara la
defensa — no porque algo se rompiera. Los datos ya ingeridos (14/8–30/8),
el grafo, y los modelos servidos siguen intactos y consultables; reanudar
es una variable de Terraform.

**¿El STGNN se sirve en producción, o solo está en la Tabla 3?**
**[Actualizado dos veces — primero tras `FIL_20`, ahora tras `FIL_26`,
cada uno aterrizado después de escribir la versión anterior de esta
respuesta]**: **sí se sirve**, como una 10.ª tool del asistente
(`calidad_aire_prevista_grafo`, `FIL_26`) — exportado a ONNX con paridad
casi perfecta (`max|Δ|≈6e-8`, `FIL_20`, verificado también de forma
independiente con grafos de tamaño distinto al de export) y vendorizado
sin depender de `torch` en runtime. La limitación de `torch.export` con
el bucle temporal era real con versiones antiguas de `torch`, no con la
2.13 instalada. Honestamente documentado: en métricas puntuales a 1h
pierde frente a `calidad_aire_prevista` (LightGBM, skill -0,51), así que
se sirve con la fiabilidad topada en BAJA — su valor real es la
**explicabilidad de grafo** que un modelo de árboles no da (qué estación
vecina explica la predicción), no sustituir al LightGBM como previsión
principal. El STGNN se evalúa y se compara honestamente contra LightGBM
en §7.2/Tabla 3.

**¿Por qué la ventana de datos es tan corta (~2 semanas)?**
La ingesta en continuo arrancó el 14 de agosto de 2026; el proyecto se
entrega el 17 de septiembre. Es una demostración de metodología con
validación temporal real (holdout), no una estimación de rendimiento en
régimen estacional — el backtest incremental (`ML_10`) es la evidencia de
que el enfoque mejora con más datos, no de que ya esté maduro.

**¿Por qué EMT solo captura una parada?**
Decisión de alcance de la tarea original (`FIL_07`, multi-parada, quedó
sin hacer) — la API de EMT no da una vista agregada barata de todas las
paradas de una línea sin multiplicar las llamadas; capturar una parada
representativa por línea fue el compromiso de coste/cobertura elegido
para esta entrega.

**¿Cómo se sabe que el asistente no inventa datos?**
Cada tool está verificada de extremo a extremo contra Athena/Neo4j reales
(no mockeados) al menos una vez (`doc/079`–`096`, `FIL_13`/`14`, y el
recorrido de `VIKT_06`), y cada respuesta incluye su fuente (tabla Gold,
consulta al grafo, o modelo servido) trazable. Cuando falta un dato, la
tool lo dice explícitamente (`disponible=false` + motivo) en vez de
rellenar el hueco.

**¿Qué pasó con los incidentes reales de producción?**
Cuatro incidentes reales se diagnosticaron con causa raíz, se corrigieron
y se verificaron contra datos reales: una librería de Glue compartida
rota (28h de fallos horarios), un patrón de "job SUCCEEDED pero escribe 0
filas" en dos datasets distintos (encontrado dos veces, con el mismo
diagnóstico), y una caída de 28h en la ingesta de Bluesky por un cambio
de política del proveedor. Es evidencia de que el sistema se opera con
rigor real, no solo se construye una vez y se abandona.

## 4. Diagrama "memoria vs. construido vs. futuro"

| | En la memoria | Construido y verificado | Solo futuro (§7.5) |
|---|---|---|---|
| Ingesta | 24 fuentes, 16 en producción continua | ✅ igual, + `parques_jardines`/`ser_calles` ya con Lambda (Bronze-only) | Recarga vehículo eléctrico, plazas PMR, infraestructura ciclista |
| Procesamiento | Lakehouse medallón + Great Expectations | ✅ igual | Delta Lake, Kafka/Flink (ruta caliente) |
| Grafo | 5 labels, 4 relaciones | ✅ igual, 9.633 nodos / 72.310 relaciones reales | Enriquecimiento OSM completo (hoy: muestra) |
| Modelado | LightGBM + STGNN, Tabla 3 | ✅ ambos entrenados y evaluados; **Tabla 3 publicada puede no coincidir con el código actual, y el skill es volátil día a día** (ver checklist §1); STGNN exportable a ONNX (`FIL_20`) **y ya integrado como 10.ª tool** (`calidad_aire_prevista_grafo`, `FIL_26`) — pierde a LightGBM en métricas puntuales a 1h pero aporta explicabilidad de grafo (vecinos influyentes) | Ablaciones descartadas por tiempo |
| Asistente | "Siete" tools (memoria sin actualizar) | ✅ **nueve** tools reales (`FIL_13`/`14`) | Auth/rate-limiting, cuadro de mando Power BI |
| Operación | — | ✅ alertado diseñado (`FIL_16`), secretos en runtime (`FIL_17`), test e2e (`FIL_18`), README raíz (`FIL_19`) — ninguno mencionado aún en la memoria | Rotación de secretos, trazas distribuidas |

## Estado de este ticket

- ✅ Checklist editorial (sección 1) — preparada, sin marcar (requiere lectura humana).
- ✅ `doc/VIKT-10-defensa.md` (este documento) — completo.
- ⬜ Lista de erratas aplicada al `.docx` — depende de que se apliquen primero los fixes de `VIKT_07`/`VIKT_09` (bloqueados por permisos de esta sesión, ver ambos documentos).
- ⬜ Lectura editorial humana completa — pendiente, requiere a Víctor y/o Filippos.

**Este ticket permanece `status: pending`** — la parte de Claude está
lista, pero el criterio de aceptación real ("el `.docx` pasa la checklist
... guion de defensa Y Q&A cerrados") necesita la lectura humana que este
ticket explícitamente no permite sustituir.
