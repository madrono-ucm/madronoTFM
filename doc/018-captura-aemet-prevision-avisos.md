# 018 — Captura de previsión meteorológica y avisos de AEMET (muestra)

## Qué se implementó

`ingesta/capturas/aemet_prevision_avisos.py`: productor de dos señales
oficiales de AEMET OpenData para Madrid, complementarias al tiempo
**actual** que ya captura `meteorologia_madrid.py` (tarea 008):

- `fetch_prediccion(config, municipio_code="28079")`: previsión **diaria**
  (7 días) para Madrid capital.
- `fetch_avisos(config, area_code="72")`: avisos vigentes de fenómenos
  meteorológicos adversos para la provincia/Comunidad de Madrid.

Ambos endpoints siguen el mismo patrón de "envoltorio en dos pasos" de toda
la API de AEMET OpenData (la llamada con `api_key` no trae el dato, trae una
URL a él) y requieren `AEMET_API_KEY` (variable de entorno, nunca
hardcodeada). Documentación completa (esquemas, variables de entorno,
cadencia real de publicación) en `ingesta/README.md`, sección
`capturas/aemet_prevision_avisos.py`.

## Bloqueo de registro (documentado, mismo patrón que tareas 003 y 012)

Se investigó en vivo el formulario de alta de AEMET OpenData
(`opendata.aemet.es/centrodedescargas/altaUsuario`): **exige resolver un
reCAPTCHA de Google** antes de poder enviarse, sin ninguna vía alternativa.
Es un bloqueo manual no automatizable en este pipeline. Se verificó también
que el servicio exige un `api_key` con forma de JWT y no acepta ninguna
clave de prueba pública.

Por eso, siguiendo la instrucción explícita del enunciado para este caso: el
código queda completo y listo para ejecutarse tal cual el día que alguien
complete el alta manualmente, y la muestra commiteada se generó a mano,
marcada `"is_mock": true` en cada registro (mismo patrón que
`afluencia_lugares_madrid.py`, tarea 012).

**Verificación parcial en vivo, pese al bloqueo:** con una clave con forma
de JWT pero inválida, se comprobó que ambos endpoints devuelven `401` de
forma esperada — la petición llega bien construida hasta AEMET, el único
motivo del fallo es la falta de una key real. No es una captura real, pero
sí confirma que el código funciona hasta donde puede sin la credencial.

## El esquema no es una suposición: se obtuvo y se contrastó en vivo, sin key

Dos hallazgos en vivo permitieron construir una muestra de alta fidelidad
pese al bloqueo, en vez de datos totalmente inventados:

1. **La especificación OpenAPI completa de AEMET es pública, sin
   autenticación** (`https://opendata.aemet.es/AEMET_OpenData_specification.json`,
   verificado `200 OK`). De ahí salieron, con certeza, los dos endpoints
   usados, sus parámetros (incluida la tabla de códigos de área CCAA — `72`
   = Madrid), y el esquema exacto del envoltorio de dos pasos.
2. **El esquema del payload de previsión diaria se contrastó con datos
   reales y en vivo** de Madrid capital: AEMET expone, sin ninguna key, un
   feed XML legado que su propia web usa para pintar la ficha de cada
   municipio (`https://www.aemet.es/xml/municipios/localidad_28079.xml`,
   `200 OK` en vivo). Trae los mismos campos que el JSON de OpenData
   documentado en la especificación (solo que en XML/snake_case en vez de
   JSON/camelCase). Los valores numéricos de la muestra commiteada de
   previsión (`aemet_prevision_madrid_sample.json`) son esos valores reales
   capturados en vivo el 13 de agosto de 2026 (máximas de 34-38°C, avisando
   ya de una ola de calor real en curso), reestructurados a mano al esquema
   JSON documentado — no inventados, aunque no se obtuvieron por el
   endpoint de pago-con-key que pedía la tarea (de ahí que se mantenga
   `is_mock: true`).

