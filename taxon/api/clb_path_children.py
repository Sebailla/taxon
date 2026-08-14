"""Path-aware cascade resolver backed by ChecklistBank.

The cascade UI consumes ``GET /api/path-children?path=A|B|C`` and
expects the same envelope shape it used against the previous
GBIF-backed resolver (``PathChildrenResponse`` with ``parent``,
``children``, ``next_rank_hint``). The only difference: the parent
and children come from ChecklistBank, not GBIF.

CLB's tier tuple is nine elements — one more than GBIF's seven —
because the cascade exposes the ``biota`` root tier above Kingdom
and the ``subphylum`` tier between Phylum and Class. The locked
9-tuple is declared in :data:`CASCADE_TIERS`; every rank depth
calculation reads from it so the resolver never drifts when a
new tier is added.

The walk algorithm is a single forward pass over the segments:

1. For each segment, search CLB
   ``/nameusage/search?q=<segment>&rank=R``. CLB's search has no
   ``higherTaxonKey`` filter (unlike GBIF) so the resolver relies
   on the ``rank`` anchor to disambiguate same-named taxa at
   different depths. The first hit whose
   :attr:`ChecklistBankTaxon.canonical_name` matches the segment
   case-insensitively is the resolver's match.
2. After resolving the deepest segment, fetch the next tier's
   children via ``/tree/{id}/children?rank=NEXT_TIER_FOR(depth)``.

The first segment's rank is the cascade root: either ``"biota"``
(the path starts with the Biota tier) or ``"kingdom"`` (the path
starts at a kingdom like ``Animalia``). Subsequent segments use
the cascade tier tuple, advancing one slot per segment.

The subphylum collapse rule (phylum with zero subphylum children →
return class children directly) is NOT in this slice. PR #2b adds
it. In PR #2a, the resolver returns subphylum children verbatim
when the parent phylum has any and emits
``next_rank_hint = "class"``; phyla with no subphylum children
return an empty list with ``next_rank_hint = "class"`` and the
frontend renders an empty dropdown.

The shape returned to the (future) API route is the same
:class:`PathChildrenResponse` dataclass the previous resolver
exposed. PR #3's router swap translates the
:class:`ChecklistBankTaxon` parents + children into the public
``TaxonResponse`` envelope.
"""

from __future__ import annotations

from dataclasses import dataclass

from taxon.checklistbank import ChecklistBankClient, ChecklistBankTaxon

