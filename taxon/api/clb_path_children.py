"""Path-aware cascade resolver backed by ChecklistBank.

The cascade UI consumes ``GET /api/path-children?path=A|B|C`` and
expects the same envelope shape (``PathChildrenResponse`` with
``parent``, ``children``, ``next_rank_hint``). The parent and
children come from ChecklistBank.

CLB's tier tuple is nine elements because the cascade exposes the
``biota`` root tier above Kingdom and the ``subphylum`` tier
between Phylum and Class. The locked 9-tuple is declared in
:data:`CASCADE_TIERS`; every rank depth calculation reads from it
so the resolver never drifts when a new tier is added.

The walk algorithm is a single forward pass over the segments:

1. For each segment, search CLB
   ``/nameusage/search?q=<segment>&rank=R``. CLB's search has no
   ``higherTaxonKey`` filter so the resolver relies on the ``rank``
   anchor to disambiguate same-named taxa at different depths. The
   first hit whose
   :attr:`ChecklistBankTaxon.canonical_name` matches the segment
   case-insensitively is the resolver's match.
2. After resolving the deepest segment, fetch the next tier's
   children via ``/tree/{id}/children?rank=NEXT_TIER_FOR(depth)``.

The first segment's rank is the cascade root: either ``"biota"``
(the path starts with the Biota tier) or ``"kingdom"`` (the path
starts at a kingdom like ``Animalia``). Subsequent segments use
the cascade tier tuple, advancing one slot per segment.

Subphylum collapse rule (PR #2b): when the cascade reaches a
phylum, the resolver probes ``/tree/{id}/children?rank=subphylum``
first. If the response is non-empty the resolver returns those
subphyla with ``next_rank_hint = "class"`` (no collapse). If the
response is empty the resolver re-probes with ``rank=class`` and
returns the phylum's classes directly with
``next_rank_hint = "order"`` — the subphylum tier is skipped
entirely. This is one-shot: a phylum with no subphylum AND no
class children returns ``children=[]`` with ``next_rank_hint=None``
so the cascade UI renders an empty leaf dropdown. No recursion.

The shape returned to the API route is the same
:class:`PathChildrenResponse` dataclass. The router translates the
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

    The :class:`ChecklistBankTaxon` instances carry the cascade
    fields (name, rank, parent_id, dataset_key, taxon_id, count,
    child_count) for the router to translate into the public
    ``TaxonResponse`` envelope.
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
    # ``higherTaxonKey`` filter; the walk relies on the ``rank``
    # anchor at each depth to disambiguate same-named taxa at
    # different levels.
    deepest = _resolve_deepest(segments, clb)
    if deepest is None:
        return None

    children_rows, next_rank_hint = _children_for(deepest, clb)

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
    to the segment's position in the path.

    **Root tier shortcut.** The first segment can be one of the
    two top-tier names ``"Biota"`` or ``"Viruses"``. CLB's
    ``/nameusage/search`` endpoint rejects searches with
    ``rank=biota`` (it returns HTTP 400 because the root tier is
    not searchable on its own), so the resolver shortcuts the
    first segment through ``get_taxon`` with the well-known id
    found in :data:`_ROOT_TAXON_BY_NAME`. Subsequent segments
    are walked with the standard rank-anchored search.

    **Subsequent segments** advance one slot through
    :data:`CASCADE_TIERS` and use ``client.search(segment,
    rank=...)`` to bind the canonical name to a CLB taxon id.
    CLB's search has no ``higherTaxonKey`` filter, so the
    ``rank=R`` anchor at each step keeps same-named taxa from
    colliding (e.g. ``Panthera`` at genus depth vs. ``Panthera``
    at any other rank).

    **Failure mode.** The walk aborts on the first segment that
    does not resolve and returns ``None`` — partial paths do NOT
    yield a "deepest match" result. CLB has no
    ``higherTaxonKey`` to fall back on for disambiguation, so a
    half-matching path would just be a different taxon than the
    one the user requested.
    """
    if not segments:
        return None

    first_segment = segments[0]
    root_id = _ROOT_TAXON_BY_NAME.get(first_segment.lower())
    if root_id is not None:
        # Root-tier shortcut: bind the well-known id with
        # ``get_taxon`` (no search). After this binding the
        # resolver has resolved the ``biota`` tier, so the
        # next segment to walk is ``kingdom`` (tier_index=1).
        current = client.get_taxon(root_id)
        if current is None:
            return None
        next_segment_index = 1
        tier_index = 1  # next segment lives at "kingdom"
    else:
        # Non-root first segment: bind as kingdom via a
        # rank-anchored search. After this binding the resolver
        # has resolved the ``kingdom`` tier, so the next
        # segment to walk is ``phylum`` (tier_index=2).
        hits = client.search(first_segment, rank=CASCADE_TIERS[1])
        hit = _first_match(hits, first_segment)
        if hit is None:
            return None
        current = hit
        next_segment_index = 1
        tier_index = 2  # next segment lives at "phylum"

    for offset, segment in enumerate(segments[next_segment_index:]):
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


