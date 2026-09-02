# FIL_63 (M1) — landing + auth demo + `asistente/main.py` desplegado

Ejecutado 2026-09-02, contra la EC2 real (`i-0aa45f0df26b4b7e6`,
`eu-south-2`, IP `35.42.164.183`). Verificado en vivo, no solo en local.

## Qué se hizo

1. **`systemd`**: `/etc/systemd/system/madrono-web.service` —
   `uvicorn asistente.main:app --host 127.0.0.1 --port 8000`, usuario
   `ubuntu`, `Restart=always`, mismo patrón operativo que
   `madrono-agent.service`. `enabled` (sobrevive a un reboot).
2. **`nginx`** como proxy inverso (instalado vía `apt`, no estaba):
   - TLS autofirmado (`openssl req -x509`, 825 días) — no hay dominio
     propio apuntando a la IP, así que se optó por autofirmado en vez de
     Let's Encrypt (que necesita un dominio real para el reto ACME). El
     navegador avisará de certificado no confiable — aceptable para una
     demo de TFM, documentado aquí explícitamente.
   - **HTTP Basic Auth** (`demo`/`demo`, vía `htpasswd`) en el bloque
     `server`, cero código nuevo en `asistente/`.
   - Redirección 80→443.
   - `location = /` sirve el landing estático; todo lo demás se
     proxy-pasa a `uvicorn`.
3. **Security group** `sg-0b9b20f616f30216e`: abiertos 443 y 80 a
   `0.0.0.0/0` (antes solo tenía el 22). Aplicado a mano
   (`aws ec2 authorize-security-group-ingress`), no vía Terraform —
   coherente con que esta EC2 no está gestionada por Terraform.
4. **Landing** (`/var/www/madrono/index.html`): página estática simple,
   enlaza a `/docs` (Swagger autogenerado por FastAPI) y a `/health`.

## Dos bugs reales encontrados y arreglados en el camino

- **`NoRegionError` de boto3**: el `systemd` no heredaba
  `AWS_DEFAULT_REGION` — sin él, cualquier tool que llame a Athena (la
  mayoría) fallaba con `500`. Arreglado con
  `Environment=AWS_DEFAULT_REGION=eu-west-1` en la unidad. Mismo motivo
  ya documentado toda la sesión como nota de entorno de esta EC2 (región
  por defecto real de la instancia: `eu-south-2`).
- **`index` de nginx rompía el landing**: `location = / { root ...;
  index index.html; }` daba `404` con `Content-Type: application/json`
  — el `index` de nginx hace una redirección interna a `/index.html`,
  que **reentra en el matching de `location`** y caía en el
  `location /` genérico (proxy a FastAPI, que no tiene esa ruta y
  devuelve su propio 404 JSON). Arreglado con `try_files /index.html
  =404;`, que sirve el fichero directamente sin la redirección interna.

## Verificado en vivo contra la instancia pública (no localhost)

- `https://35.42.164.183/` sin credenciales → `401`.
- Con `demo:demo` → `200` (landing real).
- `/health` → `200`, cuerpo real.
- `/docs` → `200` (Swagger real).
- `http://35.42.164.183/` → `301` a `https://`.
- **Tools reales que no dependen de Neo4j, probadas con datos reales**:
  `/calidad-aire`, `/calidad-aire-prevista`, `/trafico-prevista` — las
  tres responden `200` con JSON real y coherente (no mockeado).

## Limitación conocida, no un bug de este ticket: Neo4j sin credenciales

Las tools que necesitan el grafo (`trafico_cercano`,
`opciones_movilidad`, `disponibilidad_aparcamiento`, `eventos_cercanos`,
la resolución de "lugar" en `ruta_saludable`/`trafico_prevista`) fallan
con `KeyError: 'NEO4J_URI'` porque el `systemd` no tiene esas 4
variables — **mismo límite ya documentado durante toda esta sesión**:
esta sesión de Claude nunca ha tenido acceso a las credenciales reales de
Neo4j (`aws ssm get-parameter --with-decryption` sobre
`/madrono-tfm/dev/secrets/neo4j-*` bloqueado, ver `doc/VIKT-06-...md`).
No se ha intentado sortear. Interesante de paso: algunas tools degradan
con elegancia ante este fallo (`trafico_prevista` devuelve una respuesta
estructurada explicando el motivo), otras no (`trafico_cercano` da un
`500` crudo) — inconsistencia menor, no arreglada aquí (fuera del
alcance de este ticket de despliegue).

**Para que estas tools funcionen en producción**: añadir
`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE` al
`systemd` (idealmente leídos de SSM en el arranque, no como
`Environment=` en claro, mismo patrón que `secretos.py`) — quien tenga
acceso a esas credenciales.

## Qué queda para `M2` (aparte, no en este ticket)

- La capa de chat en lenguaje natural sobre Groq (`FIL_62`).
- Resolver el acceso a Neo4j si se quiere que las tools de grafo
  funcionen en la demo pública.
- Certificado real (Let's Encrypt) si se decide poner un dominio.

## Acceso

`https://35.42.164.183/` — usuario `demo`, contraseña `demo`. Certificado
autofirmado (aviso de navegador esperado).
