"""Path-aware hierarchy resolver.

The original ``resolve_path`` walks a list of segments against a
hardcoded 6-rank ladder (kingdom → phylum → class → order →
family → genus). CoL introduces intermediate ranks (subphylum,
gigaclass, infraclass, superorder, parvorder, ...) that the
fixed ladder skips, so a request like
``/api/Animalia/Chordata/classes`` returns ``[]`` when the
children of Chordata are subphyla (Vertebrata, Cephalochordata,
Tunicata), not classes.

The functions in this module do not assume any rank order. They
take whatever segments the caller provides, walk them as case-
insensitive names anchored on the parent at each step, and
return the deepest resolved taxon. The router in
:mod:`taxon.api.router` exposes them as a single new endpoint
``GET /api/path-children?path=A|B|C``.

The 6-rank helpers in :mod:`taxon.api.hierarchy` remain
available for callers that still need them. Their deprecation
and removal is a follow-up PR; this commit is additive.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.api.hierarchy import TaxonRow, _to_row
from taxon.schema import Taxon


@dataclass(frozen=True)
class PathChildrenResponse:
    """Result of ``GET /api/path-children``.

    The ``parent`` row is the deepest taxon the path resolved to.
    The ``children`` are its direct children regardless of rank
    name. The ``next_rank_hint`` is the rank that appears most
    often among the children so the frontend can label the next
    dropdown; ``None`` when there are no children (leaf node).
    """

    parent: TaxonRow
    children: list[TaxonRow]
    next_rank_hint: str | None


def list_path_children(
    session: Session,
    segments: list[str],
) -> PathChildrenResponse | None:
    """Walk ``segments`` to the deepest resolved taxon and return its
    direct children.

    Returns ``None`` when the deepest segment does not resolve —
    the router maps that to a 404. Returns a
    :class:`PathChildrenResponse` whose ``children`` is the empty
    list when the deepest taxon has no children (the leaf case).

    The resolver does NOT validate ranks. Any segment that
    resolves case-insensitively as a direct child of the
    previous segment is accepted, regardless of rank. This is
    the change that lets the cascade UI follow paths like
    ``Animalia → Chordata → subphylum Vertebrata → class
    Actinopterygii`` without the resolver refusing the
    subphylum step.

    ``next_rank_hint`` is the mode of ``children[].rank`` so a
    heterogeneous set (a few subphyla + a handful of
    unranked microspecies) gets the rank that the frontend
    should show as the dropdown label. When children are empty,
    the hint is ``None``.
    """
    if not segments:
        return None

    parent_id: int | None = None
    current: TaxonRow | None = None

    for segment in segments:
        stmt = select(Taxon).where(func.lower(Taxon.name) == segment.lower())
        if parent_id is None:
            stmt = stmt.where(func.lower(Taxon.rank) == "kingdom")
        else:
            stmt = stmt.where(Taxon.parent_id == parent_id)
        candidate = session.scalars(stmt).first()
        if candidate is None:
            return None
        current = _to_row(candidate)
        parent_id = current.id

    # Current must be set because segments is non-empty and every
    # segment resolved above.
    assert current is not None

    children_stmt = (
        select(Taxon)
        .where(Taxon.parent_id == current.id)
        .order_by(func.lower(Taxon.name), Taxon.name)
    )
    child_rows = [_to_row(t) for t in session.scalars(children_stmt).all()]

    next_rank_hint: str | None = None
    if child_rows:
        rank_counts = Counter(child.rank for child in child_rows)
        next_rank_hint = rank_counts.most_common(1)[0][0]

    return PathChildrenResponse(
        parent=current,
        children=child_rows,
        next_rank_hint=next_rank_hint,
    )


__all__ = [
    "PathChildrenResponse",
    "list_path_children",
]
