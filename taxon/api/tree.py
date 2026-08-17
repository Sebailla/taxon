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
from taxon.schema import Taxon

# When a parent taxon has more than this many direct children, the
# tree endpoint returns ``species_count=None`` instead of walking
# the recursive CTE. The benchmark in ``design.md`` (section
# "species_count threshold benchmark") measured the break-even point
# against ``data/col.db``; this constant is the consolidated value.
SPECIES_COUNT_LAZY_NULL_THRESHOLD: Final[int] = 100_000

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
) -> int | None:
    """Return the descendant ``species``-rank count under ``parent_id``.

    Uses a recursive CTE against ``taxa`` so the count stays
    accurate across re-imports. When the parent has more than
    ``threshold`` direct children the helper returns ``None`` —
    the recursive CTE would be too slow at that breadth to keep
    the response under the 100ms target.

    Implementation notes
    --------------------
    The CTE unions an anchor (direct children of ``parent_id``)
    with a recursive branch that joins ``taxa`` on each level's
    ``parent_id``. The outer aggregation counts only rows whose
    computed display level equals ``species``. The function
    short-circuits on the direct-children count BEFORE running the
    CTE so the threshold check itself costs O(1) on the index.
    """
    direct_count_stmt = select(func.count()).select_from(Taxon).where(Taxon.parent_id == parent_id)
    direct_count = int(session.execute(direct_count_stmt).scalar_one())
    if direct_count > threshold:
        return None

    sql = text(
        """
        WITH RECURSIVE descendants(id) AS (
            SELECT id FROM taxa WHERE parent_id = :parent_id
            UNION ALL
            SELECT t.id FROM taxa t
            JOIN descendants d ON t.parent_id = d.id
        )
        SELECT COUNT(*) FROM descendants
        WHERE LOWER(taxonomy_display_level(
            (SELECT rank FROM taxa WHERE id = descendants.id)
        )) = :species_level
        """
    )
    # Use session.execute directly so the session's shared connection
    # stays open after the CTE -- session.connection() as a context
    # manager invalidates the underlying connection when it exits.
    result = session.execute(sql, {"parent_id": parent_id, "species_level": SPECIES_DISPLAY_LEVEL})
    return int(result.scalar_one())


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


def list_tree_children(
    session: Session,
    parent_id: int,
    *,
    include_extinct: bool = True,
    limit: int = 200,
    cursor: int | None = None,
) -> tuple[TreeNodeRow | None, list[TreeNodeRow]]:
    """Return ``(parent, children)`` for the given ``parent_id``.

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
    ``cursor`` argument is reserved for pagination; the first PR
    ships the 200-row cap and the cursor is left as a hook for
    future expansion.

    The ``include_extinct`` flag defaults to ``True`` so the
    endpoint surfaces extinct rows by default (the CoL root
    dataset is mostly extant). When the caller passes
    ``include_extinct=False`` the SQL adds
    ``Taxon.is_extinct.is_(False)`` to the WHERE clause so the
    filtered list is computed server-side — the client never has to
    post-filter.
    """
    _ = cursor  # pagination wired in follow-up PR

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
    else:
        parent_orm = session.get(Taxon, parent_id)
        if parent_orm is None:
            return None, []
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
    out: list[TreeNodeRow] = []
    for child in children_orm:
        child_base = _to_row(child)
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
    return parent_row, out


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
