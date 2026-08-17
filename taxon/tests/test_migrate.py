"""Contract tests for the standalone ``taxon.migrate`` script.

Issue #68 ships a no-Alembic migration mechanism: the FastAPI lifespan
runs ``Base.metadata.create_all`` for the three workspace tables, and
the standalone ``python -m taxon.migrate {dry-run|apply}`` script
mirrors the same call out-of-band so a fresh DB can be bootstrapped
without booting the API.

The tests pin:

- ``dry-run`` prints a summary naming the missing tables without
  mutating the database.
- ``apply`` creates the three new tables without dropping pre-existing
  ``taxa`` / ``species_paths``.
- The script reads ``TAXON_DATABASE_URL`` (and ``--database-url``) so
  the operator can point it at a different DB.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def _fresh_db(tmp_path: Path) -> Path:
    """Return an empty SQLite file path with the parent directory created."""
    db = tmp_path / "taxon.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.touch()
    return db


def _tables(db_path: Path) -> set[str]:
    """Return the set of table names present in the SQLite database."""
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def _run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Invoke ``python -m taxon.migrate`` with ``argv``.

    Running the script as a subprocess (rather than importing it) keeps
    the test honest about the CLI surface: argparse, stdout, and exit
    codes all behave the way operators see them.
    """
    return subprocess.run(
        [sys.executable, "-m", "taxon.migrate", *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture
def env_with_pythonpath(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> dict[str, str]:
    """A subprocess env that preserves PATH and sets PYTHONPATH to the repo root.

    The repo's ``pyproject.toml`` declares ``pythonpath = ["."]`` but
    the subprocess may not honour that without an explicit
    ``PYTHONPATH`` override when ``pip install -e .`` was not run.
    """
    repo = str(repo_root)
    env = os.environ.copy()
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    return env


@pytest.fixture
def repo_root() -> Path:
    """Absolute path of the worktree where the test runs."""
    return Path(__file__).resolve().parents[1]


def test_dry_run_reports_missing_tables(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """``dry-run`` prints a summary naming the three missing tables and exits 1."""
    db = _fresh_db(tmp_path)
    completed = _run(
        ["dry-run", "--database-url", f"sqlite:///{db}"],
        env_with_pythonpath,
    )
    assert completed.returncode == 1, (
        f"dry-run must exit 1 on missing tables; stderr={completed.stderr!r}"
    )
    assert "species_explored" in completed.stdout
    assert "species_folders" in completed.stdout
    assert "link_visited" in completed.stdout
    # The database MUST NOT be mutated by a dry-run.
    assert _tables(db) == set()


def test_apply_creates_three_new_tables(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """``apply`` creates the three workspace tables."""
    db = _fresh_db(tmp_path)
    completed = _run(
        ["apply", "--database-url", f"sqlite:///{db}"],
        env_with_pythonpath,
    )
    assert completed.returncode == 0, f"apply must exit 0 on success; stderr={completed.stderr!r}"
    tables = _tables(db)
    assert {"species_explored", "species_folders", "link_visited"}.issubset(tables)


def test_apply_is_idempotent(tmp_path: Path, env_with_pythonpath: dict[str, str]) -> None:
    """Re-running ``apply`` on a populated DB exits 0 and does NOT drop tables."""
    db = _fresh_db(tmp_path)
    _run(["apply", "--database-url", f"sqlite:///{db}"], env_with_pythonpath)
    first_tables = _tables(db)
    completed = _run(
        ["apply", "--database-url", f"sqlite:///{db}"],
        env_with_pythonpath,
    )
    assert completed.returncode == 0, (
        f"second apply must be idempotent; stderr={completed.stderr!r}"
    )
    assert "already present" in completed.stdout.lower()
    assert _tables(db) == first_tables


def test_apply_does_not_drop_pre_existing_tables(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """A pre-existing ``taxa`` table is NOT dropped by ``apply``."""
    db = _fresh_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE taxa (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.execute("CREATE TABLE species_paths (id INTEGER PRIMARY KEY, species TEXT NOT NULL)")
        conn.commit()

    completed = _run(
        ["apply", "--database-url", f"sqlite:///{db}"],
        env_with_pythonpath,
    )
    assert completed.returncode == 0, f"apply must exit 0; stderr={completed.stderr!r}"
    tables = _tables(db)
    assert "taxa" in tables, "apply must not drop pre-existing taxa table"
    assert "species_paths" in tables, "apply must not drop pre-existing species_paths table"


def test_dry_run_after_apply_reports_no_missing(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """After ``apply``, ``dry-run`` reports no missing tables (exit 0)."""
    db = _fresh_db(tmp_path)
    _run(["apply", "--database-url", f"sqlite:///{db}"], env_with_pythonpath)
    completed = _run(
        ["dry-run", "--database-url", f"sqlite:///{db}"],
        env_with_pythonpath,
    )
    assert completed.returncode == 0, (
        f"dry-run on populated DB must exit 0; stderr={completed.stderr!r}"
    )
    assert "already present" in completed.stdout.lower()


def test_reads_taxon_database_url_env(tmp_path: Path, env_with_pythonpath: dict[str, str]) -> None:
    """The script honours ``TAXON_DATABASE_URL`` when ``--database-url`` is absent."""
    db = _fresh_db(tmp_path)
    env = dict(env_with_pythonpath)
    env["TAXON_DATABASE_URL"] = f"sqlite:///{db}"
    completed = _run(["dry-run"], env)
    assert completed.returncode == 1, f"dry-run must exit 1; stderr={completed.stderr!r}"
    assert "species_explored" in completed.stdout
