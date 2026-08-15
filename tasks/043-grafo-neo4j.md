---
id: 43
slug: grafo-neo4j
title: Grafo urbano en Neo4j — infraestructura, sin aplicar
status: in_progress
force: true
allow_infra_apply: false
branch: task/043-grafo-neo4j
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-15T18:20:44.516699+00:00'
started_at: '2026-08-15T18:20:44.516674+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La memoria (apartado 5.2) describe el grafo urbano (Neo4j) construido sobre la
capa Gold: lugares, estaciones de medida, conexiones de transporte. Todavía no se
ha decidido ni empezado. A diferencia de Kafka (ya decidido: autogestionado), aquí
la decisión sigue abierta.

**Alcance: solo escribir infraestructura como código, no aplicar nada en AWS.**

## Objetivo

Decidir entre Neo4j autogestionado en EC2 o Neo4j AuraDB Free (SaaS gestionado por
Neo4j, con un tier gratuito), e implementar la infraestructura correspondiente.

## Alcance concreto

1. Investiga las condiciones reales del tier gratuito de Neo4j AuraDB Free
   vigentes ahora mismo (límites de tamaño, si expira o se pausa por inactividad,
   si permite acceso programático sin tarjeta de crédito) y compáralo con
   autogestionado en EC2 (coste de la instancia, esfuerzo de mantenimiento,
   backups). Decide con criterio, documentando explícitamente el porqué — no es
   una decisión trivial, tómatela en serio.
2. Si autogestionado: Terraform de una EC2 dedicada (separada de la de este
   pipeline), con Neo4j instalado, security group de acceso mínimo (igual criterio
   que la tarea 042 para Kafka).
3. Si AuraDB Free: documenta el proceso de alta (probablemente requiere un paso
   manual del usuario, igual que EMT/AEMET/CAMS — si es así, documenta el bloqueo
   igual que en esas tareas, con el código lo más preparado posible para cuando
   existan credenciales) y qué necesitaría el proyecto para conectarse
   (variables de entorno, sin hardcodear nada).
4. Define, como código, el esquema inicial del grafo: tipos de nodo (lugar,
   estación, barrio/distrito) y tipos de relación (proximidad, conexión de
   transporte) — no hace falta cargar datos reales todavía, solo el esquema/
   constraints iniciales (p.ej. como un script Cypher versionado).
5. Documenta en un README nuevo (p.ej. `infra/neo4j/README.md`) la decisión y el
   diseño del esquema.

## Restricciones

- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- No captures ninguna credencial real en ningún fichero commiteado.
- No cargues datos reales en el grafo — es esquema e infraestructura, no ETL
  todavía (eso depende de que exista Gold, tarea 041 y sus extensiones futuras).

## Criterios de aceptación

- Decisión (autogestionado vs. AuraDB Free) tomada y documentada con criterio.
- Infraestructura correspondiente escrita (Terraform si autogestionado,
  documentación del alta si AuraDB), sin aplicar.
- Esquema inicial del grafo (nodos/relaciones) definido como código versionado.
