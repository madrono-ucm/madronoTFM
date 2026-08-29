"""Tests del productor de menciones de Bluesky sobre lugares de Madrid.

No hacen ninguna llamada de red: usan el fixture
`fixtures/bluesky_search_posts_sample.json`, una respuesta de ejemplo con la
misma forma que devuelve `app.bsky.feed.searchPosts` (ver docstring de
`bluesky_menciones_madrid.py`), pero con `author` (`did`/`handle`/
`displayName`/`avatar`) y `uri`/`cid` sustituidos por valores de relleno
inventados, no de usuarios reales: no hace falta preservar identificadores
reales de terceros para probar que `normalize_post` los descarta.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ingesta.capturas import bluesky_menciones_madrid as bsky
from ingesta.capturas.bluesky_menciones_madrid import (
    MODE_DISTRICT_SWEEP,
    MODE_SEARCH_PLACE,
    CaptureConfig,
    _build_query,
    _hash_text,
    create_session,
    normalize_post,
    search_posts_raw,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SEARCH_POSTS_PATH = FIXTURES_DIR / "bluesky_search_posts_sample.json"


class BuildQueryTests(unittest.TestCase):
    def test_combines_base_term_and_tags(self):
        self.assertEqual(_build_query("Retiro", ["#Madrid", "#Parques"]), "Retiro #Madrid #Parques")

    def test_no_extra_terms(self):
        self.assertEqual(_build_query("Retiro"), "Retiro")


class NormalizePostTests(unittest.TestCase):
    def setUp(self):
        payload = json.loads(SEARCH_POSTS_PATH.read_text(encoding="utf-8"))
        self.raw_posts = payload["posts"]
        self.captured_at = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)

    def test_normalizes_a_post_from_search_place(self):
        record = normalize_post(
            self.raw_posts[0], match_term="Retiro Madrid", mode=MODE_SEARCH_PLACE, captured_at=self.captured_at
        )
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "bluesky_menciones_madrid")
        self.assertEqual(record["mode"], MODE_SEARCH_PLACE)
        self.assertEqual(record["match_term"], "Retiro Madrid")
        self.assertEqual(
            record["text"],
            "El Ayuntamiento activa la alerta amarilla en El Retiro por el calor de esta tarde.",
        )
        self.assertEqual(record["lang"], "es")
        self.assertEqual(record["created_at"], "2026-08-13T10:22:02.727Z")
        self.assertEqual(record["indexed_at"], "2026-08-13T10:22:04.111Z")
        self.assertEqual(record["like_count"], 12)
        self.assertEqual(record["repost_count"], 3)
        self.assertEqual(record["reply_count"], 1)
        self.assertEqual(record["quote_count"], 0)
        self.assertEqual(record["captured_at"], "2026-08-13T20:00:00+02:00")

    def test_normalizes_a_post_from_district_sweep(self):
        record = normalize_post(
            self.raw_posts[1], match_term="eventos:queja", mode=MODE_DISTRICT_SWEEP, captured_at=self.captured_at
        )
        self.assertEqual(record["mode"], MODE_DISTRICT_SWEEP)
        self.assertEqual(record["match_term"], "eventos:queja")
        self.assertIn("agobio", record["text"])

    def test_picks_first_lang_only(self):
        record = normalize_post(
            self.raw_posts[2], match_term="Madrid", mode=MODE_SEARCH_PLACE, captured_at=self.captured_at
        )
        self.assertEqual(record["lang"], "en")

    def test_does_not_leak_author_or_uri_identifiers(self):
        record = normalize_post(
            self.raw_posts[0], match_term="Retiro Madrid", mode=MODE_SEARCH_PLACE, captured_at=self.captured_at
        )
        forbidden_keys = {"author", "did", "handle", "displayName", "avatar", "uri", "cid"}
        self.assertEqual(set(record.keys()) & forbidden_keys, set())

    def test_post_hash_is_deterministic_and_matches_text(self):
        record_a = normalize_post(
            self.raw_posts[0], match_term="Retiro Madrid", mode=MODE_SEARCH_PLACE, captured_at=self.captured_at
        )
        record_b = normalize_post(
            self.raw_posts[0], match_term="otro termino", mode=MODE_DISTRICT_SWEEP, captured_at=self.captured_at
        )
        self.assertEqual(record_a["post_hash"], record_b["post_hash"])
        self.assertEqual(record_a["post_hash"], _hash_text(record_a["text"]))
        self.assertEqual(len(record_a["post_hash"]), 16)

    def test_records_are_json_serializable(self):
        records = [
            normalize_post(post, match_term="Madrid", mode=MODE_SEARCH_PLACE, captured_at=self.captured_at)
            for post in self.raw_posts
        ]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida y sin identificadores."""

    def test_committed_sample_matches_schema_and_both_modes_present(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "bluesky_menciones_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        modes = {record["mode"] for record in records}
        self.assertEqual(modes, {"bajo_demanda", "distrito_sweep"})

        forbidden_keys = {"author", "did", "handle", "displayName", "avatar", "uri", "cid"}
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "bluesky_menciones_madrid")
            self.assertIn("match_term", record)
            self.assertIn("text", record)
            self.assertIn("post_hash", record)
            self.assertIn("created_at", record)
            self.assertEqual(set(record.keys()) & forbidden_keys, set())


def _cfg(**over):
    base = dict(
        api_base_url="https://api.bsky.app",
        auth_base_url="https://bsky.social",
        identifier="madrono97.bsky.social",
        app_password="pc6y-6s6c-6dar-jgit",
        lang="es",
        limit_per_query=5,
        place_queries=[],
        districts=[],
        event_terms=[],
        timeout_seconds=15.0,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )
    base.update(over)
    return CaptureConfig(**base)


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


class AuthTests(unittest.TestCase):
    def test_create_session_posts_credentials_and_returns_jwt(self):
        with mock.patch.object(bsky.requests, "post", return_value=_Resp({"accessJwt": "JWT123"})) as p:
            token = create_session(_cfg())
        self.assertEqual(token, "JWT123")
        url, = p.call_args.args
        self.assertEqual(url, "https://bsky.social/xrpc/com.atproto.server.createSession")
        self.assertEqual(
            p.call_args.kwargs["json"],
            {"identifier": "madrono97.bsky.social", "password": "pc6y-6s6c-6dar-jgit"},
        )

    def test_create_session_without_credentials_raises(self):
        with self.assertRaises(RuntimeError):
            create_session(_cfg(identifier=None, app_password=None))

    def test_search_posts_raw_sends_bearer_token(self):
        with mock.patch.object(bsky.requests, "get", return_value=_Resp({"posts": [{"x": 1}]})) as g:
            posts = search_posts_raw(_cfg(), "Centro Madrid", lang="es", token="JWT123")
        self.assertEqual(posts, [{"x": 1}])
        self.assertEqual(g.call_args.kwargs["headers"]["Authorization"], "Bearer JWT123")
        self.assertTrue(g.call_args.args[0].endswith("/xrpc/app.bsky.feed.searchPosts"))


if __name__ == "__main__":
    unittest.main()
