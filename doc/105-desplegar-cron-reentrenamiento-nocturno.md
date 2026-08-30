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

---

## Despliegue real (2026-08-30, sesión interactiva — aprobado)

Los tres bloqueos anteriores resueltos vía **SSM Run Command** contra la EC2
del demonio (`i-0aa45f0df26b4b7e6`, `eu-south-2`, SSM-gestionada, comandos
como `root`):

1. **Disco** — `aws ec2 modify-volume` `vol-045f46fb5c526a771` **8 → 24 GiB**
   + `growpart /dev/nvme0n1 1` + `resize2fs`. `/` pasó de 985 MiB libres
   (86 %) a ~15 GiB libres. Limpieza extra: revisiones `snap` deshabilitadas
   (ssm-agent 13009, core22 2411, snapd 27591), `apt-get clean`.
2. **venv** — `apt install python3.14-venv` (esta EC2 es Ubuntu con Python
   3.14 nativo), `python3 -m venv /home/ubuntu/repos/madronoTFM/.venv`,
   `pip install --only-binary :all:` de `modelado/requirements.txt`
   **sin `torch`** (verificado: `retrain_nightly.py` solo importa
   `pandas` + `datasets.splits`/`evaluation.metrics`/`models.{baselines,gbt}`;
   `torch` es exclusivo del STGNN/`train_stgnn.py`/`export/to_onnx.py`, que
   no entran en el reentreno nocturno). Descarga de `torch` fallaba además
   por red intermitente en la EC2 — otro motivo para dejarlo fuera.
3. **Credenciales** — no hay perfil `AWS_PROFILE=madrono` en la EC2; el rol
   de instancia `madrono-terraform-deployerEC2` llega a Athena de forma
   ambiente. La plantilla del cron se corrigió: `AWS_PROFILE=madrono` →
   `AWS_DEFAULT_REGION=eu-west-1` (la EC2 está en `eu-south-2`, los datos en
   `eu-west-1`).
4. **Memoria RAM** — la instancia tiene **3,7 GiB de RAM**. El primer
   reentreno completo murió por **OOM** al construir el panel de `trafico`
   (~1,6 M filas + join de meteo). Se añadió **4 GiB de swap**
   (`/swapfile`, persistente en `/etc/fstab`). Con swap el reentreno
   completo termina en **~6,5 min** (pico ~1,6 GiB de swap usados).

### Instalado

`/etc/cron.d/madrono-retrain` (644, `ubunto`):

```
30 3 * * *  ubuntu  cd /home/ubuntu/repos/madronoTFM && AWS_DEFAULT_REGION=eu-west-1 /home/ubuntu/repos/madronoTFM/.venv/bin/python -m modelado.training.retrain_nightly --rebuild-panel >> /var/log/madrono-retrain.log 2>&1
```

Checkout de producción: `/home/ubuntu/repos/madronoTFM` (clon manual,
independiente del `~/repos/madronoTFM-agent` que el demonio hace
`git reset --hard` cada ciclo). Todas las salidas del reentreno
(`modelado/mlflow.db`, `modelado/evaluation/artifacts/`, `modelado/_data/`)
están en `.gitignore`, así que un `git pull` futuro sobre ese checkout no
las pisa.

### Verificación (ejecución real forzada tras instalar)

`retrain_nightly --rebuild-panel` completo, exit 0:

- Paneles reconstruidos desde Athena con el rol de instancia:
  `calidad_aire` 43 243 filas / 30 features, `trafico` 1 635 505 filas / 30
  features (meteo + previsión AEMET + festivos — el cierre de `ML_01`
  corriendo en producción).
- 6 modelos entrenados y registrados en MLflow
  (`madrono-{calidad_aire,trafico}-h{1,3,6}` v1, backend SQLite
  `modelado/mlflow.db`).
- `historial.csv` con 6 filas nuevas; el *guardrail* de promoción funciona:
  `calidad_aire` h1 con `skill_nuevo` -0,0031 < vigente → `promovido=False`;
  el resto promovidos.

### Daemon reiniciado

`systemctl restart madrono-agent.service` (cola vacía en ese momento):
PID 719351 → 722608, `active (running)`, watchdog OK. Con esto el demonio
recoge el `merge_pr()` de la tarea 101 (espera a la CI en verde antes de
auto-fusionar un PR `force: true`).

### Pendiente

- `documents/Memoria_TFM FV.docx` §5.5/§7.4: **ahora sí** se puede quitar
  "pendiente de desplegar" — el cron está instalado y verificado (pista
  Memoria).
- Vigilar `/var/log/madrono-retrain.log` los primeros días; si el checkout
  de producción se queda atrás respecto a `main` en algo relevante para el
  reentreno, refrescarlo a mano (`git -C /home/ubuntu/repos/madronoTFM pull
  --ff-only`).
