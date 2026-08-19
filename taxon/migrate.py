"""Standalone migration script for the workspace tables.

Issue #68 introduces three orthogonal tables — ``species_explored``,
``species_folders``, ``link_visited`` — keyed by ``(genus, epithet)``.
Issue #76 (PR A.2) extends the same script with a composite index
migration step: ``ix_taxa_parent_rank_name ON taxa (parent_id, rank, name)``
to accelerate the per-tier recursive CTE used by ``/api/tree/children``.
The project does not use Alembic (none added). Migrations are performed
two ways:

1. The FastAPI lifespan in :mod:`taxon.api` runs ``create_all`` for the
   three new tables at app start. This handles the normal operator case.
2. This script runs ``create_all`` out-of-band for environments where
   the API never boots (CI, fresh-DB smoke tests, manual schema rebuild).

Usage::

    python -m taxon.migrate dry-run                  # print summary, do not mutate
    python -m taxon.migrate apply                    # create tables + ensure indexes
    python -m taxon.migrate apply --only-index       # skip non-index migrations
    python -m taxon.migrate apply --skip-indexes     # skip the index migration step

The script reads ``TAXON_DATABASE_URL`` (default ``sqlite:///./data/taxon.db``)
so the operator can point it at a different DB without code edits.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from taxon.api.workspace import WORKSPACE_TABLES
from taxon.schema import Base

DEFAULT_DATABASE_URL = "sqlite:///./data/taxon.db"

# Composite index added by PR A.2 of #76. The DDL is intentionally
# ``CREATE INDEX IF NOT EXISTS`` so the step is idempotent — a second
# ``apply`` is a no-op when the index already exists. The column list
# matches the per-tier recursive CTE in :mod:`taxon.api._tree_tiers`.
INDEX_DDL: tuple[tuple[str, str], ...] = (
    (
        "ix_taxa_parent_rank_name",
        "CREATE INDEX IF NOT EXISTS ix_taxa_parent_rank_name ON taxa (parent_id, rank, name)",
    ),
)
"""Each entry is ``(index_name, ddl_statement)``. The list is open-ended so
future migrations (PR A.3+) append tuples here without touching the CLI."""


def _resolve_database_url(database_url: str | None) -> str:
    resolved = database_url or os.environ.get("TAXON_DATABASE_URL") or DEFAULT_DATABASE_URL
    if resolved.startswith("sqlite:///") and not resolved.startswith("sqlite:///:memory:"):
        path_part = resolved[len("sqlite:///") :]
        if path_part and path_part != ":memory:":
            Path(path_part).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _missing_tables(engine: Engine, table_names: tuple[str, ...]) -> list[str]:
    """Return the subset of ``table_names`` not present in the engine."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    return [name for name in table_names if name not in existing]


def _existing_index_names(engine: Engine, table: str) -> set[str]:
    """Return the set of index names attached to ``table`` in the engine.

    Returns an empty set when ``table`` is missing so callers can branch
    on the same ``if index_name in _existing_index_names(...)`` pattern
    without a separate existence check.
    """
    inspector = inspect(engine)
    if table not in set(inspector.get_table_names()):
        return set()
    return {name for name in (idx["name"] for idx in inspector.get_indexes(table)) if name}


def _table_columns(engine: Engine, table: str) -> set[str] | None:
    """Return the set of column names on ``table`` or ``None`` when the table is missing.

    A ``None`` return signals "the target table does not exist yet" so
    :func:`_ensure_indexes` can defer the index step until the schema
    migration has produced the full table. This keeps the migration safe
    on pre-existing DBs with a hand-rolled ``taxa`` table that lacks
    some columns the composite index expects.
    """
    inspector = inspect(engine)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def _ensure_indexes(engine: Engine) -> int:
    """Idempotently create every index in :data:`INDEX_DDL`.

    Returns the number of indexes that were actually created on this run
    (zero on a re-run where every index already exists). The DDL uses
    ``CREATE INDEX IF NOT EXISTS`` so concurrent invocations on the same
    engine converge without raising.

    When the target table is missing or lacks one of the indexed columns
    the index is silently skipped (the message still names the table) so
    a pre-existing DB with a hand-rolled ``taxa`` table does not crash
    the migration; the operator can re-run after ``create_all`` brings
    the full schema up.
    """
    created = 0
    with engine.begin() as conn:
        for index_name, ddl in INDEX_DDL:
            target_table = ddl.split(" ON ", 1)[1].split(" ", 1)[0]
            if index_name in _existing_index_names(engine, target_table):
                continue
            columns = _table_columns(engine, target_table)
            if columns is None:
                print(f"[apply-indexes] skipping {index_name}: table {target_table!r} not present")
                continue
            # Extract the column list between the outermost parentheses.
            inner = ddl[ddl.index("(") + 1 : ddl.rindex(")")]
            wanted = {col.strip() for col in inner.split(",")}
            if not wanted.issubset(columns):
                missing = sorted(wanted - columns)
                print(
                    f"[apply-indexes] skipping {index_name}: table {target_table!r} "
                    f"missing columns {', '.join(missing)}"
                )
                continue
            conn.execute(text(ddl))
            created += 1
    if created:
        print(
            f"[apply-indexes] created {created} index(es): {', '.join(name for name, _ in INDEX_DDL)}"
        )
    else:
        print("[apply-indexes] all indexes already present; no changes made")
    return created


