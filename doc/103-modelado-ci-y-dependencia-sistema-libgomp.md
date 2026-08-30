# 103 — QA: `modelado/` fuera de la CI + dependencia de sistema `libgomp1`

## Contexto

Al comprobar si `VIC_05` podía avanzar (necesita las salidas reales de
`ML_03`/Tier 1 y `ML_05`/Tier 2), se auditó el estado real de `ML_01`–`ML_03`
en una sesión previa (commit `6ac24a5`). Dos hallazgos, cerrados aquí:

1. `modelado/tests/test_ml03.py` fallaba al importar con
   `OSError: libgomp.so.1: cannot open shared object file: No such file or
   directory`. No es un bug de código: `lightgbm` (Tier 1) enlaza en tiempo
   de importación contra `libgomp.so.1` (runtime de OpenMP), y esta EC2 no
   lo traía preinstalado como librería de sistema. Se instaló con
   `sudo apt-get install -y libgomp1` en esa sesión previa (ya presente en
   esta EC2, verificado con `dpkg -l | grep libgomp` antes de esta pasada:
   `libgomp1:amd64 16-20260322-1ubuntu1`), y los 3 tests de `ML_03` pasan
   limpios. Sin este paso, cualquier sesión nueva en una EC2 sin el paquete
   vería el mismo fallo y podría malinterpretarlo como una regresión real
   del código de `modelado/`.
2. `.github/workflows/ci.yml` (tarea 097) no incluía `modelado/` en
   absoluto — solo corría `pytest ingesta/ procesamiento/ grafo/ asistente/
   herramientas/`. El track de ML, "el elemento central del TFM" según
   `NEXT_STEPS.md`, era el único módulo sin ninguna cobertura automática.

La corrección de `status` desactualizado en el front-matter de `ML_02`/
`ML_03` (`pending` → `done`, con `ML_01` dejado en `pending` porque su
propia nota ya admite gaps reales de join de meteo/festivos) se aplicó en
el commit previo `6ac24a5`, no en este.

## Cambios de esta tarea

### `.github/workflows/ci.yml`

- `modelado/` se añade al job `tests`: se instala
  `modelado/requirements.txt` (mismo patrón que el resto de módulos) y se
  incluye en la línea de `pytest` y en `cache-dependency-path`.
- Paso nuevo **`sudo apt-get install -y libgomp1`** antes de instalar
  `modelado/requirements.txt`, explícito e incondicional.

### Decisión: instalar `libgomp1` siempre, sin verificarlo primero

El ticket pedía verificar en un run real de GitHub Actions si las imágenes
`ubuntu-latest` ya traen `libgomp1` preinstalado, en vez de asumirlo. Desde
este worktree no es posible disparar un run real de GitHub Actions (no se
hace `git push`; un orquestador externo se encarga de eso tras esta tarea),
así que no hay forma de confirmarlo empíricamente en esta sesión.

Ante esa incertidumbre, la decisión tomada es instalar el paquete siempre
de forma explícita y defensiva, en vez de condicionar el paso a un
resultado no verificado:

- Si el runner ya lo trae (lo más probable — `libgomp1` es dependencia de
  `gcc`/`libstdc++`, presente en la mayoría de imágenes base de Ubuntu con
  toolchain de compilación), `apt-get install` es un no-op de pocos
  segundos.
- Si no lo trae, el paso evita que la CI falle igual que falló en esta EC2.

El coste de este paso "por si acaso" es mínimo frente al riesgo de dejar la
CI rota por una dependencia de sistema no verificable desde aquí.
**Seguimiento real**: la próxima vez que alguien inspeccione un run de esta
CI en GitHub Actions, confirmar cuánto tarda ese paso (si es near-instant,
confirma que el paquete ya estaba) y, si se confirma que sobra, se puede
quitar en un ticket de limpieza — no se ha hecho aquí para no dejar la CI
en un estado sin verificar.

### `modelado/README.md`

Sección nueva "Prerrequisito de sistema: `libgomp1`" documentando el
síntoma exacto (`OSError: libgomp.so.1: ...`), que no es una regresión de
código, el comando de instalación, y que la CI ya lo cubre — para que una
sesión interactiva nueva en una EC2 sin el paquete no pierda tiempo
diagnosticando el mismo error otra vez.

## Verificación realizada

- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
  → el YAML resultante es válido.
- `dpkg -l | grep libgomp` en esta EC2 → `libgomp1` ya presente (instalado
  en la sesión de auditoría previa), confirma que el síntoma diagnosticado
  es real y que el paquete es la causa raíz, no otra cosa.
- **No** se ha ejecutado `pip install -r modelado/requirements.txt` completo
  en esta pasada ni se ha vuelto a correr `pytest modelado/`: el disco de
  esta EC2 está al 95 % (`df -h /` → 376 M libres), y `torch`/`mlflow`
  (`ML_04`/`ML_05`) son pesados — instalarlos agotaría el disco compartido
  con el propio pipeline. Los resultados de `ML_02`/`ML_03` en verde ya
  están verificados y documentados (`doc/ML-02-splits-baselines-metricas.md`,
  `doc/ML-03-tier1-lightgbm-shap.md`, y la
  auditoría del commit `6ac24a5`); no hacía falta re-verificarlos para este
  ticket, que es un cambio de CI/documentación, no de lógica de `modelado/`.
- No se ha modificado ninguna lógica de `modelado/` — cambio acotado a CI +
  documentación, como pide el ticket.

## Pendiente / seguimiento

- Confirmar en un run real de GitHub Actions si el paso `apt-get install
  libgomp1` es un no-op (paquete ya presente) o instala algo de verdad; si
  es no-op de forma consistente, se puede simplificar a un comentario de
  documentación sin el paso, en un ticket aparte.
- Vigilar el tiempo total del job `tests` en CI: `torch`+`lightgbm`+`mlflow`
  son las dependencias más pesadas del repo — si el tiempo de instalación
  se vuelve un problema, considerar separar `modelado/` en un job de CI
  propio con su propia caché de pip.
