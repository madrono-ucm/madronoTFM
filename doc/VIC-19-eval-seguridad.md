# VIC-19 — Evaluación técnica ronda 2: auditoría de seguridad dedicada

Ejecutado 30/8. Auditoría defensiva sobre un proyecto propio con acceso ya
autorizado. Ningún cambio de código; ninguna credencial fue usada para
autenticar contra un servicio externo.

## 🔴 Hallazgo crítico — ver `FIL_28`

`ingesta/tests/test_bluesky_menciones_madrid.py` tiene, en el working
tree actual, `identifier="madrono97.bsky.social"` +
`app_password="pc6y-6s6c-6dar-jgit"` — un identificador que parece la
cuenta real del proyecto y una contraseña con el formato exacto de un
Bluesky App Password real. **El repositorio es público** (verificado con
`gh api repos/madrono-ucm/madronoTFM` → `"private": false`). No se ha
intentado autenticar con esta credencial. Detalle completo, contexto del
commit que la introdujo, y recomendación de rotación inmediata en
[`FIL_28`](../tasks/FIL_28_CRITICO-posible-credencial-bluesky-en-repo-publico.md) —
**reportado de inmediato en el chat al encontrarlo, no se esperó al
resumen final de este ticket.**

## Resto de la auditoría — sin hallazgos

- **Buckets S3** (`bronze`, `silver`, `gold`, `athena-results`): los 4
  con `PublicAccessBlockConfiguration` completo (`BlockPublicAcls`,
  `IgnorePublicAcls`, `BlockPublicPolicy`, `RestrictPublicBuckets`, los
  4 en `true`) — privados, correcto.
- **IAM de mínimo privilegio**: sin `Resource: "*"` en ninguna política
  del árbol Terraform completo (verificado en `VIC_18`, no se repite el
  grep aquí). Política de `FIL_17` (secretos SSM) acotada a los ARNs
  concretos de `local.secrets`, sin comodines.
- **`EMT_API_PASSWORD="tu-contraseña"`** (el otro resultado del grep de
  patrones de credenciales): confirmado que es un placeholder de plantilla
  genuino, junto a `EMT_API_EMAIL="tu-email@ejemplo.com"` en la misma
  línea de documentación — no es una credencial real.
- **Superficie del servidor MCP sin auth/rate-limiting**: confirmado que
  está honestamente documentado (`README.md` raíz, lista explícita de "no
  construido" — `auth/rate-limiting del MCP`), no simplemente omitido.

## Conclusión

Un hallazgo crítico real (`FIL_28`, reportado de inmediato). El resto de
la superficie revisada (buckets, IAM, documentación de la superficie sin
auth) está en buen estado.