def _run_dry_run(engine: Engine, table_names: tuple[str, ...]) -> int:
    missing = _missing_tables(engine, table_names)
    if missing:
        print(
            f"[dry-run] missing tables: {', '.join(missing)} "
            f"(run `python -m taxon.migrate apply` to create them)"
        )
        return 1
    print(f"[dry-run] all {len(table_names)} workspace tables already present")
    return 0


def _run_apply(
    engine: Engine, table_names: tuple[str, ...], *, only_index: bool, skip_indexes: bool
) -> int:
    """Apply the table migration, then the index migration (unless filtered).

    The two CLI flags are mutually exclusive in spirit (``--only-index``
    implies "skip the table step" and ``--skip-indexes`` implies "skip
    the index step") but argparse keeps them orthogonal so an operator
    who passes both is told explicitly.
    """
    if not only_index:
        missing = _missing_tables(engine, table_names)
        if not missing:
            print(
                f"[apply] all {len(table_names)} workspace tables already present; no changes made"
            )
        else:
            Base.metadata.create_all(
                engine, tables=[Base.metadata.tables[name] for name in missing]
            )
            after = _missing_tables(engine, table_names)
            created = [name for name in missing if name not in after]
            print(f"[apply] created {len(created)} table(s): {', '.join(created)}")

    if not skip_indexes:
        _ensure_indexes(engine)
    return 0


def main(argv: list[str] | None = None) -> int:
    # The ``--database-url`` flag is shared by both subcommands. We
    # declare it on a parent parser that each subparser inherits so the
    # operator can pass it either before or after the subcommand
    # (``taxon.migrate --database-url X apply`` OR
    # ``taxon.migrate apply --database-url X``).
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--database-url",
        default=None,
        help="Override TAXON_DATABASE_URL for this run (default: env or sqlite:///./data/taxon.db).",
    )
    parser = argparse.ArgumentParser(
        prog="taxon.migrate",
        description=(
            "Create the three workspace tables (species_explored, species_folders, "
            "link_visited) and ensure the composite taxa indexes against "
            "TAXON_DATABASE_URL without dropping existing data."
        ),
        parents=[parent],
    )
    sub = parser.add_subparsers(dest="mode", metavar="MODE")
    sub.required = True
    sub.add_parser(
        "dry-run",
        help="print a summary without mutating the database",
        parents=[parent],
    )
    apply_parser = sub.add_parser(
        "apply",
        help="create the workspace tables + ensure the composite taxa indexes (idempotent)",
        parents=[parent],
    )
    apply_parser.add_argument(
        "--only-index",
        action="store_true",
        help="Skip the table-creation step and only ensure the composite taxa indexes.",
    )
    apply_parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip the index-ensure step and only run the table-creation migration.",
    )
    args = parser.parse_args(argv)

    database_url = _resolve_database_url(args.database_url)
    engine = create_engine(database_url)

    if args.mode == "dry-run":
        return _run_dry_run(engine, WORKSPACE_TABLES)
    if args.mode == "apply":
        return _run_apply(
            engine,
            WORKSPACE_TABLES,
            only_index=args.only_index,
            skip_indexes=args.skip_indexes,
        )
    parser.error(f"unknown mode: {args.mode}")
    return 2  # unreachable; parser.error exits


if __name__ == "__main__":
    sys.exit(main())
