"""CoL DwC-A import path: parser → SQLite.

Mirrors the WoRMS import in ``taxon/import_data.py`` but adapted
to CoL's TSV schema and unordered rows. Three-pass strategy:

1. **Insert pass.** Stream the TSV, parse each row, batch-insert
   into ``Taxon`` with ``parent_id = NULL``. CoL rows arrive out
   of depth-first order so the parent may not yet be in the
   database when its child arrives. We disable FKs at the engine
   level for the duration of the import and re-enable them at
   the end (the app reads the DB without writes so this is safe).

   While reading, the importer keeps an in-memory
   ``parent_source_id_by_child_source_id`` dict so the second
   pass can wire parents without re-streaming the file.

   Each row also carries its ``display_level`` bucket (see
   :mod:`taxon.taxonomy`) so the cascade UI can filter without
   re-mapping every rank at query time.

2. **Parent-wiring pass.** Single ``UPDATE taxa SET parent_id = ...``
   statement per distinct parent, batched across every child
   that points to it. The parent IDs come from a ``source_id →
   database_id`` map the first pass already populated.

3. **Species-path pass.** For every row whose rank is species (or
   any infraspecific rank), insert a ``SpeciesPath`` row using
   the rank-resolved columns ``col:kingdom`` (65), ``col:phylum``
   (64), ``col:class`` (62), ``col:order`` (60), ``col:family``
   (57), ``col:genus`` (53), and the binomen from
   ``col:scientificName`` + ``col:authorship``. CoL populates
   those columns per-row, so no recursive walk is needed.

The marker flags are persisted in the same Taxon rows during
the insert pass — the parser sets them, the schema has columns
for them, and the SQLite default is False so unspecified rows
just stay False.

Use this module directly:

    from taxon.col_import import import_col_dataset
    counts = import_col_dataset("path/to/NameUsage.tsv", "data/taxon.db")
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, insert, select, update

from taxon.col_parser import parse_col_taxa
from taxon.parser import ParsedTaxon
from taxon.schema import Base, SpeciesPath, Taxon
from taxon.taxonomy import display_level

DEFAULT_SOURCE = Path(
    os.environ.get(
        "TAXON_COL_DATASET",
        "/Users/sebailla/Developer/research/e8ce17c8-47c4-4b10-8316-7b699472c3b1/NameUsage.tsv",
    )
)
DEFAULT_DATABASE = Path("data/taxon.db")
BATCH_SIZE = 1_000

# CoL's ``col:rank`` values that should produce a SpeciesPath row.
# Infraspecific ranks share the species path because the cascade
# UI only drills down to species.
_SPECIES_RANKS = frozenset(
    {
        "species",
        "subspecies",
        "variety",
        "subvariety",
        "form",
        "subform",
    }
)

# Species-path column ordinals (0-indexed) in the CoL TSV.
# Hard-coded because they are fixed by the CoL DwC-A schema.
_COL_KINGDOM = 64
_COL_PHYLUM = 63
_COL_CLASS = 61
_COL_ORDER = 59
_COL_FAMILY = 56
_COL_GENUS = 52
_COL_RANK = 9
_COL_STATUS = 6
_COL_SCIENTIFIC_NAME = 7
_COL_AUTHORSHIP = 8
_COL_EXTINCT = 45
_COL_ID = 0


@dataclass(frozen=True)
class ColImportCounts:
    total_taxa: int = 0
    total_species: int = 0
    synonym: int = 0
    extinct: int = 0
    uncertain: int = 0
    unassigned: int = 0


def import_col_dataset(
    source_path: Path | str,
    database_path: Path | str = DEFAULT_DATABASE,
    *,
    batch_size: int = BATCH_SIZE,
) -> ColImportCounts:
    """Drop, recreate, and stream the CoL archive into SQLite."""
    source = Path(source_path)
    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    engine = _sqlite_engine(database)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    source_to_database_id, parent_source_by_child, counts = _insert_pass(engine, source, batch_size)
    _wire_parents(engine, source_to_database_id, parent_source_by_child)
    _populate_species_paths(engine, source)
    return counts


def _sqlite_engine(database: Path) -> Engine:
    engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def toggle_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    return engine


def _insert_pass(
    engine: Engine,
    source: Path,
    batch_size: int,
) -> tuple[dict[str, int], dict[str, str], ColImportCounts]:
    """First pass: insert every Taxon row with parent_id = NULL.

    The CoL rows arrive out of depth-first order, so we cannot
    wire up parents in-line. We disable FKs on the engine (see
    ``_sqlite_engine``) until the second pass re-enables them.

    Side effects: builds two in-memory maps for later passes:

    - ``source_to_database_id``: every CoL source_id we inserted,
      mapped to its autoincrement ``Taxon.id``.
    - ``parent_source_by_child``: every child source_id we
      inserted, mapped to its parent source_id. Used by
      ``_wire_parents`` to build the ``UPDATE`` without
      re-streaming the source file.

    Memory bound: at ~7.87M rows the parent map holds roughly
    100 MB (12 bytes per entry × 7.87M). The source_to_id map is
    similar. Both fit comfortably in modern RAM. If the dataset
    grows past ~50M rows, switch to a two-file approach (write
    the parent edges to disk and read them back in pass 2).
    """
    source_to_database_id: dict[str, int] = {}
    parent_source_by_child: dict[str, str] = {}
    batch: list[dict[str, Any]] = []
    counts = ColImportCounts()
    with source.open(encoding="utf-8", newline="") as lines:
        for parent_source_id, parsed in parse_col_taxa(lines):
            if parent_source_id is not None:
                parent_source_by_child[parsed["source_id"]] = parent_source_id
            # ``ParsedTaxon`` is a TypedDict; cast to plain dict so
            # mypy accepts the insertion into ``batch: list[dict[str, Any]]``.
            batch.append(dict(parsed))
            counts = _increment_counts(counts, parsed)
            if len(batch) >= batch_size:
                _flush_taxon_batch(engine, batch, source_to_database_id)
                batch.clear()
                if counts.total_taxa % 100_000 == 0:
                    print(f"Imported {counts.total_taxa:,} taxa...", flush=True)
    if batch:
        _flush_taxon_batch(engine, batch, source_to_database_id)
    return source_to_database_id, parent_source_by_child, counts


def _flush_taxon_batch(
    engine: Engine,
    rows: list[dict[str, Any]],
    source_to_database_id: dict[str, int],
) -> None:
    rows_with_null_parent = [
        {
            **row,
            "parent_id": None,
            # populate the cascade bucket at insert time so the
            # resolver does not have to map rank -> bucket at query
            # time. ``display_level`` is a pure function of the
            # rank; ``None`` lands as ``NULL`` in the column.
            "display_level": display_level(row["rank"]),
        }
        for row in rows
    ]
    with engine.begin() as connection:
        connection.execute(insert(Taxon), rows_with_null_parent)
        source_ids = [row["source_id"] for row in rows_with_null_parent]
        inserted = connection.execute(
            select(Taxon.source_id, Taxon.id).where(Taxon.source_id.in_(source_ids))
        )
        source_to_database_id.update(inserted.tuples().all())


def _wire_parents(
    engine: Engine,
    source_to_database_id: dict[str, int],
    parent_source_by_child: dict[str, str],
) -> None:
    """Second pass: UPDATE parent_id for every Taxon row whose parent
    source_id is known.

    CoL's top of the tree (``Biota``) is the implicit superdomain
    and may not be in the imported subset; rows whose parent is
    unknown are left with ``parent_id = NULL`` — those are the
    roots of the imported forest.

    Per-parent batching keeps the number of ``UPDATE`` statements
    small (one per distinct parent source_id) while letting
    SQLite update many rows per statement.
    """
    children_by_parent: dict[str, list[str]] = {}
    for child_source_id, parent_source_id in parent_source_by_child.items():
        if parent_source_id in source_to_database_id:
            children_by_parent.setdefault(parent_source_id, []).append(child_source_id)
    with engine.begin() as connection:
        for parent_source_id, child_source_ids in children_by_parent.items():
            parent_id = source_to_database_id[parent_source_id]
            connection.execute(
                update(Taxon)
                .where(Taxon.source_id.in_(child_source_ids))
                .values(parent_id=parent_id)
            )


def _populate_species_paths(engine: Engine, source: Path) -> None:
    """Third pass: build SpeciesPath rows using CoL's resolved columns.

    CoL pre-resolves each row's kingdom → genus in its own
    columns (50, 53, 57, 60, 62, 64, 65), so the breadcrumb is
    per-row rather than reconstructed from a walk. Infraspecific
    ranks also map to SpeciesPath so the cascade UI can show the
    variety/form under a species (the species name used in the
    display column is the binomen from ``col:scientificName``;
    the infraspecific epithet is not surfaced yet — a future PR
    can extend ``SpeciesPath`` with a ``subspecies`` column).
    """
    paths: list[dict[str, Any]] = []
    with source.open(encoding="utf-8", newline="") as lines:
        next(lines)  # header
        for raw_line in lines:
            if not raw_line.strip():
                continue
            cells = raw_line.rstrip("\r\n").split("\t")
            row = _extract_species_path_row(cells)
            if row is None:
                continue
            paths.append(row)
            if len(paths) >= BATCH_SIZE:
                _flush_species_paths(engine, paths)
                paths.clear()
    if paths:
        _flush_species_paths(engine, paths)


def _extract_species_path_row(cells: list[str]) -> dict[str, Any] | None:
    rank = cells[_COL_RANK]
    if rank not in _SPECIES_RANKS:
        return None
    species_name = cells[_COL_SCIENTIFIC_NAME]
    if not species_name:
        return None
    genus = cells[_COL_GENUS]
    kingdom = cells[_COL_KINGDOM]
    phylum = cells[_COL_PHYLUM]
    class_name = cells[_COL_CLASS]
    order = cells[_COL_ORDER]
    family = cells[_COL_FAMILY]
    status = cells[_COL_STATUS]
    extinct = cells[_COL_EXTINCT].strip().lower() == "true"
    authorship = cells[_COL_AUTHORSHIP]
    display_name = f"{species_name} {authorship}".strip() if authorship else species_name
    return {
        "species_id": cells[_COL_ID],
        "kingdom": kingdom or None,
        "phylum": phylum or None,
        "class_name": class_name or None,
        "order": order or None,
        "family": family or None,
        "genus": genus or None,
        "species": species_name,
        "display_name": display_name,
        "is_synonym": status in {"synonym", "ambiguous synonym", "misapplied"},
        "is_extinct": extinct,
        "is_uncertain": status == "provisionally accepted",
        "is_unassigned": rank == "unranked",
    }


def _flush_species_paths(engine: Engine, paths: list[dict[str, Any]]) -> None:
    with engine.begin() as connection:
        connection.execute(insert(SpeciesPath), paths)


def _increment_counts(counts: ColImportCounts, parsed: ParsedTaxon) -> ColImportCounts:
    return ColImportCounts(
        total_taxa=counts.total_taxa + 1,
        total_species=counts.total_species + (parsed["rank"] in _SPECIES_RANKS),
        synonym=counts.synonym + parsed["is_synonym"],
        extinct=counts.extinct + parsed["is_extinct"],
        uncertain=counts.uncertain + parsed["is_uncertain"],
        unassigned=counts.unassigned + parsed["is_unassigned"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("TAXON_DATABASE", DEFAULT_DATABASE)),
    )
    args = parser.parse_args()
    counts = import_col_dataset(args.source, args.database)
    print(f"Database: {args.database}")
    print(f"Total taxa: {counts.total_taxa}")
    print(f"Total species: {counts.total_species}")
    print(f"Synonym: {counts.synonym}")
    print(f"Extinct: {counts.extinct}")
    print(f"Uncertain: {counts.uncertain}")
    print(f"Unassigned: {counts.unassigned}")


if __name__ == "__main__":
    main()
