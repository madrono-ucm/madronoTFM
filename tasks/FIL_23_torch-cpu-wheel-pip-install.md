---
kind: fil
title: "modelado/requirements.txt: pip install torch>=2.2,<3 sin índice CPU resuelve al build CUDA (~4.5GB, no importa sin GPU)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
---

## Resolución (2026-08-30)

`modelado/requirements.txt`: añadido
`--extra-index-url https://download.pytorch.org/whl/cpu` al principio + reescrito
el comentario de `torch`. El índice de PyTorch publica `torch==X.Y.Z+cpu`;
por PEP 440 el segmento local `+cpu` ordena por encima de `X.Y.Z`, así que
`pip install -r` a secas ya trae el build CPU (~760 MB, sin
`nvidia-*`/`triton`). `modelado/README.md`: nueva sección "torch es SOLO CPU"
con el arranque en dos pasos para pips antiguos y la comprobación
(`torch.cuda.is_available() == False`). CI hereda el `--extra-index-url` sin
cambios en el workflow. `doc/FIL-23-...md`.

> **Contexto**: encontrado en `VIKT_08` (auditoría de reproducibilidad,
> `doc/PLAN-REVISION-TFM.md`), haciendo un `git clone` limpio + `venv` nuevo
> y siguiendo literalmente `modelado/README.md`/`requirements.txt`.

## Qué está roto (verificado en vivo)

`modelado/requirements.txt` fija `torch>=2.2,<3` con este comentario:

> "Tier 2 (ML_05): GNN espacio-temporal. Solo `torch` (CPU) — la capa
> GraphSAGE está implementada a mano..."

La intención es CPU-only, pero un `pip install -r modelado/requirements.txt`
literal, en un clon limpio, **no** obtiene el build CPU: PyPI resuelve
`torch` al build por defecto con soporte CUDA, que arrastra `nvidia-*`
(cuBLAS, cuDNN, cuFFT, etc.) + `triton` — **~4.5 GB** solo de esas dos
carpetas (`site-packages/nvidia/` 2.7G + `site-packages/torch/` 1.1G +
`site-packages/triton/` 691M, medido en vivo).

Dos problemas reales, no cosméticos:

1. **Coste de disco real.** En un EC2 sin GPU (como esta, o cualquier CI
   runner estándar) esos ~4.5 GB son puro desperdicio — nunca se van a
   poder usar (no hay GPU). En esta misma auditoría, un primer intento de
   instalar en `/tmp` (tmpfs, 1.9G) agotó la cuota; reintentado en disco
   real, agotó igualmente el disco compartido de la EC2 (`/dev/root`, de
   9.4G libres a 0) a mitad de instalación.
2. **Ni siquiera funciona.** Si se libera espacio borrando `nvidia`/`triton`
   a mano (sin reinstalar), `import torch` falla en runtime:
   ```
   OSError: libcudart.so.13: cannot open shared object file: No such file or directory
   ...
   ValueError: libcublasLt.so.*[0-9] not found in the system path [...]
   ```
   porque el build CUDA de `torch` espera esas librerías del sistema
   (`libcudart`, `libcublasLt`) que no existen sin GPU/toolkit CUDA
   instalado.

**Fix real, verificado en el clon limpio de esta auditoría:**

```bash
pip uninstall -y torch
pip install --index-url https://download.pytorch.org/whl/cpu torch
```

Tras esto: `torch.__version__` → `2.13.0+cpu`, `torch.cuda.is_available()`
→ `False` (correcto, es justo lo que se quiere), tamaño de `site-packages/torch/`
→ 757M (sin `nvidia`/`triton`), y **todo el resto de la auditoría
(`train_gbt`, `run_all.py`, `backtest.py`, `to_onnx.py`) corrió sin ningún
otro problema** contra este build.

## Por qué importa

- Cualquiera que siga `modelado/README.md` literalmente desde cero (un
  compañero nuevo, un revisor de la memoria, un runner de CI sin caché)
  puede quedarse sin disco a mitad de instalación, sin que el mensaje de
  error apunte a `torch`/CUDA como causa.
- La CI actual (`.github/workflows/ci.yml`) puede estar funcionando hoy por
  suerte (runner con más disco, o con `pip` cacheado de una corrida
  anterior que ya tenía el CPU-wheel) — no se ha verificado en este ticket
  si la CI ya sufre esto o no; merece una comprobación aparte.

## Qué hacer (propuesto, no aplicado aquí)

En `modelado/requirements.txt`, cambiar el comentario de `torch` para dejar
explícito el índice CPU, por ejemplo:

```
# Tier 2 (ML_05): GNN espacio-temporal — SOLO CPU. `pip install -r` a secas
# resuelve al build CUDA por defecto de PyPI (~4.5 GB de nvidia-*/triton
# que no sirven sin GPU y que además no cargan en runtime sin el toolkit
# CUDA instalado). Instalar así en vez de `pip install -r` directo:
#   pip install --index-url https://download.pytorch.org/whl/cpu torch
# y LUEGO el resto de requirements.txt (o usar --extra-index-url con el
# índice de PyPI normal primero, CPU después, según orden de resolución).
torch>=2.2,<3
```

y añadir la misma nota a `modelado/README.md` (sección de instalación) y
a cualquier guía de arranque nueva (`FIL_19`, README raíz). Verificar
también si `.github/workflows/ci.yml` ya usa el índice CPU o si le afecta
el mismo problema.

## Restricciones

- No se ha tocado `requirements.txt`/`README.md`/CI en este ticket — el fix
  de arriba se verificó contra un `venv` de auditoría desechable
  (`/home/ubuntu/vikt08-work/`, ya limpiado), no contra el repo.

## Criterios de aceptación

- `requirements.txt`/`README.md` documentan explícitamente el índice CPU.
- Verificado con un `pip install -r modelado/requirements.txt` literal
  (tal cual quede documentado) en un clon limpio: no se instala
  `nvidia-*`/`triton`, `import torch` funciona, y `pytest modelado/` sigue
  en verde.
- Comprobado si la CI actual ya tiene o no este problema.
