---
kind: vikt
title: "Coordinación de la revisión editorial humana del .docx + preparación de la defensa"
owner: Pista Memoria (Víctor + Filippos)
status: pending
created_at: "2026-08-30"
depends_on: [VIKT_06, VIKT_07, VIKT_09]
---

## Contexto

Todo el trabajo de `VIC_*`/`VIKT_*` ha sido reescritura y verificación
técnica. Falta la **lectura humana completa** del `.docx` (coherencia de
estilo, hilo argumental, figuras, bibliografía, formato de entrega) y la
preparación de la defensa. No es una tarea de código.

## Objetivo

1. **Revisión editorial** — una pasada humana de principio a fin de
   `documents/Memoria_TFM FV.docx`:
   - numeración/estilos consistentes (las ediciones con `python-docx` a
     veces dejan artefactos),
   - figuras/tablas referenciadas desde el texto y con pie,
   - abstract/conclusiones alineados con §7 real,
   - bibliografía y formato según la plantilla de la universidad,
   - portada/metadatos.
2. **Preparación de la defensa** — `doc/VIKT-10-defensa.md`:
   - guion apoyado en `VIKT_06` (recorrido e2e),
   - preguntas anticipadas y respuestas: *por qué no Kafka/Flink/Delta*
     (coste 0, decisión de §5.4), *por qué el pipeline está congelado*
     (acotar gasto, corrió 14/8–30/8), *por qué el STGNN no se sirve*
     (`torch.export`, §7.4/§7.5), *ventana de datos corta*, *EMT una parada*,
   - diagrama "lo que dice la memoria vs lo construido vs lo futuro".

## Alcance / entregables

- Checklist de revisión editorial marcada.
- `doc/VIKT-10-defensa.md`.
- Lista de erratas/ajustes finales aplicada al `.docx`.

## Criterios de aceptación

- El `.docx` pasa la checklist editorial y está en formato de entrega.
- Guion de defensa + Q&A cerrados.

## Restricciones

- Requiere un humano (Víctor y/o Filippos). Claude puede preparar la
  checklist, el `doc/VIKT-10-defensa.md` y aplicar erratas concretas, no
  sustituir la lectura.
- Última tarea de la pista. `git pull` + aviso antes de tocar el `.docx`.

## Hecho parcialmente (30/8, Claude) — sigue `status: pending`

La parte que este ticket asigna explícitamente a Claude está lista en
[`doc/VIKT-10-defensa.md`](../doc/VIKT-10-defensa.md): checklist editorial
(sin marcar — requiere lectura humana), guion de defensa completo apoyado
en `VIKT_06`, las 7 preguntas anticipadas con respuesta, y la tabla
"memoria vs. construido vs. futuro". **No se marca `status: done`**: los
criterios de aceptación reales (`.docx` pasa la checklist, erratas
aplicadas) requieren la lectura editorial humana que este mismo ticket
dice explícitamente que Claude no debe sustituir — y, además, los fixes de
`VIKT_07`/`VIKT_09` que alimentarían esas erratas están redactados pero
sin aplicar al `.docx` (bloqueo del clasificador de modo automático de
esta sesión, documentado en ambos tickets). Queda para Víctor/Filippos:
leer, aplicar los 3 documentos de fixes (`VIKT-07`, `VIKT-09`, y la
decisión de Tabla 3 de `VIKT-05`), y cerrar este ticket.
