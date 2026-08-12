"""Hierarchy resolver: path-name lookups against the ``Taxon`` table.

Sub-PR 2B exposes the cascade UI as a series of GET endpoints. Each
endpoint takes a path of canonical names (case-insensitive) and returns
the direct children at the next rank. The resolver walks the path
segment-by-segment, anchoring each lookup on the parent identified by
the previous segment; that anchoring is what prevents same-named taxa
under different parents from colliding — the path's rank context
disambiguates them by construction.

Layering
--------
The router module (:mod:`taxon.api.router`) wires this resolver to
FastAPI routes and is the only thing that touches ``FastAPI``-specific
types. This module is pure SQLAlchemy + dataclasses so it stays unit-
testable without spinning up the API.

Path names are matched with ``func.lower(Taxon.name) == func.lower(segment)``
rather than a Python ``str.lower()`` round-trip; SQLite's default
``NOCASE`` collation is not enabled on the column so a SQL-side
``LOWER()`` keeps the comparison in one place and is index-friendly via
the planner's deterministic text handling on small result sets (the
hierarchy endpoints touch only the children of one parent at a time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.schema import Taxon

# Canonical rank order used by the cascade.
PATH_RANKS: Final[tuple[str, ...]] = (
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
)

# The leaf segment of the cascade: ``/api/.../{genus}/species`` returns
# the children of a genus that have ``rank == "species"``.
SPECIES_RANK: Final[str] = "species"


@dataclass(frozen=True)
class TaxonRow:
    """Lightweight view over a ``Taxon`` row for hierarchy responses.

    Pydantic's ``TaxonResponse.model_validate(row)`` consumes any object
    that exposes the relevant attributes; this dataclass mirrors the
    column names so the response model can be built without reaching
    into ORM internals.
    """

    id: int
    name: str
    display_name: str
    rank: str
    parent_id: int | None
    is_synonym: bool
    is_extinct: bool
    is_uncertain: bool
    is_unassigned: bool


def _to_row(taxon: Taxon) -> TaxonRow:
    """Materialise a ``Taxon`` into the dataclass the response model expects."""
    return TaxonRow(
        id=taxon.id,
        name=taxon.name,
        display_name=taxon.display_name,
        rank=taxon.rank,
        parent_id=taxon.parent_id,
        is_synonym=taxon.is_synonym,
        is_extinct=taxon.is_extinct,
        is_uncertain=taxon.is_uncertain,
        is_unassigned=taxon.is_unassigned,
    )


def list_root_taxa(session: Session) -> list[TaxonRow]:
    """Return every Kingdom-rank taxon sorted by canonical ``name``.

    "Root" here means ``rank == 'kingdom'`` — the cascade starts at
    Kingdom and the frontend's first dropdown lists only those rows.
    WoRMS includes a Biota superdomain above the kingdoms; superdomains
    are intentionally excluded because the cascade UI mirrors the sheet
    behaviour which starts at Kingdom.
    """
    stmt = (
        select(Taxon)
        .where(func.lower(Taxon.rank) == "kingdom")
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    return [_to_row(t) for t in session.scalars(stmt).all()]


def list_children(
    session: Session,
    *,
    parent_id: int,
    rank: str,
) -> list[TaxonRow]:
    """Return every direct child of ``parent_id`` at ``rank``, sorted."""
    stmt = (
        select(Taxon)
        .where(Taxon.parent_id == parent_id)
        .where(func.lower(Taxon.rank) == rank.lower())
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    return [_to_row(t) for t in session.scalars(stmt).all()]


def resolve_path(session: Session, segments: list[str]) -> TaxonRow | None:
    """Walk ``segments`` against the cascade, returning the deepest match.

    Each segment must match a direct child of the previous segment by
    case-insensitive ``name``. The match's ``rank`` is checked against
    the expected rank in :data:`PATH_RANKS` so a request asking for
    ``/api/Animalia/Chordata`` does not accept a Kingdom named
    ``Chordata`` that happens to live somewhere else.

    The first segment is matched by ``rank == 'kingdom'`` (not by
    ``parent_id IS NULL``) because WoRMS attaches a Biota superdomain
    above every kingdom and the cascade UI starts at Kingdom, not at
    the superdomain. Subsequent segments are anchored on the previous
    match's ``id``.

    Returns ``None`` when any segment fails to resolve.
    """
    if not segments:
        return None

    parent_id: int | None = None
    current: TaxonRow | None = None

    for index, segment in enumerate(segments):
        expected_rank = PATH_RANKS[index]
        stmt = select(Taxon).where(func.lower(Taxon.name) == segment.lower())
        if parent_id is None:
            # First segment: anchor on rank, not on parent_id, so the
            # resolver finds Animalia even though WoRMS sits a Biota
            # superdomain above every kingdom.
            stmt = stmt.where(func.lower(Taxon.rank) == expected_rank)
        else:
            stmt = stmt.where(Taxon.parent_id == parent_id)
        candidate = session.scalars(stmt).first()
        if candidate is None:
            return None
        if candidate.rank.lower() != expected_rank:
            # The segment exists but under a different rank — the
            # cascade only accepts the canonical rank at this depth.
            return None
        current = _to_row(candidate)
        parent_id = current.id

    return current


__all__ = [
    "PATH_RANKS",
    "SPECIES_RANK",
    "TaxonRow",
    "list_children",
    "list_root_taxa",
    "resolve_path",
]
