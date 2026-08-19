"""Shared roll-up helpers for the tree-browse and cascade-resolver endpoints.

The :mod:`taxon.api.sqlite_resolver` and :mod:`taxon.api.tree` modules
both need the same off-tuple visibility rules: phylum → class roll-up,
subphylum collapse, family → genus roll-up, and the per-tier grouping
that drives ``next_tiers`` envelopes on the wire. The rules are
collected here so the two endpoints share a single source of truth and
the cascade and tree browse agree on "Archaea → Nanoarchaeota is
phylum" without duplicating the roll-up logic.

Layering
--------
This module is pure SQLAlchemy + dataclasses; it never imports FastAPI
and the helpers are unit-testable without spinning up the API.
:mod:`taxon.api.sqlite_resolver` re-exports the public names so its
existing import surface (``_phylum_rollup``, ``_family_rollup``,
``_collect_descendants_by_rank``, ``_build_tiers_from_grouping``,
``_build_tier``, ``_children_grouped_by_rank``, ``_capitalize``) is
preserved; :mod:`taxon.api.tree` imports the same names directly so
the per-tier recursive CTE walker in :mod:`taxon.api.tree` shares the
roll-up behaviour with the cascade resolver.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Final

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from taxon.api.hierarchy import (
    TaxonRow,
    _intermediate_ranks_for,
)
from taxon.api.schemas import (
    NextTier,
    TaxonResponse,
    TreeNodeResponse,
    TreeNodeTier,
)
from taxon.schema import Taxon

# Tier-ranks in cascade order. Each rank bucket below a parent is the
# tier group the wire envelope exposes; the helper iterates this list
# in order so the cascade UI renders tiers in the canonical
# top-down order. The list intentionally excludes ``realm`` and
# ``kingdom`` because the tree endpoint never emits those ranks
# (the path-resolver handles them via ``Biota``/``Viruses``).
_TIER_RANKS_IN_CASCADE_ORDER: Final[tuple[str, ...]] = (
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)

# Hard cap on the per-tier recursive CTE depth. The 57s cliff in
# issue #76 came from unbounded CASE evaluation; ``max_depth=8`` is
# the documented bound that keeps the per-tier query under the
# 50ms p95 target against ``data/col.db``.
_TIER_WALK_MAX_DEPTH: Final[int] = 8


def _capitalize(s: str) -> str:
    """Capitalise the first character of ``s`` (rest unchanged).

    Mirrors :func:`taxon.api.clb_path_children._capitalize` so the
    wire labels stay consistent across the CLB and SQLite backends.
    """
    if not s:
        return s
    return s[0].upper() + s[1:]


# Ranks whose plural label drops the trailing ``-s`` because the rank
# already ends in ``s``. Spec requirement
# ``subtree-envelope §"label capitalisation for plurals"``: edge
# cases ``species → Species``, ``subspecies → Subspecies``.
_PLURAL_LABEL_NO_SUFFIX: Final[frozenset[str]] = frozenset({"species", "subspecies"})

# Explicit irregular-plural map for ranks whose English plural does
# not follow the simple ``+s`` rule. The cascade UI renders these
# labels verbatim, so the helper hard-codes the canonical forms
# (``phylum → Phyla``) rather than relying on locale-aware rules.
_PLURAL_LABEL_IRREGULAR: Final[dict[str, str]] = {
    "phylum": "Phyla",
    "family": "Families",
    "class": "Classes",
    "order": "Orders",
    "genus": "Genera",
}


def _plural_label(rank: str) -> str:
    """Build the human-facing plural label for a tier rank.

    Most ranks pluralise with the suffix ``-s``
    (``class → Classes``); ranks that already end in ``s`` drop the
    suffix (``species → Species``); a few ranks carry an irregular
    plural that matches the cascade UI's existing convention
    (``phylum → Phyla``, ``genus → Genera``). The result is the wire
    label the cascade UI renders on the tier group header.
    """
    if rank in _PLURAL_LABEL_IRREGULAR:
        return _PLURAL_LABEL_IRREGULAR[rank]
    base = _capitalize(rank)
    if rank.lower() in _PLURAL_LABEL_NO_SUFFIX:
        return base
    return f"{base}s"


def _children_grouped_by_rank(
    session: Session,
    parent_id: int,
) -> dict[str, list[TaxonRow]]:
    """Fetch every direct child of ``parent_id`` grouped by rank.

    A plain query without a ``display_level`` filter so off-tuple
    ranks surface in the grouping; the roll-up helpers decide which
    groups to collapse. Returns a dict keyed by lower-cased rank.
    """
    stmt = (
        select(Taxon)
        .where(Taxon.parent_id == parent_id)
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    grouped: dict[str, list[TaxonRow]] = {}
    for child in session.scalars(stmt).all():
        grouped.setdefault(child.rank.lower(), []).append(_row_to_dataclass(child))
    return grouped


def _row_to_dataclass(taxon: Taxon) -> TaxonRow:
    """Convert a SQLAlchemy ``Taxon`` row into a :class:`TaxonRow`.

    Mirrors :func:`taxon.api.hierarchy._to_row` but is duplicated here
    so this module stays decoupled from the legacy rank-anchored
    resolver. Both helpers produce identical dataclasses.
    """
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


# Rank-by-rank roll-up rules. Each helper takes the children grouped
# by their actual rank and returns the wire-shaped grouping plus the
# tier list. The wire envelope exposes one tier per group; the roll-up
# helpers collapse intermediate ranks into a single tier so the
# cascade UI does not render empty dropdowns for off-tuple ranks.


def _phylum_rollup(
    session: Session,
    children_by_rank: dict[str, list[TaxonRow]],
) -> tuple[dict[str, list[TaxonRow]], list[NextTier] | None]:
    """Apply Rule 1 + Rule 2 to a phylum parent's children.

    Rule 1 fires when the phylum has any child at the off-tuple
    intermediate ranks (subphylum / infraphylum / parvphylum /
    microphylum / megaclass). The resolver descends through every
    intermediate child breadth-first until it reaches the
    ``class`` rank — multi-level descent handles real-world datasets
    that nest intermediates several tiers deep (e.g. Chordata →
    Vertebrata → Gnathostomata → Osteichthyes → Tetrapoda →
    Mammalia). Rule 2 fires when the phylum has only direct
    ``class`` children — the resolver still emits a single ``class``
    tier but skips the recursion.
    """
    intermediates = _intermediate_ranks_for("phylum")
    has_intermediates = any(rank in intermediates for rank in children_by_rank)

    if not has_intermediates:
        if "class" in children_by_rank and len(children_by_rank) == 1:
            class_children = children_by_rank["class"]
            return (
                {"class": class_children},
                [_build_tier("class", class_children)],
            )
        return children_by_rank, None

    aggregated_classes: list[TaxonRow] = _collect_descendants_by_rank(
        session,
        start_nodes=[child for rank in intermediates for child in children_by_rank.get(rank, [])],
        target_rank="class",
        intermediate_ranks=tuple(sorted(intermediates)),
    )
    aggregated_classes.extend(children_by_rank.get("class", []))

    if aggregated_classes:
        aggregated_classes = sorted(aggregated_classes, key=lambda r: (r.name.lower(), r.name))
        return (
            {"class": aggregated_classes},
            [_build_tier("class", aggregated_classes)],
        )

    return children_by_rank, None


def _family_rollup(
    session: Session,
    children_by_rank: dict[str, list[TaxonRow]],
) -> tuple[dict[str, list[TaxonRow]], list[NextTier] | None]:
    """Apply Rule 3 to a family parent's children.

    When the family has any child at the off-tuple intermediate
    ranks (subfamily / tribe / subtribe / infratribe), the resolver
    descends breadth-first through each, collects the ``genus``-rank
    descendants, and emits a single ``genus`` tier. When no
    ``genus`` descendants exist (e.g. a fossil family whose
    subfamily leaves are also leaves), the resolver falls back to
    the per-rank-group behaviour so the cascade UI renders the
    subfamily dropdown.
    """
    intermediates = _intermediate_ranks_for("family")
    has_intermediates = any(rank in intermediates for rank in children_by_rank)
    if not has_intermediates:
        return children_by_rank, None

    aggregated_genera: list[TaxonRow] = _collect_descendants_by_rank(
        session,
        start_nodes=[child for rank in intermediates for child in children_by_rank.get(rank, [])],
        target_rank="genus",
        intermediate_ranks=tuple(sorted(intermediates)),
    )

    if aggregated_genera:
        return (
            {"genus": aggregated_genera},
            [_build_tier("genus", aggregated_genera)],
        )
    return children_by_rank, None


def _collect_descendants_by_rank(
    session: Session,
    start_nodes: list[TaxonRow],
    *,
    target_rank: str,
    intermediate_ranks: tuple[str, ...],
) -> list[TaxonRow]:
    """Walk the subtree breadth-first and aggregate every ``target_rank`` descendant.

    The helper terminates when a level yields no new intermediate
    children — defensive against datasets that grow an extra rank
    not listed in ``intermediate_ranks``. The returned order mirrors
    the order each level emits the children so the cascade UI renders
    the genus dropdown in the same sequence the user would see in a
    tree walk.
    """
    if not start_nodes:
        return []
    collected: list[TaxonRow] = []
    frontier = list(start_nodes)
    intermediate_set = set(intermediate_ranks)
    while frontier:
        next_frontier: list[TaxonRow] = []
        for node in frontier:
            children = _children_grouped_by_rank(session, node.id)
            for rank, group in children.items():
                if rank == target_rank:
                    collected.extend(group)
                elif rank in intermediate_set:
                    next_frontier.extend(group)
        if not next_frontier:
            break
        frontier = next_frontier
    return collected


def _build_tiers_from_grouping(
    grouping: dict[str, list[TaxonRow]],
) -> list[NextTier]:
    """Build one :class:`NextTier` per rank group.

    The tier order mirrors the rank order within the grouping so the
    cascade UI renders dropdowns in the dataset's natural order. The
    ``label`` is the capitalised rank; ``examples`` carry up to three
    canonical names for tooltips.
    """
    tiers: list[NextTier] = []
    for rank, value in grouping.items():
        tiers.append(_build_tier(rank, value))
    return tiers


def _build_tier(rank: str, children: list[TaxonRow]) -> NextTier:
    """Build a single :class:`NextTier` from a rank label and its children."""
    return NextTier(
        rank=rank,
        label=_capitalize(rank),
        examples=[child.name for child in children[:3]],
        children=[TaxonResponse.model_validate(child) for child in children],
    )


# ---------------------------------------------------------------------------
# Per-tier recursive CTE walk (PR A.1 of #76)
# ---------------------------------------------------------------------------


def _encode_cursor(name: str, id: int) -> str:
    """Encode the per-tier pagination cursor as opaque base64.

    The cursor encodes both the canonical ``name`` and the row ``id``
    so re-imports that renumber ids can be tolerated by skipping
    rows whose ``id`` no longer matches the cursor's id (see the
    ``Cursor stability across re-imports`` requirement in
    ``index-and-performance.md``). The separator is the NUL byte so
    canonical names containing ``:`` or other safe characters round-
    trip without ambiguity.

    The encoded value is opaque to the client; it MUST NOT be parsed
    or interpreted by anything but :func:`_decode_cursor`.
    """
    raw = f"{name}\x00{id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, int]:
    """Decode the opaque per-tier cursor into ``(name, id)``.

    Inverse of :func:`_encode_cursor`. Raises :class:`ValueError`
    when the cursor cannot be parsed — the router translates that
    into a 400 so a malformed cursor never crashes the resolver.
    The split is on the first NUL byte so canonical names carrying
    any other character round-trip without ambiguity.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = raw.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"invalid cursor: {cursor!r}") from exc
    separator_idx = decoded.find("\x00")
    if separator_idx < 0:
        raise ValueError(f"invalid cursor: {cursor!r}")
    name = decoded[:separator_idx]
    id_str = decoded[separator_idx + 1 :]
    try:
        row_id = int(id_str)
    except ValueError as exc:
        raise ValueError(f"invalid cursor: {cursor!r}") from exc
    return name, row_id