#: Well-known CLB ids for the two cascade top-tier taxa. CLB
#: assigns the root tier opaque string ids that never change
#: across releases. The resolver shortcuts the first segment
#: through these ids because ``/nameusage/search`` returns
#: HTTP 400 when the ``rank=`` filter targets ``"biota"`` (the
#: root is not searchable on its own).
_ROOT_TAXON_BY_NAME: dict[str, str] = {
    "biota": "5T6MX",
    "viruses": "V",
}


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
    ``None`` when the chain has reached a leaf and there is
    no next tier.

    The mapping matches the 9-tier tuple. For phylum parents the
    static mapping returns ``"subphylum"``; the actual fetch
    logic in :func:`_children_for` may collapse that to ``"class"``
    when the phylum has no subphylum children (the subphylum
    collapse rule from PR #2b).

    CLB publishes the root tier (``Biota`` / ``Viruses``) under
    rank ``"unranked"`` rather than ``"biota"``; the resolver
    normalises that through :func:`_normalize_root_rank` so the
    mapping below can be a flat dict lookup.
    """
    rank = _normalize_root_rank(rank)
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


def _normalize_root_rank(rank: str) -> str:
    """Map CLB's ``"unranked"`` label to the resolver's ``"biota"`` tier.

    CLB publishes ``Biota`` / ``Viruses`` under the rank label
    ``"unranked"`` rather than ``"biota"`` because the curated
    CoL taxonomy has not assigned them a Linnaean rank. The
    resolver treats them as the cascade's "biota" root tier
    so the rest of the resolver can keep a single key space
    keyed on :data:`CASCADE_TIERS`.
    """
    if rank.lower() == "unranked":
        return "biota"
    return rank


def _children_for(
    parent: ChecklistBankTaxon,
    client: ChecklistBankClient,
) -> tuple[list[ChecklistBankTaxon], str | None]:
    """Return ``(children, next_rank_hint)`` for ``parent``.

    The cascade renders one dropdown per tier. Given a parent
    at some rank, this helper fetches the parent's children at
    the next cascade tier and emits the tier label the frontend
    needs for the dropdown placeholder.

    Subphylum collapse (PR #2b): when ``_next_tier_for(parent.rank)``
    returns ``"subphylum"`` (i.e. the parent is a phylum), the
    helper probes ``/tree/{id}/children?rank=subphylum`` first:

    - **Non-empty** subphylum response: return those subphyla with
      ``next_rank_hint = "class"``. No collapse.
    - **Empty** subphylum response: re-query with
      ``rank=class`` and return the phylum's classes directly
      with ``next_rank_hint = "order"`` (skipping subphylum
      entirely). If the class query also returns ``[]``, the
      helper emits ``next_rank_hint = None`` so the cascade UI
      renders the leaf dropdown.

    The collapse is one-shot (no recursion): a phylum with zero
    subphylum children queries ``rank=class`` once. A fossil
    phylum with no subphylum AND no class children terminates
    cleanly with an empty list and ``None`` hint.

    For non-phylum parents the collapse rule does not fire: the
    helper queries ``rank=next_tier`` once and emits
    ``next_rank_hint = next_tier.lower()``. The leaf case
    (``next_tier is None``) emits ``children=[]`` with
    ``next_rank_hint=None`` so the cascade UI stops cleanly.
    """
    next_tier_rank = _next_tier_for(parent.rank)
    if next_tier_rank is None:
        # Leaf parent (e.g. species): no further tier to render.
        return [], None

    if next_tier_rank == "subphylum":
        # Subphylum collapse probe (PR #2b). Most phyla in
        # CLB's COL2024 dataset have zero subphylum children
        # (e.g. Arthropoda); only Chordata carries the three
        # chordate subphyla. Probe first; collapse on empty.
        subphyla = client.get_children(parent.taxon_id, rank="subphylum")
        if subphyla:
            return subphyla, "class"
        # Collapse: skip subphylum, return classes directly.
        classes = client.get_children(parent.taxon_id, rank="class")
        if not classes:
            # Fossil phylum with no subphylum AND no class
            # children: terminate cleanly. The cascade UI
            # renders an empty dropdown.
            return [], None
        return classes, "order"

    # Standard path: parent is not a phylum, so no collapse.
    children_rows = client.get_children(parent.taxon_id, rank=next_tier_rank)
    return children_rows, next_tier_rank.lower()


__all__ = [
    "CASCADE_TIERS",
    "TIER_DEPTH",
    "PathChildrenResponse",
    "list_path_children",
]
