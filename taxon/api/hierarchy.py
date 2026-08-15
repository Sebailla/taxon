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

PR #58 (SQLite-only cascade)
----------------------------
The PR adds three display-level-aware helpers:

- :func:`_intermediate_ranks_for` — derive the set of "off-tuple"
  ranks that sit inside a display bucket (e.g. every rank that maps
  to ``"family"`` except ``"family"`` itself). The mapping is read
  directly from :data:`taxon.taxonomy.RANK_TO_DISPLAY_LEVEL` so the
  whitelist stays the single source of truth.
- :func:`resolve_path_by_display_level` — descendant lookup that
  matches each path segment against ``display_level == bucket`` and
  verifies the parent chain is contiguous across matched nodes.

The cascade walk was historically projected onto a fixed 9-tier tuple
(``biota, kingdom, phylum, subphylum, class, order, family, genus,
species``) and dead-ended at every off-tuple rank. The display-level
helpers fold every intermediate rank into the parent bucket so the
walk keeps advancing on real-world data shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import Case, case, func, select
from sqlalchemy.orm import Session

from taxon.schema import Taxon
from taxon.taxonomy import RANK_TO_DISPLAY_LEVEL

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
    "_intermediate_ranks_for",
    "list_children",
    "list_root_taxa",
    "resolve_path",
    "resolve_path_by_display_level",
]


# ---------------------------------------------------------------------------
# PR #58 — display-level-aware resolvers.
# ---------------------------------------------------------------------------

# The cascade buckets in the order the UI walks them. ``realm`` sits at
# the top (above kingdom) and ``species`` at the bottom.
_DISPLAY_LEVELS_IN_ORDER: Final[tuple[str, ...]] = (
    "realm",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)


def _intermediate_ranks_for(level: str) -> set[str]:
    """Return the set of ranks whose ``display_level`` equals ``level`` excluding ``level`` itself.

    Derived from :data:`taxon.taxonomy.RANK_TO_DISPLAY_LEVEL` so the
    whitelist stays the single source of truth. Used by the
    roll-up rules in :mod:`taxon.api.sqlite_resolver` to detect
    "off-tuple" intermediate ranks (e.g. ``subphylum`` inside the
    ``phylum`` bucket) so the cascade walk can hide them inside
    intermediate hops instead of surfacing them as separate dropdowns.

    The result is intentionally a ``set[str]`` so membership tests
    run in constant time at the resolver hot-path.
    """
    bucket = {rank for rank, lvl in RANK_TO_DISPLAY_LEVEL.items() if lvl == level}
    bucket.discard(level)
    return bucket


def _effective_display_level() -> Case[str | None]:
    """Return a SQL expression that yields the bucket, computed at query time.

    The WoRMS DwC-A importer (``taxon.import_data``) pre-populates
    ``Taxon.display_level`` at insert time. The GBIF indented-tree
    importer (``taxon.indented_import``) intentionally leaves the
    column NULL so :func:`taxon.taxonomy.display_level` is the source
    of truth. Both shapes resolve through this expression:

    - ``Taxon.display_level`` when the column is populated (WoRMS).
    - ``taxonomy_display_level(Taxon.rank)`` when the column is
      NULL (GBIF indented). The function is registered on every
      SQLite connection via :func:`taxon.api._build_engine`.

    The resolver filters, orders, and groups by the result of this
    expression so the cascade endpoints work identically against
    either data source. Returns ``None`` when the rank is outside
    :data:`taxon.taxonomy.RANK_TO_DISPLAY_LEVEL` (the row is filtered
    out of the cascade).
    """
    return case(
        (Taxon.display_level.isnot(None), Taxon.display_level),
        else_=func.taxonomy_display_level(Taxon.rank),
    )


def _candidate_bucket_indices(last_bucket_index: int | None) -> list[int]:
    """Return the bucket indices to try for the next path segment.

    The cascade tuple is the source of truth for tier ordering
    (``realm, kingdom, phylum, class, order, family, genus, species``).
    The first segment anchors on ``kingdom`` because the cascade
    UI's first queryable tier is kingdom (Biota / Viruses come from
    the synthesised root dropdown, never a path segment).

    Each subsequent segment tries two buckets in priority order:

    1. The bucket one tier below the previously-matched row's
       bucket — the canonical cascade walk.
    2. The same bucket as the previously-matched row — the
       off-tuple intermediate walk (e.g. subphylum / infraphylum /
       parvphylum / microphylum / megaclass under phylum;
       superfamily / subfamily / tribe / subtribe / infratribe under
       family).

    The resolver picks the first match; the second bucket is the
    "same tier, off-tuple intermediate" fallback. Once the resolver
    reaches the leaf tier (``species``), every further segment also
    anchors on ``species`` so subspecies / variety / form
    descendants keep resolving through the same anchor.
    """
    if last_bucket_index is None:
        return [_DISPLAY_LEVELS_IN_ORDER.index("kingdom")]
    if last_bucket_index >= len(_DISPLAY_LEVELS_IN_ORDER) - 1:
        return [last_bucket_index]
    return [last_bucket_index + 1, last_bucket_index]


def resolve_path_by_display_level(
    session: Session,
    segments: list[str],
) -> TaxonRow | None:
    """Resolve ``segments`` against the cascade via display-level anchors.

    Each segment is matched against a row whose ``display_level`` is
    either one tier below the previously-matched row's bucket OR the
    same bucket (for off-tuple intermediates), and whose ``name``
    matches the segment case-insensitively. The first match anchors
    the next segment on its ``id`` so same-named taxa under
    different parents cannot collide.

    Returns the deepest matched row, or ``None`` when any segment
    fails to resolve. The match is unanchored on the first segment
    (the parent of the first tier is unknown — the resolver cannot
    anchor "Animalia" against itself).
    """
    if not segments:
        return None

    parent_id: int | None = None
    current: TaxonRow | None = None
    last_bucket_index: int | None = None

    for segment in segments:
        match: Taxon | None = None
        for bucket_index in _candidate_bucket_indices(last_bucket_index):
            bucket = _DISPLAY_LEVELS_IN_ORDER[bucket_index]
            stmt = (
                select(Taxon)
                .where(func.lower(Taxon.name) == segment.lower())
                .where(func.lower(_effective_display_level()) == bucket.lower())
            )
            if parent_id is not None:
                stmt = stmt.where(Taxon.parent_id == parent_id)
            candidate = session.scalars(stmt).first()
            if candidate is not None:
                match = candidate
                last_bucket_index = bucket_index
                break
        if match is None:
            return None
        current = _to_row(match)
        parent_id = current.id

    return current
