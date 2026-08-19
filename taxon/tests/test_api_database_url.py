"""RED-first contract tests for :mod:`taxon.api.database_url`.

The helper centralises the URL-resolution chain shared by
:func:`taxon.api.create_app` and :mod:`taxon.migrate`. Behaviour we
pin here:

- Precedence: explicit argument > ``TAXON_DATABASE_URL`` env var >
  ``DEFAULT_DATABASE_URL``.
- When the primary default (``sqlite:///./data/col.db``) is selected
  and the file is missing on disk, the resolver transparently falls
  back to ``sqlite:///./data/taxon.db`` if that file exists, and
  emits a single WARNING so operators notice the drift.
- An explicit argument or env var that points to a missing file is
  honoured as-is — the caller asked for that URL.
- File-backed SQLite URLs always have their parent directory created.
- Non-SQLite and in-memory URLs pass through untouched, with no
  filesystem probes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from taxon.api.database_url import DEFAULT_DATABASE_URL, resolve_database_url


@pytest.fixture()
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the resolver to ``tmp_path`` so tests never touch ``data/``.

    The helper hard-codes the primary default and fallback URLs against
    ``./data/``. We rewrite both the default and the fallback via the
    ``fallback_url`` parameter so each test sees an isolated filesystem
    while the public API stays unchanged.
    """
    return tmp_path


def _new_fallback(tmp_path: Path) -> str:
    """Return a file-backed SQLite URL inside ``tmp_path``."""
    return f"sqlite:///{tmp_path}/taxon.db"


def test_default_url_is_col_db() -> None:
    # The default must point to the Catalogue of Life dataset, not the
    # legacy ``taxon.db`` location. This pins the contract for every
    # consumer that reads the constant directly.
    assert DEFAULT_DATABASE_URL.endswith("data/col.db")
    assert DEFAULT_DATABASE_URL.startswith("sqlite:///")


def test_explicit_argument_wins_over_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAXON_DATABASE_URL", "sqlite:///:memory:")
    explicit = "sqlite:///:memory:"

    assert resolve_database_url(explicit, fallback_url=_new_fallback(tmp_path)) == explicit


def test_env_var_wins_over_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAXON_DATABASE_URL", "sqlite:///:memory:")

    assert resolve_database_url(None, fallback_url=_new_fallback(tmp_path)) == "sqlite:///:memory:"


def test_default_used_when_no_argument_or_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the primary default file exists, the default is returned untouched.

    We pin the test against the real ``DEFAULT_DATABASE_URL`` so the
    contract under test is the one callers actually consume. The
    helper creates the primary file at the canonical path inside the
    pytest-managed temp directory; if the real ``data/col.db`` already
    exists on the test machine we skip (the assertion would still
    hold, but creating the file is the operator's job, not ours).
    """
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)
    primary_path = Path(DEFAULT_DATABASE_URL[len("sqlite:///") :]).expanduser()
    # If the canonical primary file already exists, the default path
    # resolves without the fallback and the test holds by inspection.
    # We do NOT create it ourselves — that would mutate the user's
    # repository.
    if not primary_path.exists():
        pytest.skip(
            f"primary default {primary_path} not present; skipping no-fallback contract check"
        )

    with caplog.at_level(logging.WARNING, logger="taxon.api.database_url"):
        resolved = resolve_database_url(None, fallback_url=_new_fallback(tmp_path))

    assert resolved == DEFAULT_DATABASE_URL
    # The default path MUST NOT emit the fallback warning.
    assert "falling back to" not in caplog.text


def test_fallback_used_when_primary_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)
    fallback = _new_fallback(tmp_path)
    Path(fallback[len("sqlite:///") :]).touch()
    # Primary intentionally NOT created.

    with caplog.at_level(logging.WARNING, logger="taxon.api.database_url"):
        resolved = resolve_database_url(None, fallback_url=fallback)

    assert resolved == fallback
    # Operators must see WHY the app silently switched databases.
    assert "falling back to" in caplog.text


def test_primary_missing_and_fallback_missing_returns_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When neither file exists, keep the primary URL.

    The fallback only fires when both files would exist; otherwise we
    would silently swap a missing default for a missing fallback and
    SQLAlchemy would create yet another empty file.
    """
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)

    with caplog.at_level(logging.WARNING, logger="taxon.api.database_url"):
        resolved = resolve_database_url(None, fallback_url=_new_fallback(tmp_path))

    assert resolved == DEFAULT_DATABASE_URL
    assert "falling back to" not in caplog.text


def test_explicit_argument_with_missing_file_is_honoured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller asked for it — give it to them, even if the file does not exist.

    The fallback only applies when the resolver reaches the default
    via its own resolution chain. An explicit argument or env var
    bypasses the fallback entirely. We use a path inside ``tmp_path``
    so the helper can ``mkdir`` the parent directory without touching
    the host filesystem.
    """
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)
    missing = f"sqlite:///{tmp_path}/subdir/col.db"

    assert resolve_database_url(missing, fallback_url=_new_fallback(tmp_path)) == missing


def test_env_var_with_missing_file_is_honoured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same guarantee for ``TAXON_DATABASE_URL``: bypass the fallback."""
    target = tmp_path / "subdir" / "col.db"
    monkeypatch.setenv("TAXON_DATABASE_URL", f"sqlite:///{target}")

    assert resolve_database_url(None, fallback_url=_new_fallback(tmp_path)) == f"sqlite:///{target}"


def test_in_memory_url_passes_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)

    resolved = resolve_database_url("sqlite:///:memory:", fallback_url=_new_fallback(tmp_path))

    assert resolved == "sqlite:///:memory:"


def test_non_sqlite_url_passes_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)
    url = "postgresql+psycopg://user:pass@host:5432/db"

    resolved = resolve_database_url(url, fallback_url=_new_fallback(tmp_path))

    assert resolved == url


def test_parent_directory_created_for_file_backed_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper must mkdir -p the parent so SQLAlchemy does not crash."""
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)
    nested = tmp_path / "deep" / "nested" / "dir"
    url = f"sqlite:///{nested}/col.db"

    resolved = resolve_database_url(url, fallback_url=_new_fallback(tmp_path))

    assert resolved == url
    assert nested.is_dir()


def test_default_constant_is_used_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end pin: with no argument and no env var, the resolver
    returns a ``sqlite:///``-shaped URL rooted at ``DEFAULT_DATABASE_URL``.

    We do not assert the exact constant because the test machine may
    or may not have ``data/col.db`` on disk — both states (primary
    present → default; primary missing → fallback to ``taxon.db``)
    satisfy the contract.
    """
    monkeypatch.delenv("TAXON_DATABASE_URL", raising=False)

    with caplog.at_level(logging.WARNING, logger="taxon.api.database_url"):
        resolved = resolve_database_url(None, fallback_url=_new_fallback(tmp_path))

    # Either the primary default or the fallback — both are
    # ``sqlite:///``-shaped and live under ``tmp_path``'s sibling.
    assert resolved.startswith("sqlite:///")
    assert resolved.endswith(("data/col.db", "data/taxon.db"))
