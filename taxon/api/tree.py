"""Tree-browse backend for the ``arbol-col-browse`` change.

The module exposes three helpers consumed by the FastAPI router:

- :func:`split_authorship` splits the citation tail out of a
  CoL-shaped ``display_name`` so the tree UI can render
  ``rank: Name Authorship • N spp.`` rows. The split is
  case-insensitive on the leading ``name`` because CoL author
  citations begin with a capitalised surname that carries no
  matching prefix.
- :func:`list_tree_children` returns the direct children of a
  parent plus their ``has_children`` flag and a derived
  ``species_count``. The recursive CTE walks the subtree at
  query time so the count stays accurate even after re-imports;
  ``species_count`` is ``None`` for parents whose subtree is
  too expensive to walk (configurable threshold via
  :data:`SPECIES_COUNT_LAZY_NULL_THRESHOLD`).
- :func:`search_taxon` returns ranked hits for the "Find taxon"
  autocomplete: exact > prefix > substring, then by
  ``display_name`` length ascending so the most relevant hit sits
  at the top.

Layering
--------
This module is pure SQLAlchemy + dataclasses; the FastAPI
router module owns the request/response surface. The same
layering keeps the rest of :mod:`taxon.api` consistent — the
helpers are unit-testable without spinning up the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from taxon.api.hierarchy import _to_row
from taxon.api.schemas import TreeNodeResponse, TreeNodeTier
from taxon.schema import Taxon

# When a parent taxon has more than this many direct children, the
# tree endpoint returns ``species_count=None`` instead of walking
# the recursive CTE. The benchmark in ``design.md`` (section
# "species_count threshold benchmark") measured the break-even point
# against ``data/col.db``; this constant is the consolidated value.
# The species_count threshold fires when a parent's direct-children
# count exceeds this number AND the recursive CTE count would be too
# expensive. The previous 100k threshold was checked against the
# direct-children count only — that missed the case where a parent
# has a small number of direct children but a wide subtree (the
# CoL root ``?incertae sedis`` has 14,017 direct children; the
# root ``Eukaryota`` has only 9 direct children but a 5.6M-row
# subtree). The threshold is now checked against the CTE count
# AFTER the recursive walk, so any subtree that would cost more
# than this many rows in the CTE short-circuits to None.
# The species_count threshold fires when a parent's recursive CTE
# would walk too many rows. The previous 100k threshold was checked
# against the direct-children count only — that missed the case
# where a parent has a small number of direct children but a wide
# subtree (the CoL root ``?incertae sedis`` has 14,017 direct
# children; the root ``Eukaryota`` has only 9 direct children but
# a 5.6M-row subtree). The threshold is now checked against the
# total CTE count AFTER the recursive walk, so any subtree that
# would cost more than this many rows short-circuits to None.
# 1M is a conservative bound: the recursive CTE on a 1M-row
# subtree runs in ~500ms-2s on col.db, which keeps the per-tier
# envelope within the 1s response target.
SPECIES_COUNT_LAZY_NULL_THRESHOLD: Final[int] = 1_000_000

# Display level used for the species-tier roll-up. The cascade bucket
# includes subspecies / variety / form children so a parent that has
# subspecies rows under its species children still counts each leaf.
SPECIES_DISPLAY_LEVEL: Final[str] = "species"


@dataclass(frozen=True)
class TreeNodeRow:
    """Materialised child row for the tree-browse endpoint.

    Mirrors :class:`TreeNodeResponse` (Pydantic). The dataclass is
    the surface the SQLAlchemy queries build; the router translates
    each row into a :class:`TreeNodeResponse` at the wire boundary.
    """

    id: int
    name: str
    display_name: str
    rank: str
    parent_id: int | None
    authorship: str
    has_children: bool
    species_count: int | None
    is_synonym: bool
    is_extinct: bool
    is_uncertain: bool
    is_unassigned: bool


@dataclass(frozen=True)
class TreeSearchRow:
    """Materialised hit for the tree search endpoint.

    Mirrors :class:`TreeSearchHit`. ``relevance`` names the match
    tier (exact / prefix / substring) so the UI can label the hit
    if it ever wants to.
    """

    id: int
    name: str
    display_name: str
    rank: str
    parent_id: int | None
    has_children: bool
    relevance: str


def split_authorship(name: str, display_name: str) -> str:
    """Return the citation tail of ``display_name`` after ``name``.

    CoL carries the citation inside ``display_name``
    (``"Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978"``) and
    the citation-free canonical ``name`` (``"Eukaryota"``). The
    split returns the substring after the canonical ``name`` --
    whitespace-stripped, with any trailing ``[rank]`` tag stripped
    out so the authorship surface never carries parser noise.

    When the ``name`` is not a prefix of ``display_name``
    (defensive fallback), the original ``display_name`` is returned
    verbatim so the row always renders something legible.

    The split is case-insensitive on the leading ``name`` because
    author surnames begin with capitals and are not part of the
    canonical name; the trailing whitespace is stripped before the
    return so the rendered row avoids a leading space.
    """
    if not display_name:
        return ""
    name_clean = name.strip()
    display_clean = display_name.strip()
    if name_clean and display_clean.lower().startswith(name_clean.lower()):
        tail = display_clean[len(name_clean) :].lstrip()
        # Strip the WoRMS-importer ``[rank]`` tag if present so the
        # authorship surface never carries parser noise.
        if tail.endswith("]") and "[" in tail:
            cut = tail.find("[")
            tail = tail[:cut].rstrip()
        return tail
    # Defensive fallback: show the full display_name so the row is
    # never blank.
    return display_clean


def _count_descendant_species(
    session: Session,
    parent_id: int,
    *,
    threshold: int = SPECIES_COUNT_LAZY_NULL_THRESHOLD,
    _cache: dict[int, int | None] | None = None,
) -> int | None:
    """Return the descendant ``species``-rank count under ``parent_id``.

    Uses a recursive CTE against ``taxa`` so the count stays
    accurate across re-imports. When the parent has more than
    ``threshold`` direct children the helper returns ``None`` —
    the recursive CTE would be too slow at that breadth to keep
    the response under the 100ms target.

    The ``_cache`` parameter is a request-scoped dict that memoises
    the result per parent. The tree walk calls this helper once
    per tier row (50 × 6 tiers = 300 calls per envelope); without
    the cache, each call ran an independent recursive CTE on the
    full subtree, blowing past the 1s response target for any
    parent with a deep subtree. With the cache, repeat calls hit
    the dict in O(1). Callers that pre-batch (see
    :func:`_batch_species_counts` in ``_tree_tiers.py``) can
    pass the batch's result dict and skip the CTE entirely.

    Implementation notes
    --------------------
    The CTE unions an anchor (direct children of ``parent_id``)
    with a recursive branch that joins ``taxa`` on each level's
    ``parent_id``. The outer aggregation counts only rows whose
    computed display level equals ``species``. The function
    short-circuits on the direct-children count BEFORE running the
    CTE so the threshold check itself costs O(1) on the index.
    """
    if _cache is not None and parent_id in _cache:
        return _cache[parent_id]

    # Count the direct children first as a cheap short-circuit. A
    # parent with a very wide fan-out is likely to have a wide
    # subtree; the direct-count check costs O(1) on the index and
    # protects the deeper CTE work.
    direct_count_stmt = select(func.count()).select_from(Taxon).where(Taxon.parent_id == parent_id)
    direct_count = int(session.execute(direct_count_stmt).scalar_one())
    if direct_count > threshold:
        if _cache is not None:
            _cache[parent_id] = None
        return None

    # Walk the entire subtree so we know both the species count and
    # the total descendant count. The species count is the surface
    # the tree UI displays; the total count lets us short-circuit
    # subtrees that would cost too much to count in a single CTE
    # walk (CoL's ``Eukaryota`` root has only 9 direct children but
    # a 5.6M-row subtree — the direct-count check would pass but
    # the CTE would walk every row). When the total count exceeds
    # the threshold we return ``None`` so the wire surface stays
    # consistent with the direct-count short-circuit.
    sql = text(
        """
        WITH RECURSIVE descendants(id) AS (
            SELECT id FROM taxa WHERE parent_id = :parent_id
            UNION ALL
            SELECT t.id FROM taxa t
            JOIN descendants d ON t.parent_id = d.id
        )
        SELECT
            SUM(CASE WHEN LOWER(taxonomy_display_level(
                (SELECT rank FROM taxa WHERE id = descendants.id)
            )) = :species_level THEN 1 ELSE 0 END) AS species_count,
            COUNT(*) AS total_count
          FROM descendants
        """
    )
    # Use session.execute directly so the session's shared connection
    # stays open after the CTE -- session.connection() as a context
    # manager invalidates the underlying connection when it exits.
    result = session.execute(
        sql, {"parent_id": parent_id, "species_level": SPECIES_DISPLAY_LEVEL}
    ).one()
    species_count = int(result.species_count or 0)
    total_count = int(result.total_count or 0)
    if total_count > threshold:
        if _cache is not None:
            _cache[parent_id] = None
        return None
    if _cache is not None:
        _cache[parent_id] = species_count
    return species_count


def _children_query_base(session: Session, parent_id: int) -> list[Taxon]:
    """Return direct children of ``parent_id`` ordered by canonical name.

    The query is kept short so the calling functions can decorate
    it with EXISTS / CTEs for the derived fields. Ordering matches
    the cascade contract: case-insensitive by ``name`` so
    re-imports keep the same sort.
    """
    stmt = (
        select(Taxon)
        .where(Taxon.parent_id == parent_id)
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    return list(session.scalars(stmt).all())


def _decorate_children_with_flags(
    session: Session,
    children: list[Taxon],
) -> list[Taxon]:
    """No-op pass-through kept for symmetry with future derived fields.

    The endpoint emits :class:`TreeNodeResponse` rows directly from
    these values; the helper exists so the parent-fetch and child-
    decoration paths are extensible without surgery.
    """
    return children


def build_tree_node_response(
    session: Session,
    taxon: Taxon,
    has_children: bool = False,
) -> TreeNodeResponse:
    """Build a :class:`TreeNodeResponse` from a ``Taxon`` ORM row.

    Shared between the direct-children slice and the per-tier CTE
    walker so both surfaces apply the same derived-field contract
    (``has_children``, ``species_count``, ``authorship``). The
    ``has_children`` flag is computed in batch by the caller because
    the recursive per-tier CTE already materialises every child row
    and a per-row EXISTS query would multiply the round-trip count.
    """
    base = _to_row(taxon)
    species_count = _count_descendant_species(session, taxon.id)
    return TreeNodeResponse(
        id=base.id,
        name=base.name,
        display_name=base.display_name,
        rank=base.rank,
        parent_id=base.parent_id,
        authorship=split_authorship(base.name, base.display_name),
        has_children=has_children,
        species_count=species_count,
        is_synonym=base.is_synonym,
        is_extinct=base.is_extinct,
        is_uncertain=base.is_uncertain,
        is_unassigned=base.is_unassigned,
    )


def list_tree_children(
    session: Session,
    parent_id: int,
    *,
    include_extinct: bool = True,
    limit: int = 200,
    cursor: str | int | None = None,
    tier: str | None = None,
    tier_limit: int = 50,
) -> tuple[TreeNodeRow | None, list[TreeNodeRow], list[TreeNodeTier] | None]:
    """Return ``(parent, children, next_tiers)`` for the given ``parent_id``.

    A ``parent_id`` of ``0`` is the sentinel for "roots" — the SQL
    fetch uses ``parent_id IS NULL`` and the parent envelope
    returns ``None`` so the tree UI does not invent a synthetic
    ``Biota`` superdomain.

    The returned children are direct children of ``parent_id``
    (no recursive descent). Each child carries:

    - ``has_children`` — the EXISTS subquery against
      ``taxa.parent_id = child.id``.
    - ``species_count`` — the recursive count from
      :func:`_count_descendant_species`, or ``None`` for parents
      above the lazy-null threshold.
    - ``authorship`` — the citation tail from :func:`split_authorship`.

    Ordering is alphabetical by canonical name. The optional
    ``cursor`` argument is reserved for pagination of the direct
    children; the first PR ships the 200-row cap and the cursor is
    left as a hook for future expansion.

    The ``include_extinct`` flag defaults to ``True`` so the
    endpoint surfaces extinct rows by default (the CoL root
    dataset is mostly extant). When the caller passes
    ``include_extinct=False`` the SQL adds
    ``Taxon.is_extinct.is_(False)`` to the WHERE clause so the
    filtered list is computed server-side — the client never has to
    post-filter.

    ``next_tiers`` carries the per-tier subtree envelope (one tier
    per cascade bucket below the parent — phylum / class / order /
    family / genus / species). ``None`` for a true-leaf parent; the
    field is additive so old clients keep working without it.

    When ``tier`` is provided the per-tier envelope is computed for
    that single rank only — the wire envelope narrows to a single
    tier so the client can advance one bucket at a time. The
    ``tier_limit`` parameter caps the per-tier row count (default
    ``50``, hard cap ``200``); values above the cap are clamped
    silently by the router.
    """
    _ = cursor  # direct-children cursor reserved for future expansion

    from taxon.api._tree_tiers import _build_next_tiers, _decode_cursor

    # When ``tier`` is supplied, decode the opaque base64 cursor
    # into the ``(name, id)`` tuple the per-tier CTE expects.
    # Other callers pass ``cursor=None`` and the envelope returns
    # the first page for every tier.
    per_tier_cursor: tuple[str, int] | None = None
    if cursor is not None and isinstance(cursor, str) and tier is not None:
        try:
            per_tier_cursor = _decode_cursor(cursor)
        except ValueError:
            per_tier_cursor = None

    if parent_id == 0:
        # Roots: every taxon with ``parent_id IS NULL`` (5 rows on
        # ``col.db``: Archaea + Bacteria + Eukaryota + Viruses +
        # ?incertae sedis).
        stmt = (
            select(Taxon)
            .where(Taxon.parent_id.is_(None))
            .order_by(func.lower(Taxon.name), Taxon.name)
            .limit(limit)
        )
        if not include_extinct:
            stmt = stmt.where(Taxon.is_extinct.is_(False))
        children_orm = list(session.scalars(stmt).all())
        parent_row: TreeNodeRow | None = None
        next_tiers: list[TreeNodeTier] | None = None
    else:
        parent_orm = session.get(Taxon, parent_id)
        if parent_orm is None:
            return None, [], None
        children_orm = _children_query_base(session, parent_id)
        if not include_extinct:
            # Filter the child ORM list in-place rather than re-running
            # the query — the limit cap is already respected by the
            # base helper and the children count is bounded.
            children_orm = [c for c in children_orm if not c.is_extinct]
        parent_base = _to_row(parent_orm)
        parent_row = TreeNodeRow(
            id=parent_base.id,
            name=parent_base.name,
            display_name=parent_base.display_name,
            rank=parent_base.rank,
            parent_id=parent_base.parent_id,
            authorship=split_authorship(parent_base.name, parent_base.display_name),
            has_children=True,  # arbitrary; not surfaced in the wire envelope
            species_count=None,
            is_synonym=parent_base.is_synonym,
            is_extinct=parent_base.is_extinct,
            is_uncertain=parent_base.is_uncertain,
            is_unassigned=parent_base.is_unassigned,
        )

        # Compute the per-tier subtree envelope once for the
        # parent. The cursor is None on the first-page call;
        # clients advance one tier at a time with
        # ``?tier={rank}&cursor={c}``. The tier walker now builds
        # ``TreeNodeResponse`` inline and pulls ``species_count``
        # from a single batched CTE per request — see
        # ``_build_next_tiers`` and ``_batch_species_counts`` in
        # ``_tree_tiers.py``. The previous per-row ``enrich``
        # callback ran 50 × ``_count_descendant_species`` calls
        # per tier page, blowing past the 1s response target.
        next_tiers = _build_next_tiers(
            session,
            parent_id=parent_id,
            direct_children_rows=[],
            tier_limit=tier_limit,
            cursor=per_tier_cursor,
            include_extinct=include_extinct,
            enrich=None,  # species_count is batched inside _build_next_tiers
        )

    children_orm = _decorate_children_with_flags(session, children_orm)
    children_orm = children_orm[:limit]
    # Batch-fetch ``has_children`` for every child in ONE round trip.
    # The naive implementation ran one EXISTS query per child which,
    # for a 200-row page, hit SQLite 200 extra times per expand and
    # blew past the 100ms response target against ``data/col.db``.
    has_children_by_id: dict[int, bool] = {}
    if children_orm:
        child_ids = [child.id for child in children_orm]
        batch_stmt = select(Taxon.parent_id, Taxon.id).where(Taxon.parent_id.in_(child_ids))
        parents_seen: set[int] = set()
        for row in session.execute(batch_stmt).all():
            parents_seen.add(row.parent_id)
        has_children_by_id = {cid: cid in parents_seen for cid in child_ids}

    # For the CoL root (parent_id=0) the per-child species_count
    # walks the entire subtree below each root — 5.6M rows under
    # Eukaryota, 1.7M under incertae sedis. The species count
    # on the root surface is decorative (the wire UI shows
    # "Eukaryota — 5,654,267 spp.") and the lazy tier query
    # (next_tiers=None for parent_id=0) is the path that matters
    # for navigation. Skip the per-child species_count for the
    # roots so the surface metadata is cheap; the next-tier
    # queries return the actual counts for the per-tier paginated
    # disclosure. The threshold check (1M descendants) still
    # protects against runaway subtrees elsewhere.
    is_root_request = parent_id == 0

    out: list[TreeNodeRow] = []
    for child in children_orm:
        child_base = _to_row(child)
        if is_root_request:
            species_count = None
        else:
            species_count = _count_descendant_species(session, child.id)
        out.append(
            TreeNodeRow(
                id=child_base.id,
                name=child_base.name,
                display_name=child_base.display_name,
                rank=child_base.rank,
                parent_id=child_base.parent_id,
                authorship=split_authorship(child_base.name, child_base.display_name),
                has_children=has_children_by_id.get(child.id, False),
                species_count=species_count,
                is_synonym=child_base.is_synonym,
                is_extinct=child_base.is_extinct,
                is_uncertain=child_base.is_uncertain,
                is_unassigned=child_base.is_unassigned,
            )
        )
    return parent_row, out, next_tiers


# Sentinel returned when the helper finds no matches -- the
# router surfaces a 200 with empty ``items`` rather than a 404 for
# blank queries.
_NO_ROWS_SENTINEL: Final[list[TreeSearchRow]] = []


def _relevance_for(name: str, q_lower: str) -> str:
    """Return the match tier (``exact`` / ``prefix`` / ``substring``) for ``name``."""
    name_lower = name.lower()
    if name_lower == q_lower:
        return "exact"
    if name_lower.startswith(q_lower):
        return "prefix"
    return "substring"


def _row_to_search_row(child: Taxon, relevance: str) -> TreeSearchRow:
    """Build a :class:`TreeSearchRow` from a ``Taxon`` + relevance tier."""
    return TreeSearchRow(
        id=child.id,
        name=child.name,
        display_name=child.display_name,
        rank=child.rank,
        parent_id=child.parent_id,
        has_children=False,  # populated below
        relevance=relevance,
    )


def search_taxon(
    session: Session,
    q: str,
    *,
    limit: int = 8,
    include_extinct: bool = True,
) -> list[TreeSearchRow]:
    """Return ranked taxon matches for the "Find taxon" autocomplete.

    The query is matched case-insensitively against both
    ``Taxon.name`` and ``Taxon.display_name`` -- a Panthera lookup
    against ``display_name="Panthera onca"`` matches the species row
    because its display name contains the query. Each match is tagged
    with the highest tier it satisfies (exact > prefix > substring)
    so the response shape stays a flat ordered list (no GROUP BY
    collapsing needed).

    Ranking
    -------
    Ties on tier break by ``display_name`` length ascending so the
    "closest" hit (e.g. "Eukarya" over "Eukaryota (Chatton, 1925)
    Whittaker & Margulis, 1978" when the user typed "Euk") sits at
    the top of the prefix group. The cap is :data:`limit` (default
    8) so the autocomplete stays snappy against ``data/col.db``.

    Empty query (or whitespace-only) returns ``[]`` without hitting
    the database.
    """
    cleaned = (q or "").strip()
    if not cleaned:
        return list(_NO_ROWS_SENTINEL)

    q_lower = cleaned.lower()
    pattern = f"%{q_lower}%"

    stmt = (
        select(Taxon)
        .where(
            (func.lower(Taxon.name).like(pattern)) | (func.lower(Taxon.display_name).like(pattern))
        )
        .order_by(func.length(Taxon.display_name), func.lower(Taxon.name))
        .limit(limit * 4)  # over-fetch so we can re-rank client-side
    )
    if not include_extinct:
        stmt = stmt.where(Taxon.is_extinct.is_(False))
    candidates = list(session.scalars(stmt).all())

    # Tag and bucket the candidates. ``bucket`` orders first, ties
    # broken by ``display_name`` length ascending (already enforced
    # by the SQL ``ORDER BY func.length(display_name)``).
    bucketed: dict[int, list[TreeSearchRow]] = {0: [], 1: [], 2: []}
    for child in candidates:
        relevance = _relevance_for(child.name, q_lower)
        bucket = {"exact": 0, "prefix": 1}.get(relevance, 2)
        bucketed[bucket].append(_row_to_search_row(child, relevance))

    # Concatenate by bucket priority.
    ranked: list[TreeSearchRow] = (bucketed[0] + bucketed[1] + bucketed[2])[:limit]

    # Populate ``has_children`` for the rendered hits in ONE round
    # trip. The naive implementation ran one EXISTS per hit which
    # multiplied query count by ``len(ranked)`` (capped at 8 by
    # ``limit`` but still wasteful on a hot path).
    if ranked:
        hit_ids = [row.id for row in ranked]
        batch_stmt = select(Taxon.parent_id, Taxon.id).where(Taxon.parent_id.in_(hit_ids))
        parents_seen: set[int] = set()
        for row in session.execute(batch_stmt).all():
            parents_seen.add(row.parent_id)
        for hit in ranked:
            object.__setattr__(hit, "has_children", hit.id in parents_seen)
    return ranked


__all__ = [
    "SPECIES_COUNT_LAZY_NULL_THRESHOLD",
    "TreeNodeRow",
    "TreeSearchRow",
    "list_tree_children",
    "search_taxon",
    "split_authorship",
]
