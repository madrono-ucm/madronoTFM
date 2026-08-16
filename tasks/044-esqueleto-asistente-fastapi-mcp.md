---
id: 44
slug: esqueleto-asistente-fastapi-mcp
title: Esqueleto del asistente conversacional (FastAPI + agente MCP)
status: in_progress
force: true
allow_infra_apply: false
branch: task/044-esqueleto-asistente-fastapi-mcp
pr_number: null
pr_url: null
attempts: 6
next_retry_at: '2026-08-16T00:00:12.520214+00:00'
last_error: You've hit your session limit · resets 9:40pm (UTC)
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-16T00:00:53.361195+00:00'
started_at: '2026-08-15T18:28:44.449045+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La memoria (apartados 5.2, 6.7) describe la cara ciudadana del proyecto: el
asistente conversacional «Madroño», un servicio FastAPI con un agente MCP que
responde preguntas como «¿voy al centro a las nueve de la noche del viernes?» con
un veredicto, una fiabilidad, y una explicación trazable a los datos.

**Este servicio depende de que exista Gold** (tareas 041 y sus extensiones
futuras) para responder con datos reales — esta tarea es solo el **esqueleto**:
estructura del servicio, no la lógica de negocio completa, que no tiene sentido
implementar todavía sin datos de Gold que consultar.

**Alcance: solo código de aplicación (y, si hace falta, infraestructura como
código), sin desplegar nada en AWS.**

## Objetivo

Crear la estructura base de un servicio FastAPI con un endpoint de salud, y un
esqueleto de agente MCP con las herramientas (`tools`) que ya se pueden anticipar
a partir de lo ya capturado, aunque todavía no lean de Gold real.

## Alcance concreto

1. Crea un directorio nuevo (p.ej. `asistente/`) con una app FastAPI mínima: un
   endpoint `/health` y la estructura de proyecto (routers, config, dependencias)
   — usa un patrón estándar y documenta las decisiones de estructura.
2. Define, como esqueleto de agente MCP, las herramientas (`tools`) que ya se
   pueden anticipar de lo capturado hasta ahora: afluencia prevista, calidad del
   aire, opciones de movilidad, disponibilidad de aparcamiento, eventos cercanos
   (memoria, apartado 6.7) — cada una como una función con firma y docstring
   claros, pero **sin implementación real todavía** (`raise NotImplementedError`
   o un mock explícito), ya que no hay Gold del que leer. No es el objetivo de
   esta tarea conectar nada a datos reales.
3. Define el esquema de la respuesta del asistente tal como lo describe la
   memoria: veredicto, nivel de fiabilidad, explicación trazable — como un modelo
   de datos (p.ej. Pydantic) reutilizable.
4. Tests del esqueleto (que la app arranca, que `/health` responde, que las
   `tools` tienen la firma esperada) — no hace falta más, no hay lógica real que
   probar todavía.
5. `requirements.txt`/dependencias del nuevo servicio (FastAPI, el SDK de MCP que
   corresponda — investiga cuál es el estándar actual, documenta la elección) y un
   README (`asistente/README.md`) explicando el estado (esqueleto, no funcional
   todavía) y qué haría falta para completarlo (Gold real, tarea 041 extendida a
   más fuentes).

## Restricciones

- NO implementes lógica de negocio real ni conectes a ninguna fuente de datos real
  (ni Bronze, ni Silver, ni Gold) — es un esqueleto.
- NO despliegues nada en AWS — si decides que hace falta algo de infraestructura
  para correr el servicio (EC2/Lambda/ECS), escríbela como código Terraform sin
  aplicarla, igual que las tareas 041-043.
- No captures ninguna credencial real en ningún fichero commiteado.

## Criterios de aceptación

- Servicio FastAPI mínimo que arranca y responde en `/health`, con tests.
- Esqueleto de herramientas MCP con firmas claras, sin implementación real.
- Modelo de datos de la respuesta del asistente (veredicto/fiabilidad/explicación)
  definido.
- README documentando el estado y los siguientes pasos.
