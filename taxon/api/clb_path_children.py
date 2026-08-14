"""Path-aware cascade resolver backed by ChecklistBank.

The cascade UI consumes ``GET /api/path-children?path=A|B|C`` and
expects the same envelope shape (``PathChildrenResponse`` with
``parent``, ``children``, ``next_tiers``). The parent and
children come from ChecklistBank.

The walk algorithm is a single forward pass over the segments:

1. For each segment, search CLB
   ``/nameusage/search?q=<segment>&rank=R``. CLB's search has no
   ``higherTaxonKey`` filter so the resolver relies on the ``rank``
   anchor to disambiguate same-named taxa at different depths. The
   first hit whose
   :attr:`ChecklistBankTaxon.canonical_name` matches the segment
   case-insensitively is the resolver's match.
2. After resolving the deepest segment, fetch the children via
   ``/tree/{id}/children`` with **no ``rank=`` filter** and group
   them by their actual CLB rank label.

The first segment's rank is the cascade root: either ``"biota"``
(the path starts with the Biota tier) or ``"kingdom"`` (the path
starts at a kingdom like ``Animalia``). Subsequent segments use
the cascade tier tuple, advancing one slot per segment.

Best-effort walk (Issue #43)
----------------------------

CLB / CoL publishes children at multiple ranks between any two
tuple tiers (``infraphylum``, ``parvphylum``, ``megaclass``
between subphylum and class; ``subclass`` between class and
order; ``suborder`` between order and family). The locked 9-tier
tuple the legacy resolver projected onto could not name these
intermediate ranks — the path would dead-end at any off-tuple
tier (e.g. Chordata → Vertebrata → Gnathostomata broke at
Gnathostomata because the tuple did not name ``infraphylum``).

The new resolver fetches children with no rank filter, groups
them by their actual CLB rank label, and emits one
:class:`NextTier` per rank group. The wire envelope exposes
``next_tiers: list[NextTier]`` so the cascade UI renders one
dropdown per rank group with the dropdown label taken from the
rank itself ("Infraphylum", "Parvphylum", "Megaclass",
"Subclass", "Suborder").

Subphylum collapse rule (PR #2b)
--------------------------------

When the **parent is a phylum** and the children fetch returns
only ``class``-rank rows (no subphylum, infraphylum, parvphylum,
megaclass children at all), the resolver collapses the children
to a single ``class`` tier so the cascade UI does not show an
extra empty picker. When the phylum has any non-class children
(subphylum, infraphylum, etc.) there is no collapse — the
children groups themselves encode the right number of tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
class NextTier:
    """One available tier below ``parent``.

    CLB / CoL publishes children at multiple ranks between any two
    tuple tiers (e.g. ``infraphylum`` and ``parvphylum`` between
    subphylum and class). The resolver groups children by their
    actual rank label and emits one ``NextTier`` per rank group.
    The frontend renders one cascade dropdown per group, with the
    dropdown's label taken from :attr:`label`.
    """

    rank: str
    """CLB rank label, verbatim (``"infraphylum"``, ``"suborder"``, ...)."""

    label: str
    """User-facing dropdown label, capitalised from :attr:`rank`."""

    examples: list[str] = field(default_factory=list)
    """First three children names; convenience for tests + tooltips."""

    children: list[ChecklistBankTaxon] = field(default_factory=list)
    """Children at this rank; the frontend extends the path by one
    segment per tier group."""


@dataclass(frozen=True)
class PathChildrenResponse:
    """Result of ``GET /api/path-children``.

    The :class:`ChecklistBankTaxon` instances carry the cascade
    fields (name, rank, parent_id, dataset_key, taxon_id, count,
    child_count) for the router to translate into the public
    ``TaxonResponse`` envelope.

    :attr:`children` stays as a flat, de-duplicated list of every
    child so legacy callers iterating without grouping keep
    working. :attr:`children_by_rank` carries the grouped view
    keyed by lower-cased rank label; :attr:`next_tiers` is the
    ordered list of :class:`NextTier` records the wire envelope
    exposes.
    """

    parent: ChecklistBankTaxon
    children: list[ChecklistBankTaxon]
    children_by_rank: dict[str, list[ChecklistBankTaxon]]
    next_tiers: list[NextTier] | None


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

    children_rows, children_by_rank, next_tiers = _children_for(deepest, clb)

    return PathChildrenResponse(
        parent=deepest,
        children=children_rows,
        children_by_rank=children_by_rank,
        next_tiers=next_tiers,
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
            # Off-tuple intermediate ranks (Issue #43) consume
            # more depth slots than the 9-tier tuple accounts
            # for: e.g. the Chordata chain has 5 extra tiers
            # (infraphylum, parvphylum, megaclass, subclass,
            # suborder) between subphylum and family. Once we
            # exhaust the tuple, fall back to rank-less search
            # so the walk keeps advancing on off-tuple ranks.
            # The match is then ambiguous-by-name (same-named
            # taxa at different ranks could collide) but in
            # practice the cascade UI walks each step from a
            # known parent so the breadcrumb disambiguates the
            # match.
            hits = client.search(segment)
            hit = _first_match(hits, segment)
            if hit is None:
                return None
            current = hit
            continue
        rank = CASCADE_TIERS[rank_index]
        # Best-effort fallback: when the rank-anchored search
        # returns zero hits because the segment lives at an
        # off-tuple rank, retry without the rank filter so the
        # walk can advance through infraphylum, parvphylum,
        # megaclass, subclass, suborder, ... without dying.
        hits = client.search(segment, rank=rank)
        hit = _first_match(hits, segment)
        if hit is None:
            hits = client.search(segment)
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


def _children_for(
    parent: ChecklistBankTaxon,
    client: ChecklistBankClient,
) -> tuple[list[ChecklistBankTaxon], dict[str, list[ChecklistBankTaxon]], list[NextTier] | None]:
    """Return ``(children, children_by_rank, next_tiers)`` for ``parent``.

    The cascade renders one dropdown per tier group. Given a parent
    at some rank, this helper fetches every direct child (no rank
    filter), groups them by their actual CLB rank label, and emits
    one :class:`NextTier` per rank group.

    Subphylum collapse (PR #2b): when the **parent is a phylum**
    and the children fetch returns only ``class``-rank rows (no
    subphylum / infraphylum / parvphylum / megaclass children at
    all), the resolver keeps the historical collapse to a single
    ``class`` tier so the cascade UI does not show an extra empty
    picker. When the phylum has any non-class children (subphylum,
    infraphylum, etc.) there is no collapse — the children groups
    themselves encode the right number of tiers.

    When the children list is empty, returns ``([], {}, None)`` so
    the cascade UI renders the leaf dropdown and the species-fetch
    effect kicks in.
    """
    # Single unranked children fetch.
    all_children = client.get_children(parent.taxon_id)
    if not all_children:
        return [], {}, None

    # Group by rank, preserving CLB's natural order.
    grouped: dict[str, list[ChecklistBankTaxon]] = {}
    order: list[str] = []
    for child in all_children:
        rank_key = (child.rank or "").lower()
        if rank_key not in grouped:
            grouped[rank_key] = []
            order.append(rank_key)
        grouped[rank_key].append(child)

    # Subphylum collapse rule (PR #2b): a phylum whose only
    # children are class-rank collapses to a single class tier.
    parent_rank = (parent.rank or "").lower()
    if parent_rank == "phylum" and len(grouped) == 1 and "class" in grouped:
        # Already collapsed: only the "class" group exists. Emit
        # one NextTier per the existing rule so the UI does not
        # show an extra empty picker.
        collapsed_grouped: dict[str, list[ChecklistBankTaxon]] = {"class": grouped["class"]}
        tiers = [_build_tier("class", collapsed_grouped["class"])]
        flat = list(collapsed_grouped["class"])
        return flat, collapsed_grouped, tiers

    # No collapse: one NextTier per rank group, in CLB's order.
    tiers = [_build_tier(rank_key, grouped[rank_key]) for rank_key in order]
    return list(all_children), grouped, tiers


def _build_tier(rank: str, children: list[ChecklistBankTaxon]) -> NextTier:
    """Build a :class:`NextTier` from a rank key + child list."""
    return NextTier(
        rank=rank,
        label=_capitalize(rank),
        examples=[child.canonical_name for child in children[:3]],
        children=list(children),
    )


def _capitalize(s: str) -> str:
    """Capitalise the first character of ``s`` (lowercase the rest kept).

    Used to derive a user-facing dropdown label from a CLB rank
    string (``"infraphylum"`` → ``"Infraphylum"``).
    """
    if not s:
        return s
    return s[0].upper() + s[1:]


__all__ = [
    "CASCADE_TIERS",
    "TIER_DEPTH",
    "NextTier",
    "PathChildrenResponse",
    "list_path_children",
]
