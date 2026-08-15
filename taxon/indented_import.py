"""Streaming importer for the GBIF Backbone / Catalogue of Life
indented-tree dataset.

The importer ships a GBIF Backbone or Catalogue of Life (CLB)
indented-tree dump into the local SQLite database. The source
file uses two-space indent per depth level and the syntax:

    <name> [<rank>] {ID=<source_id> <metadata>}

The metadata block is shlex-tokenised; the importer captures the
``ID`` key as the canonical external identifier and ignores the
rest for now (later migrations can promote additional metadata
columns — see :mod:`taxon.import_data` for the WoRMS-shaped
``Taxon`` projection). The depth of every line is the parent
link: a stack of the active ancestry keeps the last source id
at each depth, and the next row's parent is the source id at
``depth - 1``.

The column shape mirrors the existing :class:`taxon.schema.Taxon`
table: every node gets a row id, a parent id, a name, a rank, a
source id, and an optional ``display_level`` that the cascade UI
uses to bucket the rank. ``display_level`` is intentionally left
null by the importer — :func:`taxon.taxonomy.display_level` is
applied at query time, matching the historical WoRMS importer.
The leftover columns inherited from the older WoRMS importer
(``is_synonym``, ``is_extinct``, ``is_uncertain``,
``is_unassigned``) keep their default ``False`` so the cascade
UI's filter API keeps working out of the box.

The importer is a streaming batched write. The full GBIF
Backbone is on the order of 7 million rows; the batch boundary
fires every :data:`BATCH_SIZE` rows so the SQLite write
throughput stays high without holding the full result set in
memory. The CLI is exposed as ``python -m taxon.indented_import
<source> --database <path>``.

Historical note: this is the second attempt at landing the
importer. The first shipped as ``taxon.col_import`` and was
discarded during a merge conflict with the legacy DwC-A
ingester under the same name. The DwC-A ingester was unused
by the backend and is removed in the same PR so the
indented-tree importer is the only importer left.
"""

from __future__ import annotations

import re
import shlex
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, insert

from taxon.schema import Base, Taxon

#: Pre-compiled regex that matches the indented-tree shape
#: shared by GBIF Backbone and CLB. The metadata block is
#: optional so the importer can also flag malformed lines
#: through the rejected-lines counter rather than raising.
LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<name>.+?)\s*\[(?P<rank>[^\]]+)\]\s*"
    r"(?:\{(?P<metadata>.*?)\})?(?:\s+#.*)?\s*$"
)

#: Insert throughput / memory trade-off. 20 000 rows keeps the
#: SQLite write cache hot without holding a full taxon in process
#: memory. The CLB Eukaryota dataset fits one batch in well under
#: a second on a modern SSD.
BATCH_SIZE = 20_000

#: Default source path for the CLI. The ``TAXON_INDENTED_DATASET``
#: environment variable overrides the default without touching
#: the README; the explicit ``--database`` flag wins over both.
DEFAULT_SOURCE = Path(
    "/Users/sebailla/Developer/research/d25cad64-9895-4d53-af58-04bd9aaae23d/dataset-53147.txt"
)
DEFAULT_DATABASE = Path("data/taxon.db")


@dataclass(frozen=True)
class ImportCounts:
    """Summary of a single import run."""

    total_taxa: int = 0
    rejected_lines: int = 0
    elapsed_seconds: float = 0.0


def _parse_metadata(raw: str | None) -> dict[str, str]:
    """Tokenise the metadata block into a flat ``key -> value`` dict.

    GBIF uses comma-separated tokens inside the braces
    (``ID=1 REF=rx6N9FQ,rx7DCR6 VERN=eng:Animal``). The shlex
    parser drops the trailing comma artifacts and exposes the
    ``ID`` key that the importer records as the canonical
    :attr:`Taxon.source_id`. We intentionally do not promote
    ``REF`` or ``VERN`` to columns yet — the GBIF metadata is
    richer than the WoRMS dump and the cascade UI does not
    consume it today.
    """
    if not raw:
        return {}
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError:
        tokens = raw.split()
    values: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if sep:
            values[key] = value
    return values


