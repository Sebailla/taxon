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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.api.hierarchy import (
    TaxonRow,
    _intermediate_ranks_for,
)
from taxon.api.schemas import (
    NextTier,
    TaxonResponse,
)
from taxon.schema import Taxon


def _capitalize(s: str) -> str:
    """Capitalise the first character of ``s`` (rest unchanged).

    Mirrors :func:`taxon.api.clb_path_children._capitalize` so the
    wire labels stay consistent across the CLB and SQLite backends.
    """
    if not s:
        return s
    return s[0].upper() + s[1:]


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


__all__ = [
    "_build_tier",
    "_build_tiers_from_grouping",
    "_capitalize",
    "_children_grouped_by_rank",
    "_collect_descendants_by_rank",
    "_family_rollup",
    "_phylum_rollup",
    "_row_to_dataclass",
]
