"""Tests del modelo de datos de la respuesta del asistente."""

import unittest
from datetime import datetime, timezone

from asistente.models.respuesta import (
    FuenteConsultada,
    NivelFiabilidad,
    RespuestaAsistente,
    Veredicto,
)


class RespuestaAsistenteTests(unittest.TestCase):
    def test_builds_with_required_fields_and_defaults(self):
        respuesta = RespuestaAsistente(
            pregunta="¿voy al centro a las nueve de la noche del viernes?",
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.MEDIA,
            explicacion="Ejemplo de explicación trazable.",
        )
        self.assertEqual(respuesta.fuentes, [])
        self.assertIsNotNone(respuesta.generado_en.tzinfo)

    def test_includes_traceable_sources(self):
        fuente = FuenteConsultada(
            dataset="trafico",
            resumen="Intensidad media baja en el punto más cercano.",
            consultado_en=datetime(2026, 8, 14, 21, 0, tzinfo=timezone.utc),
        )
        respuesta = RespuestaAsistente(
            pregunta="¿hay tráfico en Gran Vía ahora?",
            veredicto=Veredicto.FAVORABLE,
            fiabilidad=NivelFiabilidad.ALTA,
            explicacion="Basado en el sensor más próximo.",
            fuentes=[fuente],
        )
        self.assertEqual(respuesta.fuentes[0].dataset, "trafico")

    def test_serializes_to_a_json_compatible_dict(self):
        respuesta = RespuestaAsistente(
            pregunta="¿puedo aparcar en Malasaña esta tarde?",
            veredicto=Veredicto.DESFAVORABLE,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion="Sin plazas libres en los aparcamientos cercanos.",
        )
        payload = respuesta.model_dump(mode="json")
        self.assertEqual(payload["veredicto"], "desfavorable")
        self.assertEqual(payload["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
