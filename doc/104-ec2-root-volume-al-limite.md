# 104 — QA: volumen raíz de la EC2 del demonio al 95%

## Hallazgo de partida

`df -h /` al empezar: **6,7G totales, 6,3G usados, 375M libres (95%)** — ya
había causado un `OSError: [Errno 122] Disk quota exceeded` real durante un
`pip install` de `modelado/` en una sesión anterior.

## Causa real (no es solo "el stack de ML pesa mucho")

Auditoría con `du -xsh` por subárbol de `/` llevó a un único directorio
responsable del **11% de todo el disco**:

```
692M  /home/ubuntu/repos/madronoTFM/infra/terraform/.terraform/providers
```

`~/repos/madronoTFM` (sin `-agent`) es un **segundo clon completo** del
mismo repo remoto (`madrono-ucm/madronoTFM.git`), en `main`, limpio y al
día — aparentemente un clon manual anterior o paralelo al que usa el
pipeline de agentes (`~/repos/madronoTFM-agent`, donde vive este worktree).
Ese clon tenía su propia caché de providers de Terraform descargada
(`hashicorp/aws` 5.100.0) y nunca limpiada tras el `terraform init` de
alguna tarea anterior. El stack de ML (`torch`/`lightgbm`/`pandas`/`scipy`/…
en `~/.local/lib/python3.14/site-packages`, 934M) es real y pesado, pero no
es la causa de haber tocado techo — es la caché de Terraform huérfana.

`/tmp` en esta instancia es **tmpfs** (RAM, montaje aparte de `/`,
`mount | grep tmp` → `tmpfs on /tmp`) — limpiar `/tmp` (como sugería el
ticket) **no libera nada del disco raíz**; se hizo de todos modos por
higiene (borrados ~70M de logs/`tfplan`/scratch de tareas ya mergeadas —
065, 075, 076, 088 — confirmadas `done` en `git log`), pero no cuenta para
el objetivo de esta tarea.

## Mitigación aplicada (sin coste, sin `sudo`, reversible)

```bash
rm -rf ~/repos/madronoTFM/infra/terraform/.terraform
```

Seguro: `.terraform/` nunca se versiona, `.terraform.lock.hcl` sí sigue
commiteado en ese clon (las versiones de provider quedan fijadas), y el
directorio se regenera solo con `terraform init` si algún día se vuelve a
usar ese clon en concreto.

**Resultado:** `df -h /` pasó de **375M libres (95%)** a **1,1G libres
(85%, ~16% libre)** — un único `rm -rf` recuperó 692M.

Para que la misma caché no se vuelva a duplicar (esta EC2 tiene al menos
dos clones del repo, y el pipeline de agentes puede añadir más
worktrees/checkouts con el tiempo), se documentó en `infra/OPERACION.md`
apuntar todos los `terraform init` de esta máquina a una caché de
providers compartida (`plugin_cache_dir` en `~/.terraformrc`) en vez de una
copia por clon.

## No aplicado en esta tarea (con el motivo)

- **Redimensionar el volumen EBS raíz** (8 → 20-30 GiB): es la vía para un
  margen holgado y duradero, pero es un cambio de infraestructura real con
  coste (~0,08 USD/GB-mes) — el propio ticket pide aprobación explícita
  antes de tocarlo, y esta sesión corre en un pipeline sin supervisión
  humana en tiempo real. Comandos exactos, ya verificados (volumen real
  localizado), dejados en `infra/OPERACION.md` a la espera de esa
  aprobación. Dato importante descubierto al prepararlos: **esta EC2 vive
  en `eu-south-2`**, no en `eu-west-1` como el resto de la infraestructura
  del proyecto (confirmado vía metadata de instancia y
  `aws ec2 describe-volumes`: instancia `i-0aa45f0df26b4b7e6`, volumen
  `vol-045f46fb5c526a771`, 8 GiB `gp3`) — cualquier comando `aws` sobre este
  volumen necesita `--region eu-south-2` explícito, no el `eu-west-1` que
  usa el resto del runbook.
- **`sudo apt-get clean` / `journalctl --vacuum` / limpiar revisiones
  `snap` antiguas** (~138M + ~65M + revisiones `disabled` de
  `amazon-ssm-agent`/`core22`): identificadas y cuantificadas, pero esta
  sesión de Claude Code corre sin privilegios de root (`sudo` bloqueado por
  el flag "no new privileges" del sandbox) — no ejecutable desde aquí.
  Comandos exactos dejados en `infra/OPERACION.md` para quien tenga acceso
  directo (con `sudo`) a la instancia.
- El volumen **no está gestionado por Terraform** (el único `aws_instance`
  en `infra/terraform/` es el broker Kafka de la tarea 042; esta EC2 se
  aprovisionó a mano fuera de este repo — mismo patrón que los recursos de
  bootstrap de `doc/014`), así que no había ningún `.tf` que tocar para el
  redimensionado.

## Estado final

```
$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/root       6.7G  5.6G  1.1G  85% /
```

Por debajo del 20% recomendado por el ticket, pero un salto real desde el
95% de partida y sin ningún riesgo ni coste. El resto del margen (apt/snap/
journal con `sudo`, y sobre todo el redimensionado de EBS) queda
documentado y listo para aplicarse en cuanto haya acceso con privilegios o
aprobación humana — ver `infra/OPERACION.md` § "Espacio en disco de la EC2
del demonio".

## Pendiente / lo retoman otras tareas

- Aplicar el redimensionado de EBS (requiere aprobación humana + acceso con
  `sudo` para `growpart`/`resize2fs`).
- Ejecutar la limpieza de `apt`/`journalctl`/`snap` con `sudo` (~250-350M
  adicionales, sin coste).
- Configurar `plugin_cache_dir` de Terraform en esta máquina para que no
  vuelva a acumularse una copia de providers por clon/worktree.
- Si se decide no ampliar el EBS, vigilar el crecimiento de
  `~/.local/lib/python3.14/site-packages` (934M) según se añadan
  dependencias nuevas a `modelado/requirements.txt` — es ya, con diferencia,
  el mayor consumidor de espacio de usuario tras esta limpieza.
