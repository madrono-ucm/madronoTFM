# FIL-38 — Backtest del STGNN sobre el Madrid Traffic Dataset (MTD)

`FIL_33`/G3 dejó claro que la ventana de datos del proyecto son ~16 días de
agosto 2026. Este ticket entrena el STGNN del proyecto
(`modelado/models/stgnn.py`) sobre un dataset abierto de **~29 meses** para
una tabla de resultados §7 más creíble.

**Results-only**: no toca los ONNX vendorizados (`asistente/modelos/`) ni las
tools. El modelo de aquí es un artefacto de evaluación.

## Dataset

*Enriched Traffic Datasets for Madrid* (MTD) v4 — Iván Gómez, Sergio Ilarri
(Univ. de Zaragoza). **CC BY 4.0**, DOI `10.17632/697ht4f65b.4`.

Se usa el **subconjunto de 300 sensores** (`subset_dataset_b8e4b3b3…`),
periodo **2022-06 .. 2024-10**. En vez del CSV crudo (`MTD_training.csv`,
**10 GB**) se consumen los tensores ya preparados que el propio dataset
publica:

| Fichero (`modelado/_data/mtd/`, `modelado/_data/` está en `.gitignore`) | Qué |
|---|---|
| `his_MTD_training_seq_len12_horizon12.npz` | `data` `[11687, 300, 3]` (feat0 = intensidad estandarizada; feat1/2 = hora y día de semana normalizados) + `mean`/`std` globales |
| `idx_{train,val,test}_MTD_training_seq_len12_horizon12.npy` | corte temporal 60/20/20 sobre los 11.687 pasos |
| `MTD_adj_matrix.npy` (553×553) + `ids_MTD_training_…txt` (300) | adyacencia del grafo, filtrada a los 300 |
| `MTD_id_longitude_latitude.csv` | coordenadas |
| `configuration.txt`, `variables.csv`, `CITATION.cff` | metadatos |

### Descarga puntual

```bash
# los ids de fichero salen de:
#   https://data.mendeley.com/public-api/datasets/697ht4f65b?fields=files
mkdir -p modelado/_data/mtd
# subset_dataset_b8e4b3b3…: his_MTD_training…npz, idx_*_MTD_training…npy,
#   ids_MTD_training…txt (300), MTD_adj_matrix.npy, MTD_id_longitude_latitude.csv
```

## Adaptador + entrenamiento

`modelado/training/backtest_stgnn_mtd.py`:

1. `_cargar_mtd()` — lee el `.npz`, filtra el adj 553→300 por `ids`.
2. `_edges_desde_adj()` — `adj > 1e-4` sin diagonal → `edge_index`/`edge_weight`.
3. `_ventanas()` — de índices-ancla `t` a `(Xseq [S,12,300,3], Y [S,300,3],
   persistencia [S,300,3])`; `Y[.,.,h]` = intensidad en `t+h` para
   `h ∈ {1,3,6}`; persistencia = intensidad en `t`. Submuestreo `--stride`
   en train/val (CPU).
4. `STGNN(in_dim=3, n_horizontes=3)` — misma arquitectura que el proyecto.
   Adam, early stopping por MSE de validación.
5. Test: destandardiza (`·std + mean` → veh/intervalo), MAE / RMSE / MAPE +
   **skill vs persistencia** por horizonte.

Salida: `modelado/evaluation/artifacts/backtest_mtd.{csv,json}`.

```bash
python -m modelado.training.backtest_stgnn_mtd --epocas 25 --stride 3
```

## Resultados

`python -m modelado.training.backtest_stgnn_mtd --epocas 3 --stride 10 --test-stride 8`
(CPU, ~5 min; 292 ventanas de test, 87.600 pares nodo·ventana por horizonte):

| h | modelo | MAE | RMSE | skill vs persistencia |
|---|---|---|---|---|
| 1 | **STGNN** | 134,7 | 227,6 | **+0,37** |
| 1 | persistencia | 166,6 | 287,1 | 0 (ref) |
| 3 | **STGNN** | 160,2 | 240,2 | **+0,70** |
| 3 | persistencia | 288,7 | 437,8 | 0 (ref) |
| 6 | **STGNN** | 121,3 | 181,5 | **+0,85** |
| 6 | persistencia | 332,4 | 462,8 | 0 (ref) |

(MAE/RMSE en veh/intervalo.) **El STGNN bate a la persistencia en los tres
horizontes**, y el margen **crece con el horizonte** (la persistencia se
degrada rápido; el modelo de grafo aguanta). Confirma, sobre una ventana
larga y un dataset abierto independiente, lo que el `tier2_trafico` del
proyecto ya mostraba en corto.

`modelado/evaluation/artifacts/backtest_mtd.{csv,json}`.

## Honestidad

- El objetivo de MTD es *intensidad de tráfico* (veh/intervalo), no el
  `avg_service_level` (0..6) del proyecto — son escalas distintas, así que
  esta tabla **no es comparable número a número** con `tier1/tier2_trafico`;
  vale como evidencia independiente de que la arquitectura de grafo
  **bate a la persistencia** a varios horizontes sobre una ventana larga.
- Sólo el subconjunto de 300 sensores y los tensores ya windowed del
  dataset; no se re-deriva el panel desde el CSV de 10 GB.
- **Entrenamiento corto** (3 épocas, ventanas submuestreadas 1/10) por coste
  de CPU — el bucle es por-muestra en Python. `val_mse` seguía bajando
  (0,20 → 0,15 → 0,14), así que las cifras son un **suelo**, no el máximo
  del modelo. Coherente con el §7.4 del proyecto ("ventana/entreno cortos").
- La meteo histórica de la Comunidad de Madrid (`FIL_38` la citaba) **no
  hace falta** por esta vía: MTD ya trae `wind`/`temperature`/`precipitation`
  alineados. Sólo sería necesaria si se reconstruyera el panel desde crudo.