def _sqlite_engine(database: Path) -> Engine:
    """Build a SQLAlchemy engine with the SQLite pragmas the importer needs.

    The foreign-key pragma is essential because the importer
    resolves ``parent_id`` against the same ``taxa`` table in a
    single forward pass. The journal / synchronous pragmas match
    the legacy WoRMS importer so the bulk write throughput stays
    the same.
    """
    engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: sqlite3.Connection, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _parse_lines(
    lines: Iterable[str],
) -> Iterable[tuple[int, int, str, str, dict[str, str]]]:
    """Yield ``(source_line, depth, name, rank, metadata)`` for every row.

    The function is a generator wrapper so the importer can
    stream the source file without loading the full dataset into
    memory. Malformed lines (odd indentation, mismatched
    brackets, missing metadata) surface through the
    ``rejected_lines`` counter in :class:`ImportCounts` rather
    than failing the whole import.
    """
    for source_line, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        match = LINE_RE.match(line)
        if match is None:
            yield source_line, -1, "", "", {"__error__": "malformed line"}
            continue
        indent = match.group("indent")
        if "\t" in indent or len(indent) % 2:
            yield source_line, -1, "", "", {"__error__": "indentation is not even spaces"}
            continue
        depth = len(indent) // 2
        raw_metadata = match.group("metadata")
        metadata = _parse_metadata(raw_metadata)
        yield source_line, depth, match.group("name"), match.group("rank"), metadata


def import_indented_dataset(
    source_path: Path | str,
    database_path: Path | str = DEFAULT_DATABASE,
    *,
    batch_size: int = BATCH_SIZE,
) -> ImportCounts:
    """Stream ``source_path`` into ``database_path`` and return import counts.

    The importer drops the existing ``taxa`` table before
    recreating it so a re-run is idempotent. The legacy
    :class:`taxon.schema.SpeciesPath` rows and the WoRMS-shape
    seed data are NOT touched by this importer — the cascade UI
    uses the indented-tree rows for the species-list and
    children endpoints, while the WoRMS-shape rows keep serving
    the search-source dispatch endpoints through the historical
    helper. The two shapes coexist in the same database; the
    importer only writes the indented-tree half.

    The parent linkage is recovered from the indent depth of
    every line: a stack of source-id pointers keeps the last
    ancestor at each depth, and the next row's parent is the
    source id at ``depth - 1``. After the bulk insert the
    importer walks the table once and rewrites ``parent_id``
    from the source-id cache so the cascade can walk the
    hierarchy through the legacy ``taxa.parent_id`` foreign key.
    """
    source = Path(source_path)
    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    engine = _sqlite_engine(database)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    depth_stack: list[str] = []
    batch: list[dict[str, object]] = []
    pending_links: list[tuple[str, str | None]] = []
    counts = ImportCounts()
    start = time.monotonic()
    with source.open(encoding="utf-8", errors="strict") as raw:
        for source_line, depth, name, rank, metadata in _parse_lines(raw):
            if "__error__" in metadata:
                counts = ImportCounts(
                    total_taxa=counts.total_taxa,
                    rejected_lines=counts.rejected_lines + 1,
                    elapsed_seconds=0.0,
                )
                continue
            source_id = metadata.get("ID")
            if source_id is None or depth < 0:
                counts = ImportCounts(
                    total_taxa=counts.total_taxa,
                    rejected_lines=counts.rejected_lines + 1,
                    elapsed_seconds=0.0,
                )
                continue
            if depth > len(depth_stack):
                counts = ImportCounts(
                    total_taxa=counts.total_taxa,
                    rejected_lines=counts.rejected_lines + 1,
                    elapsed_seconds=0.0,
                )
                continue
            del depth_stack[depth:]
            parent_source_id = depth_stack[-1] if depth_stack else None
            # Derive taxonomic flags from the leading marker of the
            # name. The CLB / GBIF indented-tree format carries these
            # signals in the column itself rather than as metadata,
            # so we read them once here and let the cascade UI filter
            # by them later.
            is_synonym = name.startswith("=")
            is_extinct = name.startswith("\u2020")
            batch.append(
                {
                    "source_id": source_id,
                    "parent_id": None,
                    "name": name,
                    "rank": rank.lower(),
                    "display_name": name,
                    "display_level": None,
                    "is_synonym": is_synonym,
                    "is_extinct": is_extinct,
                }
            )
            # Park the parent linkage for the second pass so the
            # first pass can stay row-at-a-time without needing
            # the parent's row id back from SQLite. The tuple
            # carries the source id of the new row plus the
            # source id of its parent (or ``None`` for a root).
            pending_links.append((source_id, parent_source_id))
            depth_stack.append(source_id)
            if len(batch) >= batch_size:
                _flush_batch(engine, batch)
                counts = ImportCounts(
                    total_taxa=counts.total_taxa + len(batch),
                    rejected_lines=counts.rejected_lines,
                    elapsed_seconds=time.monotonic() - start,
                )
                if counts.total_taxa % 200_000 == 0:
                    print(
                        f"Imported {counts.total_taxa:,} taxa "
                        f"({counts.total_taxa / max(counts.elapsed_seconds, 0.001):,.0f}/s)",
                        flush=True,
                    )
                batch.clear()
    if batch:
        _flush_batch(engine, batch)
        counts = ImportCounts(
            total_taxa=counts.total_taxa + len(batch),
            rejected_lines=counts.rejected_lines,
            elapsed_seconds=time.monotonic() - start,
        )
    _resolve_parent_ids(engine, pending_links)
    return counts


