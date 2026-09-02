---
kind: fil
title: "App web de Madroño — M1: landing + auth demo + desplegar asistente/main.py en la EC2 (sin chat todavía)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
depends_on: [FIL_62]
milestone: "M1"
---

## Qué es

Primer milestone de `FIL_62` (encuadre ya cerrado: Groq para el chat,
EC2 existente para el despliegue). **Este ticket deliberadamente no
incluye el chat** — valida primero que `asistente/main.py` (ya
construido, 14 tools, probado localmente, nunca desplegado) sirve de
verdad en público, con un landing y autenticación de demo delante. El
chat es `M2`, un ticket aparte, después de que esto cierre.

## Estado real de la EC2 de destino (verificado en `FIL_62`, no repetir la verificación)

- `i-0aa45f0df26b4b7e6`, `t3.medium`, región **`eu-south-2`**.
- IP pública `35.42.164.183`, sin dominio propio hoy.
- Security group `sg-0b9b20f616f30216e` (`launch-wizard-1`, no gestionado
  por Terraform): solo el puerto 22 abierto a `0.0.0.0/0`.

## Alcance

1. **Servicio `systemd` para `asistente/main.py`**: `uvicorn
   asistente.main:app` como unidad `systemd` (arranque automático,
   reinicio si cae — mismo criterio operativo que `madrono-agent.service`
   ya usado para el daemon de tareas).
2. **`nginx` (o Caddy) como proxy inverso** delante de `uvicorn`:
   - TLS: con dominio propio apuntando a `35.42.164.183`, Let's Encrypt
     vía Certbot; sin dominio, certificado autofirmado (aviso de
     navegador aceptable para una demo de TFM, dejarlo explícito en el
     ticket de cierre qué opción se tomó).
   - **HTTP Basic Auth** (`demo`/`demo`) configurado en el propio
     `nginx`, no en la app — cero código nuevo en `asistente/`. Dejar
     explícito en la landing y en la memoria que **no es seguridad
     real** (credencial fija, sin límite de intentos): aceptable porque
     los datos servidos son 100 % abiertos, sin PII; el objetivo es solo
     mantener el enlace fuera de buscadores/bots, no proteger nada
     sensible.
3. **Security group**: abrir 443 (y 80 si hace falta para el reto ACME de
   Certbot) a `0.0.0.0/0` en `sg-0b9b20f616f30216e`. Aplicado a mano
   (`aws ec2 authorize-security-group-ingress`), no vía Terraform — esta
   EC2 y su SG no están importados en el estado de Terraform del
   proyecto, y forzar un recurso nuevo por encima de uno ya existente sin
   importar generaría un conflicto/drift, no una gestión real.
4. **Landing sencillo**: una página estática servida por `nginx` (o por
   la propia FastAPI con una ruta `/`) con el nombre del proyecto y un
   enlace/redirección a la documentación de la API (`/docs`, autogenerada
   por FastAPI) — sin chat todavía, ver `M2`.
5. **CORS**: no debería hacer falta en este milestone si el landing se
   sirve desde el mismo origen que la API; revisar si `M2` cambia esto.
6. **Verificación real** (mismo rigor que el resto de `VIC_*` de esta
   sesión): `curl -I https://<ip-o-dominio>/` sin credenciales → `401`;
   con `demo:demo` → `200`; `GET /health` → `200` con el cuerpo esperado;
   al menos 2 de las 14 tools probadas de verdad contra la instancia
   pública (p. ej. `GET /calidad-aire?zona=Sol`), no solo en local.

## Qué NO hace este ticket

- No añade el chat (`M2`).
- No mete a esta EC2 ni a su security group en el estado de Terraform
  del proyecto — sigue gestionada a mano, coherente con cómo ya se
  gestiona hoy.
- No toca `pipeline_enabled` ni ningún recurso de ingesta/procesamiento.

## Restricciones

- `allow_infra_apply: true`, pero acotado a: el `systemd`/`nginx` de esta
  EC2 y la regla de security group descrita arriba — nada más.
- No usar la clave de Groq todavía (es de `M2`) — no hace falta leerla de
  SSM en este ticket.

## Criterios de aceptación

- `https://<ip-o-dominio>/` responde `401` sin auth y `200` con
  `demo`/`demo`.
- `/health` y al menos 2 tools reales responden `200` con datos reales
  desde la instancia pública (no localhost).
- `systemctl status` de la unidad nueva: `active (running)`, sobrevive a
  un `reboot` de prueba si se hace.
- Documentado en `doc/FIL-63-...md`: qué opción de TLS se tomó (dominio+
  Let's Encrypt vs. autofirmado) y la URL/IP final de acceso.
