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


def _indexes(db_path: Path, table: str = "taxa") -> set[str]:
    """Return the set of index names attached to ``table`` in the SQLite database.

    Uses ``sqlite_master`` filtered by ``tbl_name`` so the assertion targets
    index identity, not column shape (CREATE INDEX statements may include
    ``UNIQUE`` or sort-order qualifiers that vary across SQLAlchemy versions).
    """
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
                (table,),
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


# ---------------------------------------------------------------------------
# ix_taxa_parent_rank_name composite index migration
# ---------------------------------------------------------------------------
#
# PR A.2 of #76 introduces a composite index on ``taxa(parent_id, rank, name)``
# to accelerate the per-tier recursive CTE used by ``/api/tree/children``.
# The migration is idempotent (``CREATE INDEX IF NOT EXISTS``) so the
# standalone ``taxon.migrate`` script must keep that contract.


def test_migrate_creates_parent_rank_name_index(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """``apply`` creates the composite ``ix_taxa_parent_rank_name`` index and is idempotent.

    Pre-condition: pre-seed a ``taxa`` table with a few rows so the index
    has data to attach to. Drop the index if it already exists (defensive),
    run ``apply``, assert the index now exists; run ``apply`` again and
    assert the index still exists.
    """
    db = _fresh_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE taxa ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER, "
            "rank TEXT NOT NULL, "
            "name TEXT NOT NULL, "
            "display_name TEXT NOT NULL, "
            "display_level TEXT, "
            "source_id TEXT NOT NULL UNIQUE, "
            "is_synonym INTEGER NOT NULL DEFAULT 0, "
            "is_extinct INTEGER NOT NULL DEFAULT 0, "
            "is_uncertain INTEGER NOT NULL DEFAULT 0, "
            "is_unassigned INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        # Seed a few rows so the index has data to attach to.
        conn.executemany(
            "INSERT INTO taxa (id, parent_id, rank, name, display_name, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, None, "kingdom", "Animalia", "Animalia", "worms:1"),
                (2, 1, "phylum", "Chordata", "Chordata", "worms:2"),
                (3, 2, "class", "Mammalia", "Mammalia", "worms:3"),
            ],
        )
        # Defensive: drop the index if it pre-exists.
        conn.execute("DROP INDEX IF EXISTS ix_taxa_parent_rank_name")
        conn.commit()

    first = _run(["apply", "--database-url", f"sqlite:///{db}"], env_with_pythonpath)
    assert first.returncode == 0, f"apply must exit 0; stderr={first.stderr!r}"

    indexes = _indexes(db, "taxa")
    assert "ix_taxa_parent_rank_name" in indexes, (
        f"apply must create ix_taxa_parent_rank_name; got {indexes!r}"
    )

    # Idempotency: a second apply must NOT raise and the index must remain.
    second = _run(["apply", "--database-url", f"sqlite:///{db}"], env_with_pythonpath)
    assert second.returncode == 0, (
        f"second apply must be idempotent; stderr={second.stderr!r}"
    )
    assert "ix_taxa_parent_rank_name" in _indexes(db, "taxa"), (
        "second apply must preserve ix_taxa_parent_rank_name"
    )


def test_migrate_skips_index_if_present(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """``apply`` is a no-op for the index when it already exists.

    Pre-create ``taxa`` AND the index, then run ``apply`` and confirm:

    - exit code 0
    - the pre-existing index is still present
    - the row count is preserved (no destructive operations)
    """
    db = _fresh_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE taxa ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER, "
            "rank TEXT NOT NULL, "
            "name TEXT NOT NULL, "
            "display_name TEXT NOT NULL, "
            "display_level TEXT, "
            "source_id TEXT NOT NULL UNIQUE, "
            "is_synonym INTEGER NOT NULL DEFAULT 0, "
            "is_extinct INTEGER NOT NULL DEFAULT 0, "
            "is_uncertain INTEGER NOT NULL DEFAULT 0, "
            "is_unassigned INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        conn.execute(
            "INSERT INTO taxa (id, parent_id, rank, name, display_name, source_id) "
            "VALUES (1, NULL, 'kingdom', 'Animalia', 'Animalia', 'worms:1')"
        )
        conn.execute("CREATE INDEX ix_taxa_parent_rank_name ON taxa (parent_id, rank, name)")
        conn.commit()

    completed = _run(["apply", "--database-url", f"sqlite:///{db}"], env_with_pythonpath)
    assert completed.returncode == 0, f"apply must exit 0; stderr={completed.stderr!r}"
    assert "ix_taxa_parent_rank_name" in _indexes(db, "taxa"), (
        "pre-existing index must remain after apply"
    )
    with sqlite3.connect(db) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM taxa").fetchone()[0]
    assert row_count == 1, "apply must not delete rows from taxa"


def test_migrate_preserves_existing_indexes(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """``apply`` must NOT drop the three pre-existing ``taxa`` indexes when adding the new one.

    Pre-seed ``taxa`` with rows AND the three prior indexes
    (``ix_taxa_parent_name``, ``ix_taxa_rank``, ``ix_taxa_display_level``).
    Run ``apply`` and confirm the four indexes coexist afterwards.
    """
    db = _fresh_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE taxa ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER, "
            "rank TEXT NOT NULL, "
            "name TEXT NOT NULL, "
            "display_name TEXT NOT NULL, "
            "display_level TEXT, "
            "source_id TEXT NOT NULL UNIQUE, "
            "is_synonym INTEGER NOT NULL DEFAULT 0, "
            "is_extinct INTEGER NOT NULL DEFAULT 0, "
            "is_uncertain INTEGER NOT NULL DEFAULT 0, "
            "is_unassigned INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        conn.executemany(
            "INSERT INTO taxa (id, parent_id, rank, name, display_name, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, None, "kingdom", "Animalia", "Animalia", "worms:1"),
                (2, 1, "phylum", "Chordata", "Chordata", "worms:2"),
            ],
        )
        conn.execute("CREATE INDEX ix_taxa_parent_name ON taxa (parent_id, name)")
        conn.execute("CREATE INDEX ix_taxa_rank ON taxa (rank)")
        conn.execute("CREATE INDEX ix_taxa_display_level ON taxa (display_level)")
        conn.commit()

    completed = _run(["apply", "--database-url", f"sqlite:///{db}"], env_with_pythonpath)
    assert completed.returncode == 0, f"apply must exit 0; stderr={completed.stderr!r}"

    indexes = _indexes(db, "taxa")
    # The three pre-existing indexes must remain untouched.
    assert "ix_taxa_parent_name" in indexes, "ix_taxa_parent_name must survive"
    assert "ix_taxa_rank" in indexes, "ix_taxa_rank must survive"
    assert "ix_taxa_display_level" in indexes, "ix_taxa_display_level must survive"
    # The new index must be present too.
    assert "ix_taxa_parent_rank_name" in indexes, "ix_taxa_parent_rank_name must be added"
    # Row count must remain.
    with sqlite3.connect(db) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM taxa").fetchone()[0]
    assert row_count == 2, "apply must not delete rows"
