---
kind: vic-eval
title: "Memoria — §6.5–6.6 Orquestación, almacenamiento y consulta: verificar estado del pipeline + diagrama de orquestación"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: []
---

## Contexto

§6.5 describe los Glue Triggers (`SCHEDULED`/`CONDITIONAL`) y §6.6 el
acceso dual Athena/Neo4j vía el agente MCP. El riesgo principal aquí es
**temporal**: la memoria ya documenta la congelación del pipeline desde el
30/8 (vía `VIC_38`/`VIKT_11`), pero hay que confirmar que sigue congelado
hoy (15/9) y no ha habido una reanudación o un nuevo evento de
mantenimiento sin documentar (verificado: `infra/terraform/terraform.tfvars`
tenía `pipeline_enabled = false` hace 5 días — confirmar que sigue así,
dado el volumen de actividad `FIL_69`-`99` reciente, que podría haber
requerido otra ventana de mantenimiento como la del `FIL_16`/`17`).

## Alcance

1. Verificar `pipeline_enabled` actual y, si cambió, revisar `PROGRESS.md`/
   `git log -- infra/terraform/` para entender cuándo y por qué, y
   actualizar la narrativa de congelación en consecuencia (aquí y en
   cualquier otro punto de la memoria que la mencione — §7.4 principalmente,
   coordinar con `VIC_52`).
2. Confirmar que el nº de reglas EventBridge/triggers Glue citado (23
   reglas, ver `VIC_38`/`FIL_89`) sigue siendo correcto — no debería haber
   cambiado si el pipeline sigue congelado y no se añadieron fuentes
   nuevas, pero verificar.
3. §6.6: confirmar que la descripción de "el agente MCP traduce la
   pregunta del usuario en Cypher/SQL y combina resultados" sigue siendo
   precisa dado que `consulta_grafo` (`FIL_67`/`72`) y el explorador en
   vivo (`FIL_67` Parte 3) añaden vías de consulta adicionales que quizá
   merezcan una frase — sin invadir el espacio de `VIC_50` (que cubre
   §6.7 en profundidad).
4. **Diagrama**: un diagrama de orquestación (secuencia o flujo) mostrando
   el patrón `SCHEDULED`→Bronze→Silver, `CONDITIONAL`→Silver→Gold, por
   cadencia (horaria/diaria/horas fijas) — puede ser el mismo diagrama que
   `VIC_48` extendido con la capa de triggers, o uno separado si queda más
   claro. Decidir y documentar la elección.

## Fuentes técnicas

`infra/terraform/terraform.tfvars`, `infra/terraform/*.tf` (schedulers/
triggers), `PROGRESS.md`, `NEXT_STEPS.md`.

## Criterios de aceptación

- Estado de congelación del pipeline verificado a fecha de hoy (15/9), no
  asumido de hace 5 días.
- Cifras de reglas/triggers verificadas.
- Diagrama de orquestación insertado.
