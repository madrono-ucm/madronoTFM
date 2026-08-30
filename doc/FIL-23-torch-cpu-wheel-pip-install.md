# FIL-23 — `torch` CPU-only en `modelado/requirements.txt`

Hallazgo de `VIKT_08` (auditoría de reproducibilidad, clon limpio + venv
nuevo siguiendo `modelado/README.md` al pie de la letra).

## El problema

`modelado/requirements.txt` fijaba `torch>=2.2,<3` con la intención "solo
CPU", pero un `pip install -r` literal resuelve `torch` al **build CUDA por
defecto de PyPI**: arrastra `nvidia-*` (cuBLAS, cuDNN, cuFFT…) + `triton`,
**~4.5 GB** que:

1. No sirven de nada sin GPU (EC2 del proyecto, runners de CI estándar).
   En la auditoría agotó el disco a mitad de instalación, sin que el error
   señalara a `torch`/CUDA.
2. Ni siquiera cargan: si se borran `nvidia`/`triton` a mano, `import torch`
   peta con `OSError: libcudart.so.13: cannot open shared object file` /
   `libcublasLt.so not found` — el build CUDA espera librerías del sistema
   que no existen sin el toolkit CUDA.

## El arreglo

`modelado/requirements.txt` lleva ahora, al principio:

```
--extra-index-url https://download.pytorch.org/whl/cpu
```

El índice de PyTorch publica el wheel como `torch==X.Y.Z+cpu`. Por PEP 440
el segmento local `+cpu` ordena **por encima** de `X.Y.Z` a igualdad de
versión base, así que pip prefiere el `+cpu` frente al de PyPI — un
`pip install -r modelado/requirements.txt` normal ya trae el build CPU
(~760 MB, `torch.cuda.is_available() == False`, sin `nvidia-*`/`triton`).

Para pips antiguos que aun así elijan el de PyPI, `modelado/README.md`
documenta el arranque en dos pasos:

```bash
pip install --index-url https://download.pytorch.org/whl/cpu 'torch>=2.2,<3'
pip install -r modelado/requirements.txt
```

## CI

`.github/workflows/ci.yml` instala `modelado/requirements.txt` tal cual, así
que hereda el `--extra-index-url` sin cambios en el workflow. Antes podía
estar pasando "por suerte" (caché de pip de una corrida previa con el wheel
CPU, o runner con disco de sobra); ahora el índice CPU es explícito y
determinista. El `--extra-index-url` no afecta al resto de dependencias: el
índice de PyTorch solo sirve la familia `torch`, para todo lo demás pip cae
a PyPI.

## Verificación

- `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
  → `...+cpu False`; `site-packages/` sin `nvidia/`/`triton/`.
- `pytest modelado/` en verde (el resto de la auditoría de `VIKT_08` —
  `train_gbt`, `run_all.py`, `backtest.py`, `to_onnx.py` — ya corrió contra
  este build CPU sin más cambios).
