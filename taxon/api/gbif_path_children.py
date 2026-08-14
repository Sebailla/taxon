"""Path-aware cascade resolver backed by GBIF.

The cascade UI consumes ``GET /api/path-children?path=A|B|C`` and
expects the same envelope shape it used against the CoL-backed
resolver (parent row + children list + next_rank_hint). The only
difference: the parent and children come from GBIF, not the
local SQLite database.

GBIF's 6-tier taxonomy (kingdom → phylum → order → family → genus
→ species) collapses CoL's 40+ intermediate ranks into one
dropdown per tier. The cascade UI never sees the intermediate
ranks — Animalia has 34 phyla, Chordata has its classes, Panthera
has its species, and so on. The 22,711 flat-rankd children of
Animalia that broke the CoL cascade do not exist in GBIF.

The resolver walks the path in two passes:

1. Resolve the deepest segment by searching GBIF for the
   canonical name. ``/v1/species/search?q=Animalia&rank=KINGDOM``
   returns the correct Animalia in the first row.
2. Fetch the direct children of the resolved taxon via
   ``/v1/species/{key}/children`` and translate the rows into
   the cascade-friendly envelope.

The shape returned to the API route is the same as the previous
CoL-backed resolver (``PathChildrenResponse`` with ``parent``,
``children``, ``next_rank_hint``). The frontend does not need to
know the data source changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taxon.api.hierarchy import TaxonRow
from taxon.gbif import GbifClient, GbifTaxon
from taxon.taxonomy import RANK_TO_DISPLAY_LEVEL

#: The 6 cascade tiers GBIF exposes. The cascade UI renders one
#: dropdown per tier; the resolver maps each tier to the GBIF
#: rank enum (the API uses uppercase enums).
CASCADE_TIERS: tuple[str, ...] = (
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)

#: The depth at which each tier sits in the cascade. ``KINGDOM``
#: is the root of the cascade; ``SPECIES`` is the leaf. The
#: resolver uses this to compute the next dropdown label after
#: the user picks a parent.
TIER_DEPTH: dict[str, int] = {tier: idx for idx, tier in enumerate(CASCADE_TIERS)}


@dataclass(frozen=True)
class PathChildrenResponse:
    """Result of ``GET /api/path-children``.

    Mirrors the previous CoL-backed resolver so the cascade UI
    does not need to change. The :class:`TaxonRow` instances
    carry the same fields the previous resolver exposed
    (name, rank, parent_id, display_name, marker flags) plus
    a few GBIF-specific fields the cascade does not read yet
    (nub_key, num_children) for future lookup-by-id searches.
    """

    parent: TaxonRow
    children: list[TaxonRow]
    next_rank_hint: str | None


@dataclass(frozen=True)
class _SearchHit:
    """Internal carrier for a single GBIF search row.

    The cascade resolver searches by canonical name at a known
    rank (e.g. "Animalia" at rank=KINGDOM). The hit carries the
    key and the parent_key so the resolver can ask for the
    children without a second search.
    """

    key: int
    canonical_name: str
    rank: str
    parent_key: int | None


def list_path_children(
    segments: list[str],
    client: GbifClient | None = None,
) -> PathChildrenResponse | None:
    """Walk ``segments`` to the deepest taxon and return its children.

    Returns ``None`` when the deepest segment does not resolve
    against GBIF. The router maps that to a 404 so the cascade
    UI can highlight the dropdown that produced the bad path.
    """
    if not segments:
        return None

    gbif = client or GbifClient()

    # Resolve the deepest segment. We search GBIF by canonical
    # name with the rank appropriate to the path depth so the
    # first hit is unambiguous: a kingdom search for "Animalia"
    # returns the kingdom, not a stray genus named Animalia.
    deepest = _resolve_deepest(segments, gbif)
    if deepest is None:
        return None

    # Fetch the children. The cascade renders one dropdown per
    # tier; the resolver filters the children to the next cascade
    # tier so the dropdown shows only the rows the user can pick
    # to advance the chain. GBIF ships children at every rank
    # the parent has direct descendants at (Chordata's children
    # include classes, orders, and families all at once), so we
    # restrict the page to the rank that matches the next
    # cascade tier.
    #
    # The next-tier rank comes from the depth of the resolved
    # taxon in the cascade. A kingdom lookup returns phylum; a
    # genus lookup returns species. The cascade UI then sees a
    # dropdown with the rank-appropriate label.
    next_tier_rank = _next_tier_for(deepest.rank)
    children_rows = (
        gbif.get_children(
            deepest.key,
            rank=next_tier_rank,
        )
        if next_tier_rank is not None
        else []
    )
    cascade_ranks_lower = {r.lower() for r in RANK_TO_DISPLAY_LEVEL}
    visible_children = [row for row in children_rows if row.rank.lower() in cascade_ranks_lower]
    child_taxa = [_to_taxon_row(row) for row in visible_children]

    # The cascade UI needs the tier label even when the current
    # parent has no children at that tier (e.g. an extinct
    # phylum with no surviving order). The frontend renders an
    # empty dropdown so the user knows there is no further tier.
    next_rank_hint: str | None = next_tier_rank.lower() if next_tier_rank is not None else None

    return PathChildrenResponse(
        parent=_to_taxon_row(deepest),
        children=child_taxa,
        next_rank_hint=next_rank_hint,
    )


def _resolve_deepest(segments: list[str], client: GbifClient) -> GbifTaxon | None:
    """Resolve the deepest segment to a GBIF taxon row.

    The cascade path is a list of canonical names. The resolver
    walks the segments in order, asking GBIF for the taxon that
    matches the segment's canonical name and whose parent is the
    previously resolved taxon. The match is rank-agnostic so the
    caller can pass paths of any depth (a single Pantera leo
    resolves to the species; a 6-segment path resolves to the
    Panthera genus).

    The walk stops at the first segment that does not resolve
    under the expected parent, and returns the deepest match.
    The cascade UI handles the "stuck at this tier" state on
    the client side.
    """
    parent_nub: int | None = None
    current: GbifTaxon | None = None
    for depth, segment in enumerate(segments):
        taxon = _search_under_parent(segment, parent_nub, client, depth)
        if taxon is None:
            return current
        current = taxon
        parent_nub = taxon.nub_key
    return current


def _search_under_parent(
    name: str, parent_key: int | None, client: GbifClient, depth: int = 0
) -> GbifTaxon | None:
    """Search GBIF for ``name`` with the optional parent constraint.

    GBIF's search endpoint accepts ``higherTaxonKey`` and ``rank``
    filters that scope the search to children of a given parent
    at a given rank. The resolver uses both:

    - ``higherTaxonKey`` anchors the search to the cascade parent.
    - ``rank`` cuts the fuzzy matches (GBIF returns 54,284
      hits for "Animalia" without ``rank``; with
      ``rank=KINGDOM`` it returns the 8 kingdoms whose canonical
      name is "Animalia" — 1 of which is the kingdom Animalia).

    GBIF exposes multiple dataset-specific keys for the same
    canonical taxon (e.g. "Animalia" has dozens of keys across
    checklists). The resolver picks the hit whose ``nub_key``
    matches the canonical backbone — every Animalia kingdom hit
    has ``nubKey=1``, every Chordata phylum hit has ``nubKey=44``.
    Without this filter, the resolver picks a dataset-specific
    key whose children are empty.
    """
    if parent_key is None:
        results = client.search(name, rank="KINGDOM", higher_taxon_key=None, accepted_only=True)
        for taxon in results:
            if taxon.canonical_name.lower() != name.lower():
                continue
            return taxon
        return None
    # Parent anchor: the cascade tier is fixed by depth.
    rank = CASCADE_TIERS[depth].upper() if depth < len(CASCADE_TIERS) else None
    results = client.search(
        name,
        rank=rank,
        higher_taxon_key=parent_key,
        accepted_only=True,
    )
    # When the parent is the canonical backbone key, GBIF
    # returns hits with ``nubKey`` matching the parent's key.
    # The first hit whose canonical name matches the request is
    # the right answer; subsequent hits are dataset duplicates
    # that often have no children of their own.
    for taxon in results:
        if taxon.canonical_name.lower() != name.lower():
            continue
        return taxon
    return None


def _rank_for_depth(depth: int) -> str:
    """Map the cascade path depth to the GBIF rank at that depth.

    The cascade has 6 tiers (kingdom → species); GBIF's taxonomy
    collapses all intermediate ranks into the parent tier. A path
    depth 0 segment is always a kingdom.
    """
    if depth < 0 or depth >= len(CASCADE_TIERS):
        raise ValueError(f"path depth {depth} is outside the cascade tiers")
    return CASCADE_TIERS[depth].upper()


def _next_tier_for(rank: str) -> str | None:
    """Return the GBIF rank that the next cascade dropdown should show.

    The cascade walks one tier per dropdown click. Given a parent
    at ``rank``, the next dropdown shows the parent's children at
    the rank that maps to the next cascade tier. Returns
    ``None`` when the chain has reached the leaf and there is
    no next tier.
    """
    rank_upper = rank.upper()
    cascade_rank_to_bucket = {
        "KINGDOM": "PHYLUM",
        "PHYLUM": "CLASS",
        "CLASS": "ORDER",
        "ORDER": "FAMILY",
        "FAMILY": "GENUS",
        "GENUS": "SPECIES",
        # The species tier has subspecies, varieties, and forms
        # below it. The cascade surfaces those as "species"
        # children for the user to inspect.
        "SPECIES": "SPECIES",
    }
    return cascade_rank_to_bucket.get(rank_upper)


def _gbif_taxon_from_search(row: dict[str, Any]) -> GbifTaxon:
    """Build a :class:`GbifTaxon` from a /species/search row.

    The search response shape is a subset of the full species
    shape (it omits ``numDescendants`` and a few others). We
    map the columns we need and let the rest default to None.
    """
    nub_key_raw: Any = row.get("nubKey", row["key"])
    return GbifTaxon(
        key=row["key"],
        nub_key=int(nub_key_raw) if nub_key_raw is not None else row["key"],
        canonical_name=row["canonicalName"],
        scientific_name=row["scientificName"],
        rank=row["rank"],
        kingdom=row.get("kingdom"),
        phylum=row.get("phylum"),
        order=row.get("order"),
        family=row.get("family"),
        genus=row.get("genus"),
        species=row.get("species"),
        parent_key=row.get("parentKey"),
        parent=row.get("parent"),
        num_children=row.get("numDescendants"),
    )


def _to_taxon_row(row: GbifTaxon) -> TaxonRow:
    """Translate a :class:`GbifTaxon` into the legacy :class:`TaxonRow`.

    The cascade UI consumes :class:`TaxonRow`; the resolver
    bridges GBIF rows to that shape so the frontend does not
    need to change when the data source changes.
    """
    from taxon.api.hierarchy import TaxonRow

    # GBIF row IDs are not autoincrement integers; they are the
    # public species key. The cascade UI never uses the row id
    # for anything other than row tracking, so the bridge maps
    # the GBIF key to the row id slot.
    return TaxonRow(
        id=row.key,
        name=row.canonical_name,
        rank=row.rank.lower(),
        parent_id=row.parent_key,
        display_name=row.scientific_name,
        is_synonym=False,
        is_extinct=False,
        is_uncertain=False,
        is_unassigned=False,
    )


__all__ = [
    "CASCADE_TIERS",
    "TIER_DEPTH",
    "PathChildrenResponse",
    "list_path_children",
]
