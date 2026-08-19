"""Shared SQLite URL resolution for the API and migrate scripts.

Both :func:`taxon.api.create_app` and :mod:`taxon.migrate` resolve a
SQLAlchemy URL from the same precedence chain (explicit argument,
``TAXON_DATABASE_URL`` environment variable, ``DEFAULT_DATABASE_URL``).
Previously each entry point carried its own near-identical copy of
``_resolve_database_url``; this module is the single source of truth so
behaviour stays in lock-step — especially the on-disk presence check
that backs the ``col.db`` → ``taxon.db`` fallback introduced when
the CoL dataset became the primary default.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Primary default: the Catalogue of Life SQLite produced by
# ``python -m taxon.import_data``. Lives next to ``pyproject.toml`` so a
# single ``python -m taxon.main`` invocation finds the imported dataset
# without any extra config.
DEFAULT_DATABASE_URL = "sqlite:///./data/col.db"

# When ``DEFAULT_DATABASE_URL`` is in use and the on-disk file is
# missing, fall back to the legacy ``taxon.db`` location. CoL has been
# the canonical dataset since the GBIF dataset was retired, but older
# checkouts and CI caches may still ship with ``taxon.db`` only.
_FALLBACK_DATABASE_URL = "sqlite:///./data/taxon.db"

_logger = logging.getLogger(__name__)


def _sqlite_path(database_url: str) -> str | None:
    """Return the on-disk path component of a ``sqlite:///`` URL.

    Returns ``None`` for in-memory URLs (``sqlite:///:memory:``) or
    any non-SQLite URL so callers can skip the fallback probe without
    branching on URL shape themselves.
    """
    if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:///:memory:"):
        return database_url[len("sqlite:///") :]
    return None


def _sqlite_file_exists(database_url: str) -> bool:
    """True iff ``database_url`` is a file-backed SQLite URL and the file exists."""
    path_part = _sqlite_path(database_url)
    if path_part is None or path_part == ":memory:":
        return False
    return Path(path_part).expanduser().is_file()


def resolve_database_url(
    database_url: str | None,
    *,
    fallback_url: str = _FALLBACK_DATABASE_URL,
) -> str:
    """Resolve the effective database URL and apply the fallback rule.

    Precedence:
      1. Explicit ``database_url`` argument.
      2. ``TAXON_DATABASE_URL`` environment variable.
      3. ``DEFAULT_DATABASE_URL`` (``sqlite:///./data/col.db``) — and
         when this default is in use **and** the on-disk file is
         missing, transparently fall back to ``fallback_url``
         (``sqlite:///./data/taxon.db``) so older checkouts keep
         booting without an environment override.

    The fallback only kicks in when the default is reached via the
    resolution chain. An explicit argument or env var that points to a
    missing file is honoured as-is — the caller asked for that URL.
    A single WARNING is logged the first time the fallback fires in a
    process so operators notice the drift between the dataset the
    default advertises and the dataset the app actually opened.
    """
    resolved = database_url or os.environ.get("TAXON_DATABASE_URL") or DEFAULT_DATABASE_URL
    # The fallback only applies when we reached the default AND the
    # caller did not override the URL via argument or env. Both of
    # those paths are signalled by ``resolved`` matching ``DEFAULT_DATABASE_URL``
    # exactly, since neither alternative path mutates the constant.
    if resolved == DEFAULT_DATABASE_URL and not _sqlite_file_exists(resolved):
        fallback = fallback_url
        # Only fall back when the alternative exists. Otherwise we'd
        # silently swap a missing default for a missing fallback and
        # SQLAlchemy would create yet another empty file — strictly
        # worse than letting the default path surface the missing file.
        if _sqlite_file_exists(fallback):
            _logger.warning(
                "DEFAULT_DATABASE_URL %s is missing on disk; falling back to %s",
                resolved,
                fallback,
            )
            resolved = fallback
    # Ensure the parent directory exists for any file-backed SQLite URL.
    # In-memory URLs are passed through untouched.
    path_part = _sqlite_path(resolved)
    if path_part is not None and path_part != ":memory:":
        Path(path_part).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return resolved


__all__ = ["DEFAULT_DATABASE_URL", "resolve_database_url"]
