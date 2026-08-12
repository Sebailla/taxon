"""Versioned ``/api`` router.

Sub-PR 2A registered the ``/api`` prefix and a ``/_meta`` smoke probe
so we could prove the prefix was wired before any real endpoint
existed. Sub-PR 2B fills the prefix with the cascade endpoints the
frontend uses:

    GET /api/kingdoms
    GET /api/{kingdom}/phyla
    GET /api/{kingdom}/{phylum}/classes
    GET /api/{kingdom}/{phylum}/{class}/orders
    GET /api/{kingdom}/{phylum}/{class}/{order}/families
    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/genera
    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species

The leaf endpoint returns the direct species children of the genus so
the cascade UI's sixth scrolling panel has real data to render.

The ``/_meta`` route is intentionally kept; it is the smoke check that
the router is mounted at all and MUST NOT be removed by later sub-PRs.

Path-name semantics
-------------------
Each segment is matched case-insensitively against the canonical
``Taxon.name`` and anchored on the parent identified by the previous
segment. The path's rank context disambiguates same-named taxa under
different parents — there is no scenario in which a Kingdom segment
conflicts with an Order segment because the segment-by-segment walk
expects the canonical rank at each depth. A 404 is returned when any
segment fails to resolve; the error body identifies the failing
segment so the client can tell the user which step broke.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from taxon.api.db import get_db
from taxon.api.errors import NotFoundError
from taxon.api.hierarchy import (
    PATH_RANKS,
    SPECIES_RANK,
    TaxonRow,
    list_children,
    list_root_taxa,
    resolve_path,
)
from taxon.api.schemas import TaxonResponse

router = APIRouter(prefix="/api")


@router.get("/_meta")
def api_meta() -> dict[str, str]:
    """Smoke check that confirms the ``/api`` prefix is mounted."""
    return {"phase": "2B"}


@router.get("/kingdoms", response_model=list[TaxonResponse])
def list_kingdoms(session: Annotated[Session, Depends(get_db)]) -> list[TaxonResponse]:
    """Return every Kingdom-rank taxon sorted by canonical ``name``."""
    rows: list[TaxonRow] = list_root_taxa(session)
    return [TaxonResponse.model_validate(row) for row in rows]


def _resolve_or_404(session: Session, segments: list[str]) -> TaxonRow:
    """Walk ``segments`` and raise ``NotFoundError`` on any mismatch.

    The 404 detail names the failing segment so the cascade UI can
    highlight the dropdown that produced the bad path. ``resolve_path``
    already enforces the canonical rank at each depth so this helper
    only needs to translate a ``None`` return into a 404.
    """
    taxon = resolve_path(session, segments)
    if taxon is None:
        # Use the last segment as the user-visible failure point; the
        # resolver walks left-to-right so the first mismatch is the
        # leftmost unrecognised segment.
        raise NotFoundError(f"taxon not found: {segments[-1]!r}")
    return taxon


def _children_endpoint(
    parent_segments: list[str],
    rank: str,
    session: Session,
) -> list[TaxonResponse]:
    """Resolve ``parent_segments`` and return its children at ``rank``.

    Returns ``[]`` (not 404) when the parent exists but has no children
    at that rank — the cascade UI treats both cases as "no results".
    """
    parent = _resolve_or_404(session, parent_segments)
    rows = list_children(session, parent_id=parent.id, rank=rank)
    return [TaxonResponse.model_validate(row) for row in rows]


@router.get(
    "/{kingdom}/phyla",
    response_model=list[TaxonResponse],
)
def list_phyla(
    kingdom: Annotated[str, Path(min_length=1)],
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return direct Phylum children of ``{kingdom}``."""
    return _children_endpoint([kingdom], PATH_RANKS[1], session)


@router.get(
    "/{kingdom}/{phylum}/classes",
    response_model=list[TaxonResponse],
)
def list_classes(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return direct Class children of ``{kingdom}/{phylum}``."""
    return _children_endpoint([kingdom, phylum], PATH_RANKS[2], session)


@router.get(
    "/{kingdom}/{phylum}/{class_name}/orders",
    response_model=list[TaxonResponse],
)
def list_orders(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return direct Order children of ``{kingdom}/{phylum}/{class}``."""
    # ``class`` shadows a Python builtin; ``Path(alias=...)`` lets the
    # URL stay at ``{class_name}`` while the parameter binding uses a
    # non-clashing local name.
    _ = class_name
    return _children_endpoint([kingdom, phylum, class_name], PATH_RANKS[3], session)


@router.get(
    "/{kingdom}/{phylum}/{class_name}/{order_name}/families",
    response_model=list[TaxonResponse],
)
def list_families(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    order_name: Annotated[str, Path(min_length=1, alias="order_name")],
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return direct Family children of ``{kingdom}/{phylum}/{class}/{order}``."""
    return _children_endpoint([kingdom, phylum, class_name, order_name], PATH_RANKS[4], session)


@router.get(
    "/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/genera",
    response_model=list[TaxonResponse],
)
def list_genera(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    order_name: Annotated[str, Path(min_length=1, alias="order_name")],
    family_name: Annotated[str, Path(min_length=1, alias="family_name")],
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return direct Genus children of the path's last family segment."""
    return _children_endpoint(
        [kingdom, phylum, class_name, order_name, family_name],
        PATH_RANKS[5],
        session,
    )


@router.get(
    "/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/species",
    response_model=list[TaxonResponse],
)
def list_species(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    order_name: Annotated[str, Path(min_length=1, alias="order_name")],
    family_name: Annotated[str, Path(min_length=1, alias="family_name")],
    genus_name: Annotated[str, Path(min_length=1, alias="genus_name")],
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return direct Species children of the path's last genus segment.

    This is the leaf of the cascade; the frontend's sixth scrolling
    panel renders the response. Inclusion filters and per-species
    search links land in Sub-PR 2C.
    """
    return _children_endpoint(
        [kingdom, phylum, class_name, order_name, family_name, genus_name],
        SPECIES_RANK,
        session,
    )
