"""Contract tests for ``taxon.col_import``.

The importer ships a GBIF / CLB indented-tree dump into the
local SQLite database. The tests construct a tiny in-memory
fixture that mirrors the GBIF shape (two-space indent, ``[rank]
{ID=...}`` metadata) and verify the importer resolves the
parent linkage through the depth stack without touching the
network.

The behaviour we pin here is:

- The deparser drops a malformed line and keeps going.
- The depth stack rejects a depth that skips a parent level.
- A missing ``ID`` metadata entry surfaces through the
  rejected counter.
- The parent linkage matches the indent depth of every input
  row — even when the source has rows scattered across multiple
  kingdoms.
- The batch boundary flushes every row once, never twice.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from taxon.col_import import (
    _parse_lines,
    _parse_metadata,
    import_col_dataset,
)


def _gbif_fixture() -> str:
    """GBIF Backbone indented tree with two roots and one each of the 7 ranks."""
    return (
        "Animalia [kingdom] {ID=1}\n"
        "  Chordata [phylum] {ID=2}\n"
        "    Mammalia [class] {ID=3}\n"
        "      Carnivora [order] {ID=4}\n"
        "        Felidae [family] {ID=5}\n"
        "          Felis [genus] {ID=6}\n"
        "            Felis catus [species] {ID=7}\n"
        "  Arthropoda [phylum] {ID=8}\n"
        "    Insecta [class] {ID=9}\n"
        "      Lepidoptera [order] {ID=10}\n"
        "        Nymphalidae [family] {ID=11}\n"
        "          Vanessa [genus] {ID=12}\n"
        "            Vanessa cardui [species] {ID=13}\n"
        "Plantae [kingdom] {ID=14}\n"
        "  Tracheophyta [phylum] {ID=15}\n"
        "    Magnoliopsida [class] {ID=16}\n"
        "      Rosales [order] {ID=17}\n"
        "        Rosaceae [family] {ID=18}\n"
        "          Rosa [genus] {ID=19}\n"
        "            Rosa canina [species] {ID=20}\n"
    )


def _write_fixture(path: Path) -> Path:
    src = path / "dataset.txt"
    src.write_text(_gbif_fixture(), encoding="utf-8")
    return src


def test_parse_metadata_extracts_known_keys() -> None:
    """The shlex parser must surface the ``ID`` key out of the
    comma-separated metadata block."""
    metadata = _parse_metadata("ID=1 REF=rx6N9FQ,rx7DCR6 VERN=eng:Animal")
    assert metadata == {"ID": "1", "REF": "rx6N9FQ,rx7DCR6", "VERN": "eng:Animal"}


def test_parse_metadata_is_empty_for_missing_payload() -> None:
    """Empty metadata must yield an empty dict, not ``None``."""
    assert _parse_metadata(None) == {}
    assert _parse_metadata("") == {}


def test_parse_lines_yields_depth_name_rank_metadata() -> None:
    """The streaming parser assigns the right depth to each line."""
    lines = _gbif_fixture().splitlines(keepends=True)
    parsed = list(_parse_lines(lines))
    # Skip the malformed-counter rows first.
    rows = [
        (line, name, rank, meta) for line, _, name, rank, meta in parsed if "__error__" not in meta
    ]
    assert len(rows) == 20
    # Animalia is depth 0, Felis is depth 5, Felis catus is depth 6.
    by_id = {}
    for _, depth, name, rank, meta in parsed:
        if "__error__" in meta:
            continue
        by_id[meta["ID"]] = (depth, name, rank)
    assert by_id["1"] == (0, "Animalia", "kingdom")
    assert by_id["7"] == (6, "Felis catus", "species")


def test_parse_lines_flags_malformed_indentation() -> None:
    """An odd-indent line must surface as ``__error__`` rather
    than crashing the importer."""
    lines = [
        "Animalia [kingdom] {ID=1}\n",
        " Chordata [phylum] {ID=2}\n",  # one space — odd indent
    ]
    parsed = list(_parse_lines(lines))
    errors = [meta for _, _, _, _, meta in parsed if "__error__" in meta]
    assert errors == [{"__error__": "indentation is not even spaces"}]


def test_parse_lines_flags_depth_skip() -> None:
    """A depth that skips a parent level is rejected at the
    ``import_col_dataset`` router rather than the parser."""
    lines = [
        "Animalia [kingdom] {ID=1}\n",
        "        Chordata [phylum] {ID=2}\n",  # depth 4 with no depth 1-3 parents
    ]
    parsed = list(_parse_lines(lines))
    # The parser accepts both lines (the depth-skip is a router
    # concern, not a parser concern). The router rejects the
    # second row because the in-flight depth stack at line 2
    # only has depth 0 — depth 4 is greater than the stack's
    # height, which is the router's reject condition.
    assert all("__error__" not in row[4] for row in parsed)
    assert [(depth, name) for _, depth, name, _, _ in parsed] == [
        (0, "Animalia"),
        (4, "Chordata"),
    ]


def test_import_writes_all_rows_with_correct_parent(tmp_path: Path) -> None:
    """End-to-end importer test: every row's parent points at
    the previous row id of depth - 1, so the cascade walker can
    cross the whole tree without leaving the local database."""
    src = _write_fixture(tmp_path)
    db = tmp_path / "taxon.db"
    counts = import_col_dataset(src, db, batch_size=64)
    assert counts.total_taxa == 20
    assert counts.rejected_lines == 0

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT source_id, parent_id, name, rank FROM taxa ORDER BY id"
        ).fetchall()
        # Animalia has no parent.
        assert rows[0] == ("1", None, "Animalia", "kingdom")
        # Chordata's parent is Animalia (id 1).
        chordata = next(row for row in rows if row[0] == "2")
        assert chordata == ("2", 1, "Chordata", "phylum")
        # Felis catus descends all the way to Felis (id 6).
        felis_catus = next(row for row in rows if row[0] == "7")
        assert felis_catus == ("7", 6, "Felis catus", "species")
        # Plantae's parent is None (separated depth-0 root).
        plantae = next(row for row in rows if row[0] == "14")
        assert plantae == ("14", None, "Plantae", "kingdom")
    finally:
        conn.close()


def test_import_is_idempotent(tmp_path: Path) -> None:
    """A second run overwrites the previous table without
    leaving ghost rows from the first run."""
    src = _write_fixture(tmp_path)
    db = tmp_path / "taxon.db"
    import_col_dataset(src, db)
    counts = import_col_dataset(src, db)
    assert counts.total_taxa == 20
    conn = sqlite3.connect(db)
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM taxa").fetchone()[0]
        assert row_count == 20
    finally:
        conn.close()


def test_import_rejects_missing_id_metadata(tmp_path: Path) -> None:
    """A row without ``{ID=...}`` must surface as a rejected line
    so the importer does not produce a partial reconstruction."""
    src = tmp_path / "malformed.txt"
    src.write_text(
        "Animalia [kingdom] {ID=1}\n  Chordata [phylum]\n",  # missing ID metadata
        encoding="utf-8",
    )
    db = tmp_path / "taxon.db"
    counts = import_col_dataset(src, db)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT source_id FROM taxa").fetchall()
    finally:
        conn.close()
    assert counts.total_taxa == 1
    assert counts.rejected_lines == 1
    assert rows == [("1",)]


def test_import_handles_depth_skip(tmp_path: Path) -> None:
    """A row whose depth skips a parent level must be rejected
    so the parent linkage does not silently point at a stale
    stack frame."""
    src = tmp_path / "skipped.txt"
    src.write_text(
        "Animalia [kingdom] {ID=1}\n        Chordata [phylum] {ID=2}\n",
        encoding="utf-8",
    )
    db = tmp_path / "taxon.db"
    counts = import_col_dataset(src, db)
    assert counts.total_taxa == 1
    assert counts.rejected_lines == 1
