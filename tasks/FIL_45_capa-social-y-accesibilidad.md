---
kind: fil
title: "Mapa animado — capa social y de accesibilidad (perfiles de sensibilidad, umbrales OMS/UE, dosis, mejor hora)"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_34]
milestone: "M4b"
target: "2026-09-11"
---

## Objetivo

Que el mapa hable el idioma de la gente a la que afecta la calidad del aire,
no el de los µg/m³. Una capa sobre el mapa animado (`FIL_34`/`FIL_35`) que
colorea por **bandas de umbral OMS/UE**, deja elegir un **perfil de
sensibilidad**, muestra la **dosis acumulada** de una ventana y la **mejor
hora de hoy** para salir.

## Alcance

### Perfiles de sensibilidad
`perfil ∈ {general, asma_epoc, mayor, infancia, ciclista, movilidad_reducida,
trabajo_exterior}`. **Reutilizan el mismo dict de pesos que `ruta_saludable`**
(`FIL_37`, `PERFILES` en `viz/rutas.py` / `grafo_ruta.json`) — un perfil es
un vector de pesos por señal (tráfico/NO₂/O₃/ruido), no una lógica aparte.
`FIL_37` añade `movilidad_reducida` y `trabajo_exterior` a ese dict.

### Color por banda de umbral, no por valor crudo
El color de nodo pasa a mapear **bandas OMS/UE** (p. ej. NO₂: guía OMS
24 h 25 µg/m³; O₃: umbral de información 180 µg/m³, objetivo 8 h 120 µg/m³)
en vez de una rampa lineal sobre µg/m³. La leyenda nombra la banda
("por debajo de la guía OMS", "supera el objetivo UE", …), no el número.
Fuente de umbrales documentada en el propio módulo.

### Dosis acumulada
Por nodo y ventana (p. ej. las próximas 8 h desde la hora del slider):
`% de la guía diaria` = Σ(exposición prevista) / guía · 100. Toggle de capa;
tooltip por nodo.

### "Mejor hora hoy"
Barrido de las 24 h del día curado: para el perfil elegido, la hora que
minimiza la exposición ponderada (misma cantidad que `ruta_saludable`
minimiza tras `FIL_43`). Se muestra como un marcador en el timeline + texto.

### Toggle de confianza de la IDW
Capa opcional que sombrea los nodos por **distancia a la estación de aire
más cercana** (las 11 del STGNN): lejos = interpolación poco fiable (gap
G4). Es honestidad visual, no un dato nuevo.

### UI en español primero, accesible
- Todos los textos de control y leyenda en español; inglés solo en tooltips
  técnicos si hace falta.
- Contraste **AA** (WCAG 2.1) en texto y en los pares figura/fondo; las
  bandas de color elegidas para ser distinguibles en deuteranopía.
- Navegable por teclado: foco visible, `Tab`/flechas para el timeline y los
  selectores, `aria-label` en los controles.

## Guardarraíles (declararlos en el propio panel y en la memoria)

- **Solo agregados por zona** (nodo / distrito). Ningún dato personal, ningún
  cruce con padrón ni con datos de salud individuales.
- Encuadre **"condiciones / previsión"**, nunca un mapa que señale barrios
  como "malos" — se describe el aire y la hora, no el sitio ni quién vive.
- **Apoyo a la decisión, no consejo médico.** El panel lo dice literalmente;
  ninguna cadena del tipo "no salgas" — sí "el aire mejora a partir de las N".

## Qué NO hace

- **No** hace análisis distribucional formal (exposición × vulnerabilidad
  socioeconómica con test estadístico). Eso queda como **párrafo de
  encuadre en `FIL_36`** (sección "Beneficiarios" / justicia ambiental), no
  como entregable.
- No añade fuentes de datos nuevas: reutiliza `prevision_animada.parquet`
  (`FIL_33`, que amplía sus columnas para esto) + los umbrales OMS/UE como
  constantes.

## Coste

Cero AWS. Todo offline sobre los artefactos ya en repo.

## Verificación

Tests bajo `tests/` (el CI no recorre `viz/`): bandas de umbral bien
asignadas, dosis = Σ/guía, "mejor hora" coincide con el mínimo del barrido,
perfiles = los mismos pesos que `ruta_saludable`.

## Entregable / progreso

Milestone **M4b** en `viz/PROGRESO_MAPA.md`.


## Resolución (2026-08-31) — `viz/build_mapa_animado.py`

- **9 perfiles de sensibilidad** en `viz/rutas.py::PERFILES` (compartido con
  `ruta_saludable`, `FIL_37`; `_PERFILES_RUTA` en `tools.py` a 9): general,
  ciclista, sensible_aire, sensible_ruido + **asma_epoc, mayor, infancia,
  movilidad_reducida, trabajo_exterior**. `grafo_ruta.json` regenerado.
- Mapa (`_meta` + `_TEMPLATE`): grupo **♿ Salud · perfil de sensibilidad**
  con los 9 perfiles → métrica **`salud (perfil)`** calculada en el
  navegador (`w_traf·no2·o3·noise` normalizados, ruido = valor diario del
  distrito).
- **Escala lineal / bandas OMS·UE**: en modo bandas el color de nodo es
  discreto por umbral (`meta.umbrales`: NO₂ 25/40/100/200; O₃
  100/120/180/240; salud 60/70/80/90) con paleta distinguible en
  deuteranopía; la leyenda **nombra la banda**, no el número.
- Métricas **`dosis NO₂`** / **`dosis O₃`**: media de la exposición prevista
  de las próximas 8 h como % de la guía OMS.
- **"Mejor hora hoy"** por perfil: barrido de 24 h de la salud media de la
  ciudad → mejor y peor hora, en el propio grupo.
- **Confianza de la IDW**: capa opcional que marca los nodos con
  `idw_dist_m` grande (lejos de las 11 estaciones de aire — gap G4).
- **Guardarraíles** siempre visibles en el panel: agregados por zona, sin
  datos personales, describe el aire y la hora (no señala barrios), apoyo a
  la decisión no consejo médico.
- UI en español, `:focus-visible`, `aria-label` (heredado de `FIL_47`).

`tests/test_mapa_animado.py` +2. `tests/` 40, `asistente/` en verde.
El análisis distribucional formal sigue fuera (encuadre en `FIL_36`).
