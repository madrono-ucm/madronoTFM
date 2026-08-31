# VIC_27 — CVEs de dependencias con pip-audit (ronda 4)

**Fecha:** 2026-08-30. `pip-audit` no estaba instalado ni configurado en el
repo — primera vez que corre. Instalado solo en el `.venv` local de esta
EC2 para la auditoría, contra el entorno real combinado (`ingesta` +
`modelado` + `asistente`, base de datos real de OSV/PyPI).

## Comando

```
pip-audit --format markdown
```

## Resultado

**3 CVEs reales** en 2 paquetes, ambos transitivos (ninguno pineado en
`ingesta/requirements.txt`, `modelado/requirements.txt` ni
`asistente/requirements.txt` propios):

| Paquete | Instalada | CVE | Fix | Traído por |
|---|---|---|---|---|
| `cryptography` | 49.0.0 | `CVE-2026-69247` | 50.0.0+ | `evidently`, `google-auth`, `mlflow` |
| `setuptools` | 78.1.0 | `CVE-2025-47273` | 78.1.1+ | `torch` |
| `setuptools` | 78.1.0 | `CVE-2026-59890` | 83.0.0+ | `torch` |

`torch` (2.13.0+cpu) no se pudo auditar — build `+cpu` no indexado en el
PyPI estándar que consulta `pip-audit`; limitación conocida de la
herramienta, no un hueco de cobertura de esta auditoría.

## Impacto real de cada CVE (no solo la descripción de la base de datos)

- **`CVE-2026-69247`** (oráculo de Bleichenbacher en descifrado PKCS7/
  S-MIME de `cryptography`): verificado con `grep -rn "pkcs7\|smime"`
  sobre todo `ingesta/ modelado/ asistente/ grafo/ herramientas/` —
  **cero referencias** en código propio. `cryptography` llega solo como
  transitiva de `mlflow`/`google-auth`/`evidently`, usada para primitivas
  TLS/JWT internas, nunca para las funciones PKCS7 afectadas. Impacto
  real: nulo.
- **`CVE-2025-47273`** (path traversal → escritura arbitraria en
  `setuptools.PackageIndex.download`, CVSS 8.8): la API afectada es la
  instalación de paquetes estilo `easy_install`, nunca invocada desde
  código propio (el pipeline de instalación de este proyecto es
  `pip install -r requirements.txt` contra PyPI oficial). Impacto real:
  nulo en la ruta de ejecución de producción.
- **`CVE-2026-59890`** (bypass de exclusión `MANIFEST.in` por
  normalización Unicode al construir un sdist en macOS APFS/HFS+): este
  proyecto no publica ningún paquete propio en PyPI. No aplica en
  absoluto al caso de uso de este repo.

## Conclusión

Los 3 CVEs son reales según OSV/PyPI, pero ninguno tiene ruta de
explotación real en este proyecto dado cómo se usan estos paquetes aquí
(transitivos, APIs vulnerables nunca invocadas desde código propio). Se
recomienda igual el bump por ser de coste ~0 (ninguno pineado, parches
menores) → **`FIL_39`** (renumerado desde `FIL_32` el 30/8 por colisión
con una rama sin mergear, ver `doc/PLAN-EVALUACION-TECNICA-4.md`), con
las versiones exactas de destino (`cryptography>=50.0.1`,
`setuptools>=83.0.0`) y sin recomendar un `pip install -U` genérico,
siguiendo la lección de `FIL_23` sobre verificar la suite completa tras
cualquier bump de versión antes de darlo por bueno.

Cierra ronda 4 (`VIC_25`-`27`, 3/3 completados): 2 `FIL_*` nuevos
(`FIL_41` XML sin `defusedxml` -- renumerado desde `FIL_31`, ver
`doc/PLAN-EVALUACION-TECNICA-4.md` -- `FIL_39` CVEs de dependencias
transitivas), ambos severidad baja con impacto real acotado, ningún bug
funcional encontrado.
