"""Tests de `ingesta.capturas.secretos` (`FIL_17`).

Sin credenciales ni red: `boto3.client("ssm")` se sustituye por un doble.
"""

import unittest
from unittest.mock import MagicMock, patch

from ingesta.capturas import secretos


class GetSecretTests(unittest.TestCase):
    def setUp(self):
        secretos.clear_cache()

    def _fake_ssm(self, valor="valor-secreto"):
        cliente = MagicMock()
        cliente.get_parameter.return_value = {"Parameter": {"Value": valor}}
        return cliente

    def test_lee_de_ssm_cuando_hay_path(self):
        cliente = self._fake_ssm("APIKEY-123")
        with patch.dict("os.environ", {"AEMET_API_KEY_SSM_PATH": "/madrono/dev/secrets/aemet"}, clear=True), \
             patch("boto3.client", return_value=cliente):
            self.assertEqual(secretos.get_secret("AEMET_API_KEY"), "APIKEY-123")
        cliente.get_parameter.assert_called_once_with(
            Name="/madrono/dev/secrets/aemet", WithDecryption=True
        )

    def test_cachea_por_cold_start(self):
        cliente = self._fake_ssm("X")
        with patch.dict("os.environ", {"EMT_CLIENT_ID_SSM_PATH": "/p/emt"}, clear=True), \
             patch("boto3.client", return_value=cliente):
            secretos.get_secret("EMT_CLIENT_ID")
            secretos.get_secret("EMT_CLIENT_ID")
        self.assertEqual(cliente.get_parameter.call_count, 1)

    def test_fallback_a_variable_directa(self):
        with patch.dict("os.environ", {"CAMS_ADS_API_KEY": "directo"}, clear=True), \
             patch("boto3.client", side_effect=AssertionError("no debería llamar a SSM")):
            self.assertEqual(secretos.get_secret("CAMS_ADS_API_KEY"), "directo")

    def test_none_si_no_hay_ninguno(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(secretos.get_secret("BLUESKY_APP_PASSWORD"))

    def test_path_tiene_prioridad_sobre_valor_directo(self):
        cliente = self._fake_ssm("desde-ssm")
        with patch.dict(
            "os.environ",
            {"AEMET_API_KEY": "directo", "AEMET_API_KEY_SSM_PATH": "/p/aemet"},
            clear=True,
        ), patch("boto3.client", return_value=cliente):
            self.assertEqual(secretos.get_secret("AEMET_API_KEY"), "desde-ssm")

    def test_error_de_ssm_se_propaga(self):
        cliente = MagicMock()
        cliente.get_parameter.side_effect = RuntimeError("AccessDenied")
        with patch.dict("os.environ", {"AEMET_API_KEY_SSM_PATH": "/p/aemet"}, clear=True), \
             patch("boto3.client", return_value=cliente):
            with self.assertRaises(RuntimeError):
                secretos.get_secret("AEMET_API_KEY")


if __name__ == "__main__":
    unittest.main()