def _per_tier_walk(
    session: Session,
    parent_id: int,
    tier_ranks: tuple[str, ...],
    *,
    max_depth: int = _TIER_WALK_MAX_DEPTH,
    tier_limit: int = 50,
    cursor: tuple[str, int] | None = None,
    include_extinct: bool = True,
) -> list[Taxon]:
    """Walk the per-tier subtree under ``parent_id`` with a recursive CTE.

    Returns the ORM ``Taxon`` rows (NOT dataclasses) so the caller
    can enrich them with derived fields (``has_children``,
    ``species_count``, ``authorship``) the same way the
    direct-children slice does.

    The query pins ``rank IN :tier_ranks`` so the working set is
    bounded per cascade bucket — the 57s cliff in issue #76 came
    from evaluating CASE branches across every descendant rank. The
    CTE depth caps at ``max_depth`` (default 8) so pathological
    hierarchies terminate in a bounded number of hops.

    Ordering matches the per-tier ``ORDER BY LOWER(name), name`` so
    pagination round-trips deterministically. The optional
    ``cursor`` advances the window past rows whose ``(name, id)``
    tuple is strictly greater than the cursor's tuple (the same
    tie-break rule the species-list endpoint uses).

    The ``include_extinct`` flag mirrors the direct-children
    contract: ``True`` (default) preserves current behaviour; when
    ``False`` the SQL adds an ``is_extinct = false`` predicate so the
    filter applies to tier rows as well as direct children (see the
    ``include_extinct filter`` requirement in
    ``index-and-performance.md``).
    """
    if not tier_ranks:
        return []

    # Over-fetch by one so the caller can detect "more rows exist"
    # without a second round trip; the caller slices back to
    # ``tier_limit`` after the cursor decision.
    fetch_limit = tier_limit + 1

    extinct_clause = "" if include_extinct else " AND t.is_extinct = 0 "

    if cursor is not None:
        after_name, after_id = cursor
        # Advance past rows whose (name, id) tuple is strictly
        # greater than the cursor's tuple, with ``id`` as the
        # tie-break (same shape the species-list endpoint uses).
        cursor_clause = (
            " AND (lower(t.name) > :after_name "
            "      OR (lower(t.name) = :after_name AND t.id > :after_id)) "
        )
    else:
        cursor_clause = ""

    sql_text = (
        """
        WITH RECURSIVE tier_descendants(id, depth) AS (
            SELECT child.id, 0
              FROM taxa AS child
              WHERE child.parent_id = :parent_id
            UNION ALL
            SELECT next_child.id, td.depth + 1
              FROM taxa AS next_child
              JOIN tier_descendants AS td ON next_child.parent_id = td.id
              WHERE td.depth < :max_depth
        )
        SELECT t.id
          FROM taxa AS t
          JOIN tier_descendants AS d ON t.id = d.id
          WHERE lower(t.rank) IN :tier_ranks
        """
        + extinct_clause
        + cursor_clause
        + " ORDER BY lower(t.name), t.name LIMIT :tier_limit"
    )

    stmt = text(sql_text).bindparams(bindparam("tier_ranks", expanding=True))

    params: dict[str, object] = {
        "parent_id": parent_id,
        "tier_ranks": tuple(tier_ranks),
        "max_depth": max_depth,
        "tier_limit": fetch_limit,
    }
    if cursor is not None:
        params["after_name"] = after_name.lower()
        params["after_id"] = after_id

    id_rows = session.execute(stmt, params).all()
    if not id_rows:
        return []
    # Re-fetch the ORM rows by id so the caller can use the same
    # enrichment path as the direct-children slice. The list
    # preserves the CTE ordering (case-insensitive by name).
    ids_ordered = [int(row.id) for row in id_rows]
    fetched = session.scalars(select(Taxon).where(Taxon.id.in_(ids_ordered))).all()
    by_id = {t.id: t for t in fetched}
    return [by_id[tid] for tid in ids_ordered if tid in by_id]


