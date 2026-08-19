"""Rebuild the SQLite taxonomy database from the WoRMS text dump."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, insert, select
from sqlalchemy.orm import Session

from taxon.parser import ParsedTaxon, parse_taxa
from taxon.schema import Base, SpeciesPath, Taxon
from taxon.taxonomy import display_level

DEFAULT_SOURCE = Path("/Users/sebailla/Developer/research/worm/dataset-2011.txt")
DEFAULT_DATABASE = Path("data/taxon.db")
BATCH_SIZE = 1_000
MARKER_KEYS = ("is_synonym", "is_extinct", "is_uncertain", "is_unassigned")
PATH_RANKS = ("kingdom", "phylum", "class", "order", "family", "genus")


@dataclass(frozen=True)
class ImportCounts:
    total_taxa: int = 0
    total_species: int = 0
    synonym: int = 0
    extinct: int = 0
    uncertain: int = 0
    unassigned: int = 0


def import_dataset(
    source_path: Path | str,
    database_path: Path | str = DEFAULT_DATABASE,
    *,
    batch_size: int = BATCH_SIZE,
) -> ImportCounts:
    """Drop, recreate, and stream the complete dataset into SQLite."""
    source = Path(source_path)
    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    engine = _sqlite_engine(database)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    source_to_database_id: dict[str, int] = {}
    batch_source_ids: set[str] = set()
    batch: list[dict[str, Any]] = []
    counts = ImportCounts()
    with source.open(encoding="utf-8", newline="") as lines:
        for parent_source_id, parsed in parse_taxa(lines):
            if parent_source_id in batch_source_ids:
                _insert_taxon_batch(engine, batch, source_to_database_id)
                batch.clear()
                batch_source_ids.clear()
            batch.append(_taxon_row(parsed, parent_source_id, source_to_database_id))
            batch_source_ids.add(parsed["source_id"])
            counts = _increment_counts(counts, parsed)
            if len(batch) >= batch_size:
                _insert_taxon_batch(engine, batch, source_to_database_id)
                batch.clear()
                batch_source_ids.clear()
                if counts.total_taxa % 100_000 == 0:
                    print(f"Imported {counts.total_taxa:,} taxa...", flush=True)
    if batch:
        _insert_taxon_batch(engine, batch, source_to_database_id)

    _populate_species_paths(engine)
    _rebuild_descendant_counts_projection(engine)
    return counts


def _sqlite_engine(database: Path) -> Engine:
    engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _taxon_row(
    parsed: ParsedTaxon,
    parent_source_id: str | None,
    source_to_database_id: dict[str, int],
) -> dict[str, Any]:
    parent_id = source_to_database_id.get(parent_source_id) if parent_source_id else None
    if parent_source_id is not None and parent_id is None:
        raise ValueError(f"Parent {parent_source_id!r} was not imported before its child")
    return {**parsed, "parent_id": parent_id}


def _insert_taxon_batch(
    engine: Engine,
    rows: list[dict[str, Any]],
    source_to_database_id: dict[str, int],
) -> None:
    rows_with_bucket = [{**row, "display_level": display_level(row["rank"])} for row in rows]
    with engine.begin() as connection:
        connection.execute(insert(Taxon), rows_with_bucket)
        source_ids = [row["source_id"] for row in rows_with_bucket]
        inserted = connection.execute(
            select(Taxon.source_id, Taxon.id).where(Taxon.source_id.in_(source_ids))
        )
        source_to_database_id.update(inserted.tuples().all())


def _increment_counts(counts: ImportCounts, parsed: ParsedTaxon) -> ImportCounts:
    return ImportCounts(
        total_taxa=counts.total_taxa + 1,
        total_species=counts.total_species + (parsed["rank"] == "species"),
        synonym=counts.synonym + parsed["is_synonym"],
        extinct=counts.extinct + parsed["is_extinct"],
        uncertain=counts.uncertain + parsed["is_uncertain"],
        unassigned=counts.unassigned + parsed["is_unassigned"],
    )


def _populate_species_paths(engine: Engine) -> None:
    """Project each species row with its breadcrumb path.

    Memory bound: the ``stack`` only holds the chain of currently-open
    ancestors from the current taxon up to the root. Because the taxa are
    visited in autoincrement order (depth-first in the source), each push is
    followed by exactly one pop, so the stack size is bounded by the deepest
    rank chain in the dataset (around thirty ranks in WoRMS), independent of
    the total taxon count. The previous implementation kept a full
    ``ancestors`` dict of every taxon ever visited, which grew linearly with
    the input size.
    """
    stack: list[tuple[int, tuple[dict[str, str], dict[str, bool]]]] = []
    paths: list[dict[str, Any]] = []
    with Session(engine) as session:
        taxa = session.scalars(select(Taxon).order_by(Taxon.id)).yield_per(BATCH_SIZE)
        for taxon in taxa:
            while stack and stack[-1][0] != taxon.parent_id:
                stack.pop()
            if taxon.parent_id is None:
                if stack:
                    raise ValueError(
                        f"Root-level taxon {taxon.id} found after non-empty ancestor stack"
                    )
                inherited_path: dict[str, str] = {}
                inherited_markers = {key: False for key in MARKER_KEYS}
            else:
                if not stack:
                    raise ValueError(f"Missing imported parent ID {taxon.parent_id}")
                inherited_path = stack[-1][1][0].copy()
                inherited_markers = stack[-1][1][1].copy()

            rank_key = "class" if taxon.rank == "class" else taxon.rank
            if rank_key in PATH_RANKS:
                inherited_path[rank_key] = taxon.name
            for key in MARKER_KEYS:
                inherited_markers[key] = inherited_markers[key] or bool(getattr(taxon, key))
            stack.append((taxon.id, (inherited_path, inherited_markers)))

            if taxon.rank == "species":
                paths.append(
                    {
                        "species_id": taxon.source_id,
                        "kingdom": inherited_path.get("kingdom"),
                        "phylum": inherited_path.get("phylum"),
                        "class_name": inherited_path.get("class"),
                        "order": inherited_path.get("order"),
                        "family": inherited_path.get("family"),
                        "genus": inherited_path.get("genus"),
                        "species": taxon.name,
                        "display_name": taxon.display_name,
                        **inherited_markers,
                    }
                )
                if len(paths) >= BATCH_SIZE:
                    session.execute(insert(SpeciesPath), paths)
                    session.commit()
                    paths.clear()
        if paths:
            session.execute(insert(SpeciesPath), paths)
            session.commit()


def _rebuild_descendant_counts_projection(engine: Engine) -> None:
    """Recompute ``taxon_descendant_counts`` after a full re-import.

    The descendant-counts-projection change requires the projection
    table to be re-populated whenever the underlying ``taxa`` table
    is rebuilt — a fresh CoL re-import drops every taxon row, so any
    cached projection rows would point at FK ids that no longer
    exist. The rebuild runs at the very end of :func:`import_dataset`
    so the table is fresh on the next boot.

    Wires :func:`taxon.api.projections.register_display_level` so
    the recursive CTE works on the import-data engine (it builds a
    bare engine with only ``PRAGMA foreign_keys=ON``). The import
    is an offline caller, so ``budget_seconds=None`` disables the
    SLO guard.
    """
    from sqlalchemy.orm import sessionmaker

    from taxon.api.projections import (
        PROJECTION_TABLES,
        materialize_all,
        register_display_level,
    )

    register_display_level(engine)
    # Idempotent ``create_all`` so the projection table exists even on
    # a fresh DB that has not run ``python -m taxon.migrate apply``.
    table_objs = [Base.metadata.tables[name] for name in PROJECTION_TABLES]
    Base.metadata.create_all(engine, tables=table_objs)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        written = materialize_all(session, budget_seconds=None)
    print(f"Rebuilt descendant-counts projection: {written} row(s)")


def _print_counts(counts: ImportCounts, database: Path) -> None:
    print(f"Database: {database}")
    print(f"Total taxa: {counts.total_taxa}")
    print(f"Total species: {counts.total_species}")
    print(f"Synonym: {counts.synonym}")
    print(f"Extinct: {counts.extinct}")
    print(f"Uncertain: {counts.uncertain}")
    print(f"Unassigned: {counts.unassigned}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path(os.environ.get("TAXON_DATASET", DEFAULT_SOURCE)),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("TAXON_DATABASE", DEFAULT_DATABASE)),
    )
    args = parser.parse_args()
    counts = import_dataset(args.source, args.database)
    _print_counts(counts, args.database)


if __name__ == "__main__":
    main()
