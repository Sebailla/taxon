"""Streaming parser for the Catalogue of Life (CoL) DwC-A NameUsage TSV.

The parser mirrors ``taxon.parser.parse_taxa`` in shape: it yields
``(parent_source_id, ParsedTaxon)`` tuples from each non-header
line of the TSV. The downstream ``import_dataset`` reads the same
shape, so the WoRMS path and the CoL path share the inserter.

Schema mapping is documented in detail in
``tests/test_col_parser.py``. The columns we read by ordinal:

-  1  col:ID                  → source_id
-  5  col:parentID            → parent_source_id
-  7  col:status              → marker source
-  8  col:scientificName      → display_name base
-  9  col:authorship          → display_name suffix
- 10  col:rank                → rank
- 13  col:uninomial           → name (kingdom/phylum/class/order/family)
- 14  col:genericName         → name prefix (genus)
- 16  col:specificEpithet     → species epithet
- 17  col:infraspecificEpithet → subspecies/variety epithet
- 46  col:extinct             → is_extinct

Other columns (authorship parts, geographic ranks, references)
are ignored at this layer. The species-path projection happens
later in ``import_data`` by reading the rank-resolved columns
50 (species), 53 (genus), 57 (family), 60 (order), 62 (class),
64 (phylum), 65 (kingdom) directly — those are already populated
per-row by CoL so no ancestor walk is needed.

Unlike the WoRMS parser, CoL rows are NOT delivered in
depth-first order. A single ``source_id`` row may reference a
``parentID`` that does not appear earlier in the file. The
importer handles this with a two-pass strategy (insert with
``parent_id = NULL`` first, then a SQL ``UPDATE`` to wire up the
parents), not in the parser. The parser stays a pure streaming
row-to-tuple transform.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypedDict

from taxon.parser import ParsedTaxon

_REQUIRED_COLUMNS = (
    "col:ID",
    "col:parentID",
    "col:status",
    "col:scientificName",
    "col:authorship",
    "col:rank",
    "col:extinct",
)

# Column ordinals in NameUsage.tsv. Keep them as constants so the
# mapping is explicit and easy to audit against the CoL DwC-A
# schema release notes.
_COL_ID = 0
_COL_PARENT_ID = 4
_COL_STATUS = 6
_COL_SCIENTIFIC_NAME = 7
_COL_AUTHORSHIP = 8
_COL_RANK = 9
_COL_UNINOMIAL = 12
_COL_GENERIC_NAME = 13
_COL_SPECIFIC_EPITHET = 15
_COL_INFRASPECIFIC_EPITHET = 16
_COL_EXTINCT = 45


class _ColColumns(TypedDict):
    """Parsed CoL row by ordinal.

    Only the columns we read are populated. Keys are 0-indexed
    ordinals to keep the dict literal-friendly in this layer.
    """

    id: str
    parent_id: str
    status: str
    scientific_name: str
    authorship: str
    rank: str
    uninomial: str
    generic_name: str
    specific_epithet: str
    infraspecific_epithet: str
    extinct: str


def parse_col_taxa(lines: Iterable[str]) -> Iterator[tuple[str | None, ParsedTaxon]]:
    """Yield ``(parent_source_id, ParsedTaxon)`` for every data row.

    The first yielded line is the header; it is validated and
    consumed but produces no taxon. Blank lines are skipped. The
    iterator is streaming — it never reads the whole TSV into
    memory.

    Raises ``ValueError`` if the header is missing one of the
    required columns or if a data row has fewer cells than the
    header (the latter is treated as a malformed record rather
    than a silent skip, because the file ships with a strict
    column count per row in the published archive).
    """
    rows = iter(lines)
    header_cells = _consume_header(next(rows))
    expected_columns = len(header_cells)

    for raw_line in rows:
        if not raw_line.strip():
            continue
        cells = raw_line.rstrip("\r\n").split("\t")
        if len(cells) != expected_columns:
            raise ValueError(
                f"CoL row has {len(cells)} cells, expected {expected_columns}: {raw_line!r}"
            )
        row: _ColColumns = _extract_row(cells)
        parsed = _build_parsed_taxon(row)
        parent_id = row["parent_id"] or None
        yield (parent_id, parsed)


def _consume_header(line: str) -> list[str]:
    cells = line.rstrip("\r\n").split("\t")
    missing = [column for column in _REQUIRED_COLUMNS if column not in cells]
    if missing:
        raise ValueError(f"CoL TSV header is missing required columns: {missing}")
    return cells


def _extract_row(cells: list[str]) -> _ColColumns:
    return {
        "id": cells[_COL_ID],
        "parent_id": cells[_COL_PARENT_ID],
        "status": cells[_COL_STATUS],
        "scientific_name": cells[_COL_SCIENTIFIC_NAME],
        "authorship": cells[_COL_AUTHORSHIP],
        "rank": cells[_COL_RANK],
        "uninomial": cells[_COL_UNINOMIAL],
        "generic_name": cells[_COL_GENERIC_NAME],
        "specific_epithet": cells[_COL_SPECIFIC_EPITHET],
        "infraspecific_epithet": cells[_COL_INFRASPECIFIC_EPITHET],
        "extinct": cells[_COL_EXTINCT],
    }


def _build_parsed_taxon(row: _ColColumns) -> ParsedTaxon:
    name = _canonical_name(row)
    display_name = _display_name(row)
    return ParsedTaxon(
        source_id=row["id"],
        rank=row["rank"],
        name=name,
        display_name=display_name,
        is_synonym=_is_synonym(row["status"]),
        is_extinct=_is_extinct(row["extinct"]),
        is_uncertain=_is_uncertain(row["status"]),
        is_unassigned=_is_unassigned(row["rank"]),
    )


def _canonical_name(row: _ColColumns) -> str:
    """Derive the rank-specific canonical name.

    Strategy: prefer the rank-decomposed columns when CoL has
    populated them (species and below), otherwise fall back to
    ``col:scientificName`` which always carries the canonical
    label without authorship.

    - kingdom / phylum / class / order / family / suborder /
      superfamily / ... → ``col:scientificName`` (CoL leaves
      ``col:uninomial`` empty for some taxa; ``scientificName``
      is the authoritative source).
    - genus / subgenus → ``col:scientificName``.
    - species → ``"{genericName} {specificEpithet}"`` if both
      parts are populated, else ``col:scientificName``.
    - subspecies / variety / form → joined generic + specific +
      infraspecific epithet, else ``col:scientificName``.
    - unranked → ``col:scientificName``.
    """
    rank = row["rank"]
    scientific = row["scientific_name"]
    if rank in {"kingdom", "phylum", "class", "order", "family"}:
        return scientific
    if rank in {"genus", "subgenus"}:
        return scientific
    if rank == "species":
        if row["generic_name"] and row["specific_epithet"]:
            return f"{row['generic_name']} {row['specific_epithet']}"
        return scientific
    if rank in {"subspecies", "variety", "form", "subvariety", "subform"}:
        parts = [
            row["generic_name"],
            row["specific_epithet"],
            row["infraspecific_epithet"],
        ]
        joined = " ".join(part for part in parts if part).strip()
        return joined or scientific
    return scientific


def _display_name(row: _ColColumns) -> str:
    """Display name = scientificName + authorship, both verbatim from CoL."""
    if row["authorship"]:
        return f"{row['scientific_name']} {row['authorship']}".strip()
    return row["scientific_name"]


def _is_synonym(status: str) -> bool:
    """CoL surfaces synonyms under three statuses."""
    return status in {"synonym", "ambiguous synonym", "misapplied"}


def _is_uncertain(status: str) -> bool:
    """CoL's provisionally accepted maps to our is_uncertain flag."""
    return status == "provisionally accepted"


def _is_extinct(value: str) -> bool:
    return value.strip().lower() == "true"


def _is_unassigned(rank: str) -> bool:
    return rank == "unranked"
