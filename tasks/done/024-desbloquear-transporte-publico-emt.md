---
id: 24
slug: desbloquear-transporte-publico-emt
title: 'Desbloquear tarea 003: nueva autenticación EMT (v1.1, x-ClientId/passKey)'
status: done
force: true
allow_infra_apply: false
branch: task/024-desbloquear-transporte-publico-emt
pr_number: 71
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/71
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T15:24:12+00:00'
updated_at: '2026-08-14T15:32:45.183419+00:00'
started_at: '2026-08-14T15:26:08.016439+00:00'
submitted_at: '2026-08-14T15:31:38.417677+00:00'
merged_at: '2026-08-14T15:31:42Z'
---

## Contexto

La tarea 003 (`ingesta/capturas/transporte_publico_madrid.py`) quedó bloqueada:
asumió que la API de EMT MobilityLabs se autentica con email+contraseña de una
cuenta personal verificada por correo (endpoint `v1/mobilitylabs/user/login/`,
cabeceras `email`/`password`), y ese registro no se pudo completar de forma
autónoma. Esa asunción era incorrecta: el mecanismo real es distinto — la
API expone un login **v1.1** que se autentica con credenciales de aplicación
(`x-ClientId` + `passKey`) en vez de usuario/contraseña personal:

```
GET https://openapi.emtmadrid.es/v1.1/mobilitylabs/user/login/
Headers: x-ClientId: <valor>, passKey: <valor>, Content-Type: application/json
```

La respuesta (JSON, código 200 si las credenciales son válidas) trae el token en
`data[0].accessToken`, igual que en el flujo v1 que ya implementaba
`normalize`/`capture_once` — solo cambia **cómo se obtiene** el token, no cómo se
usa después contra `stops/{stop_id}/arrives/`.

**Las credenciales de aplicación ya están configuradas en esta EC2** como
variables de entorno `EMT_CLIENT_ID` y `EMT_PASS_KEY` (en el `config.env` del
servicio, fuera del repositorio). Tu proceso las tiene disponibles en el entorno
tal cual — no necesitas registrarte en ningún sitio ni pedirlas.

## Objetivo

Actualizar `transporte_publico_madrid.py` para autenticarse con el flujo real
(v1.1, `x-ClientId`/`passKey`) y completar, esta vez sí, una captura real en vivo.

## Alcance concreto

1. Sustituye la función de login actual (v1, email/password) por una que llame a
   `v1.1/mobilitylabs/user/login/` con las cabeceras `x-ClientId`/`passKey`, leídas
   de las variables de entorno `EMT_CLIENT_ID`/`EMT_PASS_KEY` — nunca hardcodeadas,
   nunca impresas en logs ni en el resumen de `doc/024-desbloquear-transporte-publico-emt.md`
   (ni el valor completo ni el token de acceso resultante; si necesitas dejar
   constancia de que funcionó, usa el código de estado HTTP y, como mucho, los
   primeros caracteres del token con el resto enmascarado).
2. Actualiza `ingesta/README.md`: sustituye la documentación del flujo v1
   (email/password) por el flujo v1.1 real (`x-ClientId`/`passKey`), incluyendo los
   nombres de variable de entorno correctos. Elimina las referencias a
   `EMT_API_EMAIL`/`EMT_API_PASSWORD` si ya no aplican, o dejalas documentadas como
   alternativa si decides mantener compatibilidad — usa tu criterio y documenta la
   decisión.
3. Ejecuta una captura real contra la API (no mock) y sustituye el fixture actual
   de `ingesta/capturas/samples/transporte_publico_madrid_sample.json` (que hoy son
   datos inventados a mano, según quedó documentado en la tarea 003) por datos
   reales.
4. Actualiza `ingesta/tests/test_transporte_publico_madrid.py` para reflejar el
   nuevo flujo de autenticación (sigue sin depender de la red real: usa un fixture
   de respuesta de login v1.1).
5. Actualiza el resumen en `doc/024-desbloquear-transporte-publico-emt.md`
   explicando el cambio de mecanismo de autenticación y confirmando la captura real.

## Restricciones

- NUNCA escribas el valor de `EMT_CLIENT_ID`/`EMT_PASS_KEY` ni del `accessToken`
  obtenido en ningún fichero que se commitee (código, tests, fixtures, docs,
  mensajes de commit). Dado que este repositorio es **público**, cualquier secreto
  commiteado quedaría expuesto públicamente de forma permanente.
- Sigue sin haber infraestructura aplicada para el destino final de estos datos:
  mismo alcance reducido que el resto de capturas (sin cron, sin escritura continua
  en disco, muestra pequeña commiteada como fixture).
- Si por lo que sea la autenticación v1.1 tampoco funcionara con estas
  credenciales, documenta el error exacto (código de estado, mensaje de la API,
  sin incluir las credenciales usadas) en `doc/024-desbloquear-transporte-publico-emt.md`
  y deja el fixture existente tal cual, explicando que sigue bloqueada.

## Criterios de aceptación

- La autenticación usa el flujo v1.1 (`x-ClientId`/`passKey`) leído de variables de
  entorno.
- El fixture commiteado contiene datos reales de llegadas de EMT (o, si la
  autenticación falló, queda documentado el motivo exacto sin exponer credenciales).
- Ningún secreto (credenciales de aplicación ni token de acceso) aparece en ningún
  fichero commiteado.
