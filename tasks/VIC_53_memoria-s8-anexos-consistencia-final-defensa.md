---
kind: vic-eval
title: "Memoria — §8 Anexos + pase de consistencia final de todo el documento (ÚLTIMO ticket, corre después de todos los demás)"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: [VIC_45, VIC_46, VIC_47, VIC_48, VIC_49, VIC_50, VIC_51, VIC_52]
---

## Contexto

Cierre de la ronda `VIC_45`-`53`. Mismo rol que `VIC_07`/`VIKT_09` en
rondas anteriores: una pasada final de extremo a extremo, después de que
todos los demás tickets hayan tocado su sección, para detectar
contradicciones **entre** secciones que ningún ticket individual vería
(p.ej. si `VIC_47` sube el recuento de tools a un número y `VIC_50` cita
otro, o si una figura nueva de `VIC_46`/`47`/`48`/`49`/`50`/`51` no quedó
bien numerada como "Figura N").

## Alcance

1. **Numeración de figuras**: con hasta 6 figuras nuevas de esta ronda
   (`VIC_46` cronograma, `VIC_47` arquitectura, `VIC_48` pipeline datos,
   `VIC_49` orquestación, `VIC_50` secuencia, `VIC_51` pipeline ML) más las
   2 ya existentes (Figura 1 arquitectura *vieja*, sustituida por
   `VIC_47`; Figura 2 resiliencia) — renumerar todas de forma correlativa
   y actualizar cada referencia cruzada "(Figura N)" en el texto. Este es
   el paso con más riesgo de error manual — hacerlo con un script que
   liste todos los `w:drawing` reales del documento en orden y cruce
   contra las menciones "Figura N" en el texto, no a ojo.
2. **Anexo A**: confirmar que el resumen de categorías de fuentes sigue
   preciso.
3. **Anexo B (Glosario)**: añadir cualquier término técnico nuevo
   introducido por esta ronda que no estuviera ya (p.ej. si `VIC_50`
   introduce "traza de herramientas" o "explicabilidad conversacional"
   como concepto).
4. **Anexo C (Reproducibilidad)**: confirmar que los comandos para
   regenerar las figuras nuevas (`VIC_46`-`51`) están documentados aquí
   igual que los de `modelado/`, con su ruta real.
5. **Pase de consistencia global**: grep de términos que no deberían
   aparecer fuera de §7.5 (Kafka, Flink, Delta, Power BI, streaming),
   grep del recuento de tools para confirmar que aparece **una sola cifra**
   en todo el documento, verificación de que toda referencia cruzada
   "(véase X.Y)" apunta a una sección que existe con ese número.
6. **Redacción final**: lectura completa (o al menos por muestreo
   representativo si el tiempo no alcanza para las ~40 páginas) buscando
   inconsistencias de registro, términos usados de forma distinta en
   secciones distintas, y la típica "costura" que delata que el documento
   se escribió en sesiones separadas.

## Fuentes técnicas

El propio `.docx` final tras `VIC_45`-`52`, más un script de verificación
ad-hoc (`python-docx`, contar `w:drawing`, extraer todo el texto y hacer
los greps).

## Criterios de aceptación

- Figuras numeradas correlativamente, cero referencias cruzadas rotas.
- Grep de términos obsoletos limpio.
- Una sola cifra de recuento de tools en todo el documento.
- Documento leído de principio a fin al menos una vez en esta pasada.
