"""Standalone migration script for the workspace tables.

Issue #68 introduces three orthogonal tables — ``species_explored``,
``species_folders``, ``link_visited`` — keyed by ``(genus, epithet)``.
The project does not use Alembic (none added). Migrations are performed
two ways:

1. The FastAPI lifespan in :mod:`taxon.api` runs ``create_all`` for the
   three new tables at app start. This handles the normal operator case.
2. This script runs ``create_all`` out-of-band for environments where
   the API never boots (CI, fresh-DB smoke tests, manual schema rebuild).

Usage::

    python -m taxon.migrate dry-run   # print summary, do not mutate
    python -m taxon.migrate apply     # create the three new tables

The script reads ``TAXON_DATABASE_URL`` (default ``sqlite:///./data/taxon.db``)
so the operator can point it at a different DB without code edits.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from taxon.api.workspace import WORKSPACE_TABLES
from taxon.schema import Base

DEFAULT_DATABASE_URL = "sqlite:///./data/taxon.db"


def _resolve_database_url(database_url: str | None) -> str:
    resolved = database_url or os.environ.get("TAXON_DATABASE_URL") or DEFAULT_DATABASE_URL
    if resolved.startswith("sqlite:///") and not resolved.startswith("sqlite:///:memory:"):
        path_part = resolved[len("sqlite:///") :]
        if path_part and path_part != ":memory:":
            Path(path_part).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _missing_tables(engine, table_names: tuple[str, ...]) -> list[str]:
    """Return the subset of ``table_names`` not present in the engine."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    return [name for name in table_names if name not in existing]


def _run_dry_run(engine, table_names: tuple[str, ...]) -> int:
    missing = _missing_tables(engine, table_names)
    if missing:
        print(
            f"[dry-run] missing tables: {', '.join(missing)} "
            f"(run `python -m taxon.migrate apply` to create them)"
        )
        return 1
    print(f"[dry-run] all {len(table_names)} workspace tables already present")
    return 0


def _run_apply(engine, table_names: tuple[str, ...]) -> int:
    missing = _missing_tables(engine, table_names)
    if not missing:
        print(f"[apply] all {len(table_names)} workspace tables already present; no changes made")
        return 0
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in missing])
    after = _missing_tables(engine, table_names)
    created = [name for name in missing if name not in after]
    print(f"[apply] created {len(created)} table(s): {', '.join(created)}")
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
            "link_visited) against TAXON_DATABASE_URL without dropping existing data."
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
    sub.add_parser(
        "apply",
        help="create the workspace tables (idempotent)",
        parents=[parent],
    )
    args = parser.parse_args(argv)

    database_url = _resolve_database_url(args.database_url)
    engine = create_engine(database_url)

    if args.mode == "dry-run":
        return _run_dry_run(engine, WORKSPACE_TABLES)
    if args.mode == "apply":
        return _run_apply(engine, WORKSPACE_TABLES)
    parser.error(f"unknown mode: {args.mode}")
    return 2  # unreachable; parser.error exits


if __name__ == "__main__":
    sys.exit(main())