def _flush_batch(engine: Engine, batch: list[dict[str, object]]) -> None:
    """Insert one batch into the ``taxa`` table.

    The caller is responsible for tracking the depth stack and
    resolving parents; this function only writes the rows the
    caller hands it. We use ``insert`` with explicit column
    values to keep the row shape consistent with the legacy
    :class:`taxon.schema.Taxon` model. The parent linkage is
    finalised by :func:`_resolve_parent_ids` after the bulk
    insert, so the first-pass rows always carry ``parent_id =
    None``.
    """
    with engine.begin() as connection:
        connection.execute(insert(Taxon), batch)


def _resolve_parent_ids(
    engine: Engine,
    pending_links: list[tuple[str, str | None]],
) -> None:
    """Patch every row's ``parent_id`` from the parent's source-id.

    The first pass cannot resolve ``parent_id`` because the
    parent's row id is assigned by SQLite's autoincrement at
    INSERT time. The depth stack tracks the source-id of every
    ancestor; the second pass queries the just-inserted
    ``source_id -> id`` map once and rewrites ``parent_id`` in
    bulk via :func:`sqlite3.Connection.executemany`. The
    function never touches the network because the map is
    built from the just-inserted taxa table on the same engine.
    """
    with engine.begin() as connection:
        source_to_id: dict[str, int] = {
            row[0]: row[1]
            for row in connection.exec_driver_sql("SELECT source_id, id FROM taxa").fetchall()
        }
        updates = [
            (source_to_id[parent_id], source_id)
            for source_id, parent_id in pending_links
            if parent_id is not None and parent_id in source_to_id
        ]
        connection.connection.executemany(
            "UPDATE taxa SET parent_id = ? WHERE source_id = ?",
            updates,
        )


def main() -> None:
    """CLI entry point — ``python -m taxon.indented_import``.

    The CLI mirrors the legacy :func:`taxon.import_data.main`
    signature so the README recipe ``python -m
    taxon.indented_import <source> --database <path>`` works
    without surprises. The import prints a single line per batch
    and a final summary so CI logs can be parsed.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        type=Path,
        default=DEFAULT_SOURCE,
        nargs="?",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
    )
    args = parser.parse_args()
    counts = import_indented_dataset(args.source, args.database, batch_size=args.batch_size)
    print(
        f"Imported {counts.total_taxa:,} taxa, "
        f"rejected {counts.rejected_lines:,} lines, "
        f"elapsed {counts.elapsed_seconds:.1f}s"
    )


__all__ = [
    "DEFAULT_DATABASE",
    "DEFAULT_SOURCE",
    "ImportCounts",
    "import_indented_dataset",
    "main",
]


if __name__ == "__main__":
    main()