def _build_next_tiers(
    session: Session,
    parent_id: int,
    direct_children_rows: list[TaxonRow],
    *,
    tier_limit: int = 50,
    cursor: tuple[str, int] | None = None,
    include_extinct: bool = True,
    max_depth: int = _TIER_WALK_MAX_DEPTH,
    enrich: Callable[[Taxon], TreeNodeResponse] | None = None,
) -> list[TreeNodeTier] | None:
    """Build the per-tier envelope for ``GET /api/tree/children``.

    Returns one :class:`TreeNodeTier` per cascade bucket below the
    parent, in cascade-rank order. Empty tiers are omitted (the spec
    pins "ranks with zero rows SHALL be omitted from the DOM"). A
    parent with no descendants at any rank returns ``None`` so the
    envelope stays additive — old clients see ``next_tiers: null``.

    The ``enrich`` callback converts each ``Taxon`` ORM row into a
    :class:`TreeNodeResponse` carrying the derived fields the tree UI
    needs (``has_children``, ``species_count``, ``authorship``). The
    caller (the router) passes the same enrichment helper it uses
    for the direct-children slice so both envelopes share the same
    derived-field contract.

    The :func:`_phylum_rollup` / :func:`_family_rollup` rules apply
    so off-tuple intermediates (subphylum / infraphylum / etc.) fold
    into the parent bucket the same way they do for the cascade
    endpoint — the wire shape stays symmetric with
    ``GET /api/path-children``.
    """
    _ = direct_children_rows  # accepted for signature parity; unused

    children_by_rank = _children_grouped_by_rank(session, parent_id)
    if not children_by_rank:
        return None

    parent_row: TaxonRow | None = None
    parent = session.get(Taxon, parent_id)
    if parent is not None:
        parent_row = _row_to_dataclass(parent)

    # Apply the roll-up rules when the parent is a phylum or family.
    grouping = children_by_rank
    if parent_row is not None and parent_row.rank.lower() == "phylum":
        grouping, _ = _phylum_rollup(session, children_by_rank)
    elif parent_row is not None and parent_row.rank.lower() == "family":
        grouping, _ = _family_rollup(session, children_by_rank)

    if not grouping:
        return None

    tiers: list[TreeNodeTier] = []
    for rank in _TIER_RANKS_IN_CASCADE_ORDER:
        rows = _per_tier_walk(
            session,
            parent_id=parent_id,
            tier_ranks=(rank,),
            max_depth=max_depth,
            tier_limit=tier_limit,
            cursor=cursor,
            include_extinct=include_extinct,
        )
        if not rows:
            continue

        # ``_per_tier_walk`` over-fetches by one so we can detect
        # "more rows exist" without a second round trip.
        over_fetched = len(rows) > tier_limit
        page_rows = rows[:tier_limit]
        next_cursor: str | None = None
        if over_fetched:
            last = page_rows[-1]
            next_cursor = _encode_cursor(last.name, int(last.id))

        if enrich is None:
            raise ValueError(
                "enrich callback is required so tier rows carry the derived "
                "TreeNodeResponse fields (has_children, species_count, authorship)"
            )
        child_responses = [enrich(row) for row in page_rows]

        tiers.append(
            TreeNodeTier(
                rank=rank,
                label=_plural_label(rank),
                examples=[row.name for row in page_rows[:3]],
                children=child_responses,
                next_cursor=next_cursor,
            )
        )

    return tiers or None


__all__ = [
    "_TIER_RANKS_IN_CASCADE_ORDER",
    "_TIER_WALK_MAX_DEPTH",
    "_build_next_tiers",
    "_build_tier",
    "_build_tiers_from_grouping",
    "_capitalize",
    "_children_grouped_by_rank",
    "_collect_descendants_by_rank",
    "_decode_cursor",
    "_encode_cursor",
    "_family_rollup",
    "_per_tier_walk",
    "_phylum_rollup",
    "_plural_label",
    "_row_to_dataclass",
]
