"""FIL_83 — `asistente.cache.cacheado`: TTL + LRU, opt-in por entorno."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from asistente import cache


class CacheTests(unittest.TestCase):
    def _fn(self):
        llamadas = {"n": 0}

        @cache.cacheado(ttl_s=100, maxsize=3)
        def f(x, y=0, *, athena_client=None):
            llamadas["n"] += 1
            return x + y + llamadas["n"] * 1000  # cambia si se vuelve a ejecutar

        return f, llamadas

    def test_desactivada_por_defecto(self):
        # sin ASSISTANT_CACHE_TTL -> siempre llama a la función real
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASSISTANT_CACHE_TTL", None)
            f, ll = self._fn()
            self.assertNotEqual(f(1), f(1))
            self.assertEqual(ll["n"], 2)
            self.assertFalse(cache.ultimo_fue_hit())

    def test_hit_dentro_del_ttl(self):
        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "100"}):
            f, ll = self._fn()
            a = f(1, 2)
            b = f(1, 2)
            self.assertEqual(a, b)
            self.assertEqual(ll["n"], 1)
            self.assertTrue(cache.ultimo_fue_hit())

    def test_clave_distingue_argumentos(self):
        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "100"}):
            f, ll = self._fn()
            f(1, 2)
            f(1, 3)
            f(9, 2)
            self.assertEqual(ll["n"], 3)

    def test_cliente_inyectable_no_forma_parte_de_la_clave(self):
        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "100"}):
            f, ll = self._fn()
            f(1, 2, athena_client="A")
            f(1, 2, athena_client="B")  # mismo resultado -> hit
            self.assertEqual(ll["n"], 1)
            self.assertTrue(cache.ultimo_fue_hit())

    def test_expira(self):
        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "100"}):
            f, ll = self._fn()
            t = [0.0]
            with patch("asistente.cache.time.monotonic", side_effect=lambda: t[0]):
                f(1)
                t[0] = 50
                f(1)
                self.assertEqual(ll["n"], 1)  # dentro del ttl
                t[0] = 200
                f(1)
                self.assertEqual(ll["n"], 2)  # expirado

    def test_lru_cota(self):
        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "100"}):
            f, ll = self._fn()
            for x in range(5):  # maxsize=3
                f(x)
            self.assertLessEqual(f.cache_len(), 3)

    def test_ttl_efectivo_es_el_minimo(self):
        # decorador ttl_s=100, env=10 -> efectivo 10
        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "10"}):
            f, ll = self._fn()
            t = [0.0]
            with patch("asistente.cache.time.monotonic", side_effect=lambda: t[0]):
                f(1)
                t[0] = 20
                f(1)
                self.assertEqual(ll["n"], 2)


if __name__ == "__main__":
    unittest.main()