Solo se implementó la previsión **diaria**, no la horaria: aunque comparten
el mismo envoltorio, el payload horario tiene una forma distinta que no se
pudo contrastar con datos reales en esta sesión (no existe un feed legado
equivalente sin key para horaria; las URLs candidatas probadas en vivo
devuelven `404`). Se prefirió dejarla fuera antes que implementar un
parseo sin forma de verificarlo.

El esquema de avisos (CAP 1.2 dentro de un `.tar.gz`) se basó en el estándar
CAP y en la página de ayuda pública de AEMET
(`aemet.es/es/eltiempo/prediccion/avisos/ayuda`, consultada en vivo: da los
tres niveles amarillo/naranja/rojo y los parámetros propios
`AEMET-Meteoalerta nivel`/`fenomeno`/`zona`), pero **no se pudo contrastar
contra un documento CAP real** — se documenta explícitamente como de menor
confianza que la previsión diaria, tanto en el docstring del módulo como en
`ingesta/README.md`.

## Cadencia real de publicación (investigada en vivo, para el futuro scheduling)

- **Previsión diaria**: la propia especificación OpenAPI la documenta como
  actualizada "continuamente" (no hay un número fijo de veces al día).
- **Avisos**: AEMET documenta públicamente periodos preferentes de emisión
  (hora peninsular): 07:30-09:00 (avisos de hoy), 10:30-11:30 (D+1/D+2),
  17:00-19:00 (revisión general), 23:50 (avance D+3). Un scheduling real
  debería sondear en esos huecos, no en un intervalo arbitrario.

Detalle completo en `ingesta/README.md`.

## Tests

`ingesta/tests/test_aemet_prevision_avisos.py`: no dependen de la red.
Fixtures: `fixtures/aemet_prediccion_diaria_sample.json` (payload en el
esquema real de OpenData, construido con los valores reales de Madrid del
punto anterior) y `fixtures/aemet_avisos_cap_sample.xml` (documento CAP 1.2
con dos bloques `<info>` -es-ES/en-GB- para probar el filtrado por idioma).
Cubren `normalize_prediccion_dia` (incluyendo el caso real de racha máxima
ausente para el periodo del día completo), `parse_cap_alert`/
`normalize_aviso` (incluido el fallback a campos CAP estándar cuando faltan
los parámetros propios de AEMET), `_extract_cap_xml_documents` (con un tar
en memoria) y una verificación de esquema sobre ambas muestras commiteadas.
Suite completa del proyecto verificada tras el cambio: 139 tests (124
previos + 15 nuevos), todos en verde.

## Relevante para tareas futuras

- Este es el tercer bloqueo de registro documentado del proyecto (tras la
  EMT en la tarea 003 y Google Maps en la tarea 012), todos por el mismo
  motivo de fondo: un paso de verificación manual (email o CAPTCHA) que
  este pipeline autónomo no puede completar. El patrón de solución
  (código completo y listo + muestra a mano con `is_mock: true`) sigue
  siendo el correcto para estos casos; no hace falta reinventarlo.
- Si una tarea futura completa el alta y configura `AEMET_API_KEY`, el
  código de previsión diaria y avisos debería funcionar tal cual (base
  verificada contra la especificación OpenAPI oficial y, para la previsión,
  contra datos reales), pero conviene **volver a contrastar el parseo de
  avisos (`parse_cap_alert`/`_extract_cap_xml_documents`) contra un
  `.tar.gz` real de AEMET en cuanto haya una key**, ya que esa parte es la
  de menor confianza de este módulo (nunca se pudo verificar en vivo).
- Si esa misma tarea futura quiere añadir la previsión horaria, debería
  primero conseguir un ejemplo real del payload (con la key ya
  disponible) antes de escribir el normalizador, en vez de asumir la forma
  del esquema — la falta de un feed público de contraste fue precisamente
  la razón para no implementarla en esta tarea.
- El feed legado sin key (`aemet.es/xml/municipios/localidad_{municipio}.xml`)
  usado aquí solo para contrastar el esquema **no sustituye** al objetivo
  de la tarea (usar la API OpenData con key): es XML, no está en el
  alcance oficial de "OpenData", y no expone avisos. Se documenta como lo
  que es, una fuente de verificación puntual, no como una alternativa
  productiva a integrar en lugar de OpenData.
