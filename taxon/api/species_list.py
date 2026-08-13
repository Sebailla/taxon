"""Path-aware species resolver.

The legacy six-fixed-rank endpoint at
``/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species``
does not work for CoL paths that contain intermediate ranks
(subphylum, gigaclass, infraphylum, etc.). CoL's Gadus, for
example, sits under a 12-segment path that includes
gigaclass → superclass → class → subclass → infraclass →
magnorder → superorder → order → suborder → infraorder → parvorder
→ ... → genus.

This module exposes a single endpoint ``GET /api/species-list?path=``
that walks the caller-supplied path (the same shape as
``/api/path-children``), resolves the deepest taxon case-
insensitively, and returns its species-rank children paginated.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.api.schemas import SpeciesListItem
from taxon.api.species import list_species_page, parse_include
from taxon.schema import Taxon


def list_species_at_path(
    session: Session,
    segments: list[str],
    *,
    include: str | None,
    cursor: str | None,
) -> tuple[list[SpeciesListItem] | None, str | None, str | None]:
    """Resolve the deepest taxon the path walks to, then return its
    species-rank children paginated.

    Returns ``(items, next_cursor, error_detail)``. The router
    inspects the three values: ``(None, None, detail)`` means a
    resolution error (e.g. path does not resolve) and ``detail``
    carries the human-readable message; ``(items, cursor, None)``
    means success. The split lets the router distinguish "not
    found" (404) from a successful empty page (200) cleanly.
    """
    if not segments:
        return None, None, "taxon not found: ''"
    """Resolve the deepest taxon the path walks to, then return its
    species-rank children paginated.

    Returns ``(None, detail)`` if the deepest segment does not
    resolve — the router maps that to a 404.

    The path is walked the same way as ``list_path_children`` (no
    rank assumption; case-insensitive; first segment anchored on
    kingdom). The deepest taxon is then queried for its species
    children via the same ``list_species_page`` helper the legacy
    endpoint uses, so pagination semantics stay consistent.
    """
    if not segments:
        return None, None, "taxon not found: ''"

    parent_id: int | None = None
    deepest: Taxon | None = None

    for segment in segments:
        stmt = select(Taxon).where(func.lower(Taxon.name) == segment.lower())
        if parent_id is None:
            stmt = stmt.where(func.lower(Taxon.rank) == "kingdom")
        else:
            stmt = stmt.where(Taxon.parent_id == parent_id)
        candidate = session.scalars(stmt).first()
        if candidate is None:
            return None, None, f"taxon not found: {segment!r}"
        deepest = candidate
        parent_id = deepest.id

    assert deepest is not None

    inclusion = parse_include(include)
    page = list_species_page(
        session,
        parent_id=deepest.id,
        inclusion=inclusion,
        cursor=cursor,
    )
    return (
        [
            SpeciesListItem(
                id=row.id,
                name=row.name,
                display_name=row.display_name,
                rank=row.rank,
                parent_id=row.parent_id,
                is_synonym=row.is_synonym,
                is_extinct=row.is_extinct,
                is_uncertain=row.is_uncertain,
                is_unassigned=row.is_unassigned,
            )
            for row in page.rows
        ],
        page.next_cursor,
        None,
    )


__all__ = ["list_species_at_path"]
