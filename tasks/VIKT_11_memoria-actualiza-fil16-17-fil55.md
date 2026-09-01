---
kind: vikt
title: "Memoria — incorporar los deltas de ingeniería del 2026-09-01 (FIL_17 aplicado, FIL_16 parcial, FIL_55 mapa, ventana de re-congelación)"
owner: Pista Memoria (Víctor + Filippos)
status: pending
depends_on: [VIKT_07, VIKT_09]
---

## Contexto

El 2026-09-01, después de que `VIC_*`/`VIKT_*` dieran por estable la
memoria, una sesión interactiva cambió tres cosas que el `.docx` aún
describe con el estado anterior:

1. **`FIL_17` — secretos en runtime — pasó de "diseñado" a "aplicado y
   verificado"** contra AWS. Los 4 productores con credencial
   (`aemet_prevision_avisos`, `bluesky_menciones`, `cams_calidad_aire`,
   `transporte_publico_emt`) ya **no** llevan el valor del secreto en el
   env de la Lambda: lo leen de SSM en runtime
   (`ingesta/capturas/secretos.py`), con una política IAM de `ssm:GetParameter`
   acotada a los 6 ARNs concretos. Verificado con un `invoke` real
   (`200`, 16 filas a Bronze leyendo la clave de SSM).
2. **`FIL_16` — observabilidad — parcialmente desplegada.** La regla
   EventBridge que detecta jobs de Glue en `FAILED/TIMEOUT/ERROR` está
   **creada y `ENABLED`**; solo el canal de notificación SNS se queda sin
   cablear (falta un permiso IAM de SNS al `madrono-terraform-deployer`;
   decisión del usuario: "basta con que esté bien construido"). Es una
   pieza **diseño-completo, despliegue-diferido**, no un hueco.
