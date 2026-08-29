# 105 — Desplegar el cron de reentrenamiento nocturno (ML_10)

## Hallazgo confirmado

`ls -la /etc/cron.d/` y `crontab -l` en esta misma EC2 (la del demonio,
donde vive `infra/OPERACION.md`) confirman lo que decía el ticket: el
`cron.d` de `ML_10` **nunca se instaló**. Solo hay el `.placeholder` y el
`e2scrub_all` de Debian; no hay ninguna entrada de `ubuntu`.

Además, al preparar la instalación real aparecieron dos bloqueos que la
plantilla original de `doc/ML-10-...md` no contemplaba:

1. **`/opt/madrono` no existe.** Esta EC2 tiene dos checkouts manuales del
   repo (`~/repos/madronoTFM` y `~/repos/madronoTFM-agent`, ver
   `doc/104-ec2-root-volume-al-limite.md`), ninguno en `/opt`. La línea de
   cron documentada apuntaba a una ruta que nunca existió en esta máquina.
2. **No hay ningún venv con las dependencias de `modelado/` instaladas.**
   `~/.venvs` está vacío y `python3 -c "import mlflow"` falla con
   `ModuleNotFoundError` en el intérprete de sistema. El stack de
   `modelado/requirements.txt` (`lightgbm`, `mlflow`, `torch`, `evidently`,
   `onnx*`…) pesa ~1 GiB instalado.
3. **Disco al límite (tarea 104, sin resolver del todo):** `df -h /` da
   **6,7 GiB totales, 5,7 GiB usados, 986 MiB libres (86 % de uso)** a
   29/8. Instalar un venv de ~1 GiB para ejecutar el cron no cabe hoy sin
   repetir el `OSError: Disk quota exceeded` que ya paró un `pip install`
   en la tarea 104 — y con un cron sería un fallo cada noche, no uno
   puntual.

## Decisión: no se instaló el cron real en esta tarea

El ticket pide explícitamente pedir **aprobación humana** antes de activar
un `cron.d` con credenciales AWS que corre a diario sin supervisión
("mismo criterio que un `terraform apply`"), y bloquear la activación si
el disco sigue al límite de la tarea 104 — las dos condiciones se dan a la
vez en esta sesión autónoma: no hay ningún humano al que pedir la
aprobación en tiempo real, y el disco (986 MiB libres) está por debajo del
margen que la propia tarea 104 recomendó (>20 % libre; hoy ~14 %) y por
debajo de lo que necesitaría instalar el venv. Además, esta misma EC2 aloja
el propio demonio del pipeline de tareas — un cron que falla cada noche por
falta de espacio (o que llena el disco en un `--rebuild-panel` real) puede
tumbar el pipeline que procesa el resto de tareas, no solo el reentreno.

En vez de forzarlo, se dejó todo listo para que la instalación real sea un
único comando una vez alguien libere disco y apruebe:

- **`infra/cron/madrono-retrain.cron`** — la plantilla del `cron.d`, con
  `<REPO>` en vez del inexistente `/opt/madrono`.
- **`infra/cron/instalar_cron.sh`** — instalador manual (no se autoejecuta
  desde ningún sitio): comprueba disco libre (aborta si hay menos de 3 GiB,
  configurable con `MIN_LIBRE_MB`) y que `<REPO>/.venv` tiene las
  dependencias importables, muestra la línea final y pide escribir `SI`
  antes de copiarla a `/etc/cron.d/` con `sudo`.
- **`infra/OPERACION.md`** actualizado: estado real ("diseñado y
  verificado, sin instalar"), los dos bloqueos encontrados, y los comandos
  exactos (crear venv → `pip install -r modelado/requirements.txt` →
  `instalar_cron.sh`) para cuando se decida activarlo.

No se ejecutó `retrain_nightly.py --rebuild-panel` de verdad en esta
sesión (más allá de la ejecución manual ya documentada en `doc/ML-10-...md`
del 29/8): habría requerido instalar ~1 GiB de dependencias sobre un disco
con 986 MiB libres, el mismo tipo de acción que este bloqueo intenta evitar.

## Memoria (`documents/Memoria_TFM FV.docx`)

**No se tocó.** El ticket pedía actualizar §5.5/§7.4 quitando la redacción
de "pendiente de desplegar" **una vez el mecanismo esté realmente en
marcha** — como no se activó el cron real, esa redacción sigue siendo la
correcta y no hay nada que corregir todavía.

## Pendiente / próximo paso real

1. Resolver disco (ampliar el EBS de 8 GiB, o mover el checkout de
   producción a un volumen con más margen — ver
   `doc/104-ec2-root-volume-al-limite.md`).
2. Decidir cuál de los dos checkouts (`~/repos/madronoTFM` o
   `~/repos/madronoTFM-agent`) es el que corre el cron en producción, o
   crear uno dedicado — hoy son dos clones manuales sin un rol claro de
   "el que despliega".
3. Con disco resuelto: `python3 -m venv <REPO>/.venv && <REPO>/.venv/bin/pip
   install -r <REPO>/modelado/requirements.txt`, luego
   `REPO=<REPO> infra/cron/instalar_cron.sh` (pide confirmación explícita).
4. Dejar pasar (o forzar una vez) una ejecución real del cron, confirmar en
   `/var/log/madrono-retrain.log` y en
   `modelado/evaluation/artifacts/nightly/historial.csv`, y **entonces sí**
   actualizar `documents/Memoria_TFM FV.docx` §5.5/§7.4 quitando "pendiente
   de desplegar".
