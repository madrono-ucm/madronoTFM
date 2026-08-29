---
id: 105
slug: desplegar-cron-reentrenamiento-nocturno
title: 'QA: el reentrenamiento nocturno de ML_10 está diseñado y verificado a mano,
  pero el cron real nunca se instaló'
status: done
force: false
allow_infra_apply: false
branch: task/105-desplegar-cron-reentrenamiento-nocturno
pr_number: 174
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/174
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-29T19:35:00+00:00'
updated_at: '2026-08-29T21:43:09.239782+00:00'
started_at: '2026-08-29T19:22:19.740362+00:00'
submitted_at: '2026-08-29T19:26:56.228677+00:00'
merged_at: '2026-08-29T21:43:06Z'
---

## Hallazgo de QA (verificado en vivo)

`doc/ML-10-reentrenamiento-nocturno-backtest.md` documenta el mecanismo
de reentrenamiento nocturno y da la línea exacta de `cron` a instalar,
pero su propia sección "Notas" ya admite: *"la verificación es de una
ejecución manual; instalar el `cron.d` en la EC2 es el paso de
despliegue"*. Comprobado hoy en esta misma EC2 (la del demonio
`madrono-agent`, donde `infra/OPERACION.md` dice que debe vivir):

```
ls /etc/cron.d/          # solo el .placeholder y e2scrub_all de Debian
crontab -l -u ubuntu     # "no crontab for ubuntu"
```

**El cron nunca se instaló.** El script (`modelado/training/
retrain_nightly.py`) funciona y se verificó ejecutándolo a mano el 29/8,
pero no hay ninguna programación periódica real corriendo en producción.

Esto es relevante porque, al escribir la memoria (`VIKT_02`), la
redacción original de §5.4/§5.5 lo describía como un mecanismo ya
programado en producción — se ha corregido para decir "diseñado y
verificado, programación pendiente de desplegar" en vez de darlo por
hecho, y se ha añadido una nota explícita en §7.4. Este ticket es para
cerrar la brecha real, no solo la de redacción.

## Objetivo

Instalar de verdad la programación periódica del reentrenamiento
nocturno en la EC2 del demonio.

## Alcance concreto

1. Crear `/etc/cron.d/madrono-retrain` con el contenido ya documentado en
   `doc/ML-10-...md` e `infra/OPERACION.md`:
   ```cron
   30 3 * * *  ubuntu  cd /opt/madrono && AWS_PROFILE=madrono /opt/madrono/.venv/bin/python -m modelado.training.retrain_nightly --rebuild-panel >> /var/log/madrono-retrain.log 2>&1
   ```
   **Verifica primero** que las rutas (`/opt/madrono`, el venv) coinciden
   con el despliegue real de esta EC2 — si el repo/entorno vive en otra
   ruta (p. ej. `/home/ubuntu/repos/madronoTFM`), ajusta el comando en
   consecuencia; no copies la ruta del `doc/` sin comprobarla.
2. Confirma que `AWS_PROFILE=madrono` (o el mecanismo de credenciales que
   corresponda en esta instancia — puede que sea el rol de instancia
   IAM, sin perfil nombrado) es correcto para que el job tenga acceso
   real a Athena al reconstruir el panel.
3. Verifica el disco disponible antes de activarlo (ver ticket `104`) —
   un job que falla noche tras noche por falta de espacio es peor que no
   tenerlo.
4. Deja pasar al menos una ejecución real (o fuérzala una vez de forma
   controlada) y confirma en `/var/log/madrono-retrain.log` y en
   `modelado/evaluation/artifacts/nightly/historial.csv` que corrió sin
   errores.
5. Actualiza `documents/Memoria_TFM FV.docx` (§5.5, §7.4) quitando la
   redacción de "pendiente de desplegar" una vez esté realmente en
   marcha — coordina el turno del `.docx` (ver `PLAN.md`).

## Restricciones

- Instalar un `cron.d` que ejecuta código real con credenciales AWS de
  forma recurrente y no supervisada es una acción de infraestructura con
  efectos continuos — **pide aprobación explícita del usuario antes de
  activarlo**, mismo criterio que un `terraform apply`.
- No lo actives si el disco sigue al límite (ticket `104`) sin resolver
  primero ese riesgo.

## Criterios de aceptación

- `/etc/cron.d/madrono-retrain` instalado y verificado con una ejecución
  real (no solo manual, vía el propio cron).
- `doc/105-...md` documenta el despliegue y el resultado de la primera
  ejecución programada.
- Memoria actualizada para reflejar que el mecanismo ya está en marcha,
  no solo diseñado.
