"""Tests de `gh_git.merge_pr` — que espera a la CI antes de fusionar (tarea 101).

No están en la CI del repo (el job `tests` no recorre `tasks/scripts/`); se
corren a mano:  `python -m pytest tasks/scripts/tests/`.
"""

import subprocess
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gh_git  # noqa: E402


def _config():
    return types.SimpleNamespace(
        gh_bin="gh",
        github_repo="madrono-ucm/madronoTFM",
        gh_merge_method="squash",
        gh_checks_timeout_seconds=900,
    )


class MergePrWaitsForChecksTests(unittest.TestCase):
    def test_espera_a_los_checks_y_luego_fusiona(self):
        llamadas = []

        def fake_run(cmd, cwd=None, timeout=None):
            llamadas.append((cmd, timeout))
            return ""

        self.enterContext(_patch(gh_git, "_run", fake_run))
        gh_git.merge_pr(Path("."), 42, _config())

        self.assertEqual(len(llamadas), 2)
        checks_cmd, checks_timeout = llamadas[0]
        merge_cmd, _ = llamadas[1]
        self.assertEqual(checks_cmd[1:4], ["pr", "checks", "42"])
        self.assertIn("--watch", checks_cmd)
        self.assertIn("--fail-fast", checks_cmd)
        self.assertEqual(checks_timeout, 900)
        self.assertEqual(merge_cmd[1:4], ["pr", "merge", "42"])

    def test_no_fusiona_si_un_check_falla(self):
        def fake_run(cmd, cwd=None, timeout=None):
            if cmd[1:3] == ["pr", "checks"]:
                raise gh_git.GitError("gh pr checks: fallo")
            raise AssertionError("merge_pr no debería llegar al merge con la CI en rojo")

        self.enterContext(_patch(gh_git, "_run", fake_run))
        with self.assertRaises(gh_git.GitError):
            gh_git.merge_pr(Path("."), 42, _config())

    def test_timeout_de_la_ci_se_convierte_en_giterror(self):
        def fake_run(cmd, cwd=None, timeout=None):
            raise subprocess.TimeoutExpired(cmd, timeout)

        self.enterContext(_patch(gh_git, "_run", fake_run))
        with self.assertRaises(gh_git.GitError):
            gh_git.merge_pr(Path("."), 42, _config())


class _patch:
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)
        return self.value

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


if __name__ == "__main__":
    unittest.main()