3. **`FIL_55` — el mapa animado publicado tenía un bug** que rompía el
   panel de resumen y el pulso de distrito al elegir cualquiera de los 9
   perfiles de sensibilidad o las métricas de dosis (la capa social de
   `FIL_45`). Corregido y redesplegado a `gh-pages` (PR #234); sitio en
   vivo verificado.
4. **El pipeline se reanudó ~24 min** el 2026-09-01 para poder aplicar y
   verificar `FIL_16`/`FIL_17` end-to-end, y **se volvió a congelar**
   (`pipeline_enabled=false`). No contradice "congelado desde el
   2026-08-30" — es una ventana puntual de mantenimiento.

## Objetivo — dónde toca en el `.docx` (`documents/Memoria_TFM FV.docx`)

Añadir/corregir, sin reescribir lo que ya está bien (`VIKT_*` **añade y
corrige**):

- **§6.8 (explotación/ética) y/o §5 (arquitectura, sub-apartado de
  seguridad) y/o Anexo de reproducibilidad**: donde se hable de gestión
  de credenciales, decir que los secretos de los productores se leen de
  **AWS SSM Parameter Store (`SecureString`) en tiempo de ejecución**, con
  IAM de mínimo privilegio (6 parámetros concretos), **no** inyectados como
  variable de entorno. Si §7 lo listaba como línea futura o como
  limitación ("secretos en claro"), moverlo a "resuelto".
- **§7.4 Limitaciones** — el punto "sin alertado" de la lista consolidada
  de `VIKT_07` pasa a matizado: *la detección de fallos de Glue está
  desplegada (regla EventBridge activa); queda pendiente solo el canal de
  aviso (SNS), una decisión de alcance, no una carencia de diseño*.
- **§ Visualización animada del grafo** (la que introdujo `FIL_36`, con la
  figura `viz/mapa_frames.png`): confirmar que el texto describe la capa
  social/accesibilidad (9 perfiles, bandas OMS·UE, métricas de dosis,
  "mejor hora") como **funcional**. Si alguna captura de pantalla o la
  figura muestra el estado roto del panel de resumen, **rehacerla** tras
  `python -m viz.build_mapa_animado`.
- **§7.4 / narrativa de congelación del pipeline** (aparece en `VIKT-06`,
  `VIKT-07`, `VIKT-08`, `VIKT-09`, `VIKT-10`): añadir una nota de que hubo
  una reanudación breve (~24 min, 2026-09-01) para aplicar
  `FIL_16`/`FIL_17`; el pipeline sigue congelado. Que no quede como
  contradicción con "sin ingestión nueva desde el 2026-08-30".

## Fuentes técnicas (leer antes de escribir)

- `doc/FIL-16-alertado-salud-pipeline.md`, `doc/FIL-17-secretos-runtime-ssm.md`.
- `tasks/FIL_55_mapa-resumen-rompe-con-metricas-de-perfil.md` + PR #234.
- `PROGRESS.md` — entrada 2026-09-01.
- `ingesta/capturas/secretos.py`, `infra/terraform/observabilidad.tf`.
- El informe de `VIC_33` (verificación independiente del estado de AWS) —
  **esperar a que cierre** antes de afirmar en la memoria que `FIL_17`
  está "verificado".

## Alcance / entregables

- Ediciones en el `.docx` con `python-docx` (preserva estilos/numeración).
- Figura `mapa_frames.png` rehecha si mostraba el bug.
- Lista de párrafos tocados en `doc/VIKT-11-...md` para la trazabilidad de
  `VIKT_09` (pasada final).

## Criterios de aceptación

- Ninguna afirmación del cuerpo contradice el estado del repo a fecha de
  este ticket (grep de "secreto"/"env"/"alertado"/"congelado" + lectura de
  los apartados tocados).
- La memoria no sobreclama: `FIL_16` se describe como parcial-por-decisión,
  no como "alertado en producción".
- `VIKT_09` puede cerrar sin encontrar estas 4 discrepancias.

## Restricciones

- `.docx` binario: `git pull` + aviso en el chat antes de tocarlo (ver
  `PLAN.md` §"Memoria — reparto"). No editar a la vez que `VIKT_09`/`10`.
- Requiere que `VIC_33` haya verificado el estado de AWS primero.
- `VIKT_*` añade y corrige; no reabrir §5.2 / §6 / Tabla 3.

## Adenda QA (Claude, 2026-09-01) — `VIC_33` ya cerró; evaluación de
## disponibilidad real antes de tocar el `.docx`, no una redacción lista

`VIC_33` cerró hoy (`doc/VIC-33-eval-fil16-17-terraform.md`): `FIL_17`
verificado como aplicado y correcto (sin secretos en claro, IAM de
mínimo privilegio con los 6 ARNs exactos, ruta de código correcta),
`FIL_16` verificado como parcial-aceptado (regla `ENABLED`, sin
`Targets`, sin topic SNS), pipeline congelado confirmado (23/23
schedulers `DISABLED`, 27/27 triggers `DEACTIVATED`). Este ticket ya
puede afirmar "verificado" con base real, no solo con lo que reportó la
sesión interactiva.

**Pero, con lectura real del `.docx` actual (solo lectura, sin editar
—`python-docx` en modo lectura no está bloqueado igual que la escritura,
comprobado hoy)**: el `.docx` está **más atrasado** de lo que este ticket
asume. Ninguna de las palabras "SNS", "notificaci[ón]", "correo",
"aviso", "congelad[o]", "SSM", "credencial", "secreto" ni "mapa animado"
aparece en ninguno de los 145 párrafos del documento. Es decir:

- No hay ningún párrafo de gestión de secretos que "corregir" en §5/§6 —
  hay que **añadir uno nuevo**, no editar uno existente.
- §7.4 (párrafos 108-118, "Limitaciones identificadas") **no** contiene
  ningún punto sobre alertado/observabilidad de Glue — el punto que
  `VIKT_09` citaba (antes en el párrafo 116 de esa sesión) no está en el
  `.docx` real de hoy, confirma que **ninguna de las ediciones de
  `VIKT_07`/`VIKT_09` se ha aplicado todavía** (ambas siguen en
  `status: done` porque el *redactado* estaba listo, no porque se
  aplicara — mismo patrón ya visto: "Claude prepara, un humano aplica").
- No existe ninguna sección "Visualización animada del grafo" — el
  párrafo 130 (§7.5) sigue diciendo literalmente *"Exportar el STGNN a
  ONNX: hoy bloqueado..."* y el 131 sigue diciendo *"...hoy sin
  implementar en el panel de entrenamiento"* — la redacción **original**,
  de antes incluso de `FIL_20`/`FIL_26`/`ML_01`. `FIL_36` (la sección del
  mapa) tampoco se ha aplicado.

**Implicación práctica**: los índices de párrafo de este ticket (y de
`VIKT_05`/`07`/`09`) van a **desplazarse** en cuanto se aplique cualquier
inserción — no tiene sentido fijar aquí "párrafo N: dice X, debería decir
Y" con precisión falsa cuando ni siquiera existe el párrafo de destino
todavía. **Recomendación de orden de aplicación** (para quien coja esto):
1º `VIKT_07`/`09` (correcciones a texto ya existente, más simple, no
depende de nada más), 2º `FIL_36` (añade la sección del mapa), 3º recién
entonces este ticket (`VIKT_11`, que depende de contenido que los 2
anteriores todavía no han creado). Aplicar `VIKT_11` antes que eso sería
insertar contenido sobre secretos/alertado sin nada que lo referencie
todavía en el hilo narrativo de §5-7.

No se marca `status: done` — sigue bloqueado por la edición real del
`.docx`, y además ahora se sabe que tiene dependencias de orden más
estrictas de las que su propio `depends_on` declara.