#: The 9 cascade tiers CLB exposes. The cascade UI renders one
#: dropdown per tier; the resolver maps each tier to the CLB rank
#: label so the search anchor is unambiguous. ``biota`` is the root
#: tier (above kingdom); ``subphylum`` sits between phylum and class.
CASCADE_TIERS: tuple[str, ...] = (
    "biota",
    "kingdom",
    "phylum",
    "subphylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)

#: The depth at which each tier sits in the cascade. ``biota``
#: is the root (depth 0); ``species`` is the leaf (depth 8). The
#: resolver uses this to compute the next-dropdown label after
#: the user picks a parent.
TIER_DEPTH: dict[str, int] = {tier: idx for idx, tier in enumerate(CASCADE_TIERS)}


@dataclass(frozen=True)
class PathChildrenResponse:
    """Result of ``GET /api/path-children``.

    Mirrors the previous GBIF-backed resolver so the cascade UI
    does not need to change. The :class:`ChecklistBankTaxon`
    instances carry the same fields the previous resolver exposed
    (name, rank, parent_id, dataset_key, taxon_id, count,
    child_count) for the router to translate into the public
    ``TaxonResponse`` envelope in PR #3.
    """

    parent: ChecklistBankTaxon
    children: list[ChecklistBankTaxon]
    next_rank_hint: str | None


def list_path_children(
    segments: list[str],
    client: ChecklistBankClient | None = None,
) -> PathChildrenResponse | None:
    """Walk ``segments`` to the deepest taxon and return its children.

    Returns ``None`` when any segment does not resolve against CLB
    (the walk aborts on the first miss and returns ``None`` — the
    router maps that to a 404 so the cascade UI can highlight the
    dropdown that produced the bad path).

    The client argument accepts an injected ``ChecklistBankClient``
    so tests can pass a transport-stubbed client. Production
    callers leave it ``None`` and the resolver owns the client
    lifecycle.
    """
    if not segments:
        return None

    clb = client or ChecklistBankClient()

    # Resolve the deepest segment. CLB search has no
    # ``higherTaxonKey`` filter (unlike GBIF); the walk relies on
    # the ``rank`` anchor at each depth to disambiguate same-named
    # taxa at different levels.
    deepest = _resolve_deepest(segments, clb)
    if deepest is None:
        return None

    # Fetch the children. The cascade renders one dropdown per
    # tier; the resolver filters the children to the next cascade
    # tier so the dropdown shows only the rows the user can pick
    # to advance the chain.
    next_tier_rank = _next_tier_for(deepest.rank)
    if next_tier_rank is None:
        return PathChildrenResponse(parent=deepest, children=[], next_rank_hint=None)

    children_rows = clb.get_children(deepest.taxon_id, rank=next_tier_rank)

    # The cascade UI needs the tier label even when the current
    # parent has no children at that tier (e.g. an extinct phylum
    # with no surviving subphylum). The frontend renders an empty
    # dropdown so the user knows there is no further tier.
    next_rank_hint: str | None = next_tier_rank.lower()

    return PathChildrenResponse(
        parent=deepest,
        children=children_rows,
        next_rank_hint=next_rank_hint,
    )


def _resolve_deepest(segments: list[str], client: ChecklistBankClient) -> ChecklistBankTaxon | None:
    """Resolve the deepest segment to a CLB taxon row.

    The cascade path is a list of canonical names. The resolver
    walks the segments in order, asking CLB for the taxon that
    matches the segment's canonical name at the rank appropriate
    to the segment's position in the path. CLB's
    ``/nameusage/search`` endpoint has no parent-anchor filter, so
    the resolver relies on the ``rank=R`` anchor at each step to
    keep same-named taxa from colliding (e.g. ``Panthera`` at genus
    depth vs. ``Panthera`` at any other rank).

    The first segment is the cascade root: either ``"Biota"``
    (rank = ``biota``) or a kingdom name like ``"Animalia"``
    (rank = ``kingdom``). Subsequent segments advance one slot
    through :data:`CASCADE_TIERS`.

    The walk aborts on the first segment that does not resolve and
    returns ``None`` — partial paths do NOT yield a "deepest match"
    result. CLB has no ``higherTaxonKey`` to fall back on for
    disambiguation, so a half-matching path would just be a
    different taxon than the one the user requested.
    """
    if not segments:
        return None

    tier_index = _first_tier_index(segments[0])
    if tier_index is None:
        return None

    current: ChecklistBankTaxon | None = None
    for offset, segment in enumerate(segments):
        rank_index = tier_index + offset
        if rank_index >= len(CASCADE_TIERS):
            # Path went past species; CLB has no rank past
            # species so the resolver stops advancing. The
            # deepest match (the species row) is the answer.
            return current
        rank = CASCADE_TIERS[rank_index]
        hits = client.search(segment, rank=rank)
        hit = _first_match(hits, segment)
        if hit is None:
            return None
        current = hit
    return current


def _first_tier_index(first_segment: str) -> int | None:
    """Return the cascade tier index for the first segment.

    The cascade root is either ``"Biota"`` (rank = ``biota``,
    index 0) or any kingdom name (rank = ``kingdom``, index 1).
    Names that are not the cascade root return ``None`` — the
    resolver treats them as a failed match.

    A more robust alternative would issue an unranked search to
    detect the segment's rank, but that costs an extra HTTP call
    per path resolution. The hardcoded dispatcher keeps the
    walk to ``N + 1`` calls (one search per segment plus one
    children fetch for the leaf).
    """
    if first_segment.lower() == "biota":
        return 0
    return 1


def _first_match(hits: list[ChecklistBankTaxon], segment: str) -> ChecklistBankTaxon | None:
    """Return the first hit whose canonical name matches ``segment``.

    The match is case-insensitive because CLB ranks sometimes
    return mixed-case canonical names (e.g. ``Animalia`` vs.
    ``animalia``) for taxa that carry author citations in the
    display label but lower-case it in the canonical column.
    """
    segment_lower = segment.lower()
    for hit in hits:
        if hit.canonical_name.lower() == segment_lower:
            return hit
    return None


def _next_tier_for(rank: str) -> str | None:
    """Return the cascade tier that follows ``rank``.

    The cascade walks one tier per dropdown click. Given a parent
    at ``rank``, the next dropdown shows the parent's children at
    the rank that maps to the next cascade tier. Returns
    ``None`` when the chain has reached the leaf and there is
    no next tier.

    The mapping matches the 9-tier tuple. The subphylum tier
    always appears as a real intermediate — PR #2b adds the
    collapse rule for phyla with no subphylum children.
    """
    cascade_next_tier: dict[str, str] = {
        "biota": "kingdom",
        "kingdom": "phylum",
        "phylum": "subphylum",
        "subphylum": "class",
        "class": "order",
        "order": "family",
        "family": "genus",
        "genus": "species",
        "species": "species",
    }
    return cascade_next_tier.get(rank.lower())


__all__ = [
    "CASCADE_TIERS",
    "TIER_DEPTH",
    "PathChildrenResponse",
    "list_path_children",
]
