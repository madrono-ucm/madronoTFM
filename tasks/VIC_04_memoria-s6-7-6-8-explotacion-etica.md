---
kind: vic
title: "Memoria §6.7 Explotación de resultados · §6.8 Ética/legal"
owner: Víctor
status: done
done_by: "Claude (Sonnet 5)"
done_at: "2026-08-29"
created_at: "2026-08-28"
---

## Fuente técnica

- `asistente/README.md` — las 6 tools reales del agente MCP
  (`calidad_aire`, `trafico_cercano`, `afluencia_estimada`,
  `disponibilidad_aparcamiento`, `eventos_cercanos`, `opciones_movilidad`),
  ninguna con `NotImplementedError`.
- `doc/079`, `doc/081`, `doc/089`, `doc/090`, `doc/091`, `doc/095`,
  `doc/096` — una tool por doc.
- `doc/012` §"zona gris académica" y `doc/083` (Google Maps descartado a
  nivel de código, coste 0 imposible).
- `NEXT_STEPS.md` §5.1 (afluencia derivada) y §5.4 (Power BI retirado).
- ML tickets — la 7ª tool `*_prevista` servida desde ONNX (Tier 4).

## Qué cambia

- **§6.7** — quitar la "cara analítica = cuadro de mando Power BI". La
  explotación es: (1) el **asistente conversacional** «Madroño» (FastAPI +
  agente MCP, respuesta con veredicto + nivel de fiabilidad según cuántas
  señales reales había + explicación trazable), y (2) los **cuadernos de
  evaluación de `modelado/`** para la visión analítica/agregada. El ejemplo
  "¿voy al centro el viernes a las 21h?" sigue valiendo — actualizar la
  lista de tools invocadas a las 6 reales + `*_prevista` cuando exista.
  Power BI → §7.5.
- **§6.8** — la obtención de afluencia de lugares vía librería open source
  en zona gris **ya no es una dependencia activa**: se sustituyó por una
  señal derivada de sensores propios vía el grafo (tarea 089 + `FIL_06`),
  toda a coste 0 y sin condiciones de uso de terceros. Reescribir el párrafo
  de "zona gris" como: se evaluó esa vía, se descartó por incompatibilidad
  con el coste 0 y con las condiciones de uso (`doc/083`), y un proveedor
  comercial con licencia queda como futura línea (§7.5). Mantener el resto
  de §6.8 (tratamiento agregado de señales sociales sin identificadores,
  descarte de datasets con datos personales, RGPD) — sigue vigente.

## Qué se mantiene

- La estructura "cara ciudadana / cara analítica" — solo cambia qué llena
  cada una.
- El principio de respuesta explicable y cuantificada en fiabilidad.

## Aceptación

- §6.7 no menciona Power BI como entregable.
- §6.8 no presenta la zona gris de Google como dependencia del sistema
  entregado; la reubica como alternativa descartada / futura línea.

## Hecho (29/8)

§6.7/§6.8 reescritas en `documents/Memoria_TFM FV.docx`. §6.7 describe las
6 tools reales del asistente (sin Power BI, movido a §7.5) y menciona la
séptima tool `*_prevista` de forma condicional ("cuando esté disponible"),
sin afirmar que ya exista. §6.8 reencuadra la "zona gris" de Google como
vía evaluada y descartada (coste 0 imposible, `doc/083`), no como
dependencia activa.
