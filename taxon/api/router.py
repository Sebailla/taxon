"""Versioned ``/api`` router.

Sub-PR 2A registered the ``/api`` prefix and a ``/_meta`` smoke probe
so we could prove the prefix was wired before any real endpoint
existed. Sub-PR 2B filled the prefix with the cascade endpoints the
frontend uses. Sub-PR 2C adds three more endpoints on top:

    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species
        Extended with ``include`` query param (CSV of
        ``synonyms,extinct,uncertain,unassigned``) and pagination
        (``next_cursor`` after the 500-item cap).
    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}
        Resolves a (genus, epithet) pair to a single species.
        200 with breadcrumb, 404 when no match, 409 with candidates[]
        when the pair is shared across multiple parent breadcrumbs.
    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}/links
        Emits the 12 dispatch URLs for a resolved species, with
        ``{q}`` substituted via :func:`urllib.parse.quote_plus`.

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

The lookup endpoint (no trailing ``/links``) is the only place where
ambiguity can surface — the path can match the genus but the
``(genus, epithet)`` pair may exist under multiple distinct parent
hierarchies. When that happens, the response is HTTP 409 with
``candidates[]`` carrying the full breadcrumb for each match so the
UI can show a disambiguation picker.
"""

from __future__ import annotations

from pathlib import Path as PathLib
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.api.db import get_db
from taxon.api.errors import AmbiguousError, NotFoundError
from taxon.api.hierarchy import (
    PATH_RANKS,
    TaxonRow,
    list_children,
    list_root_taxa,
    resolve_path,
)
from taxon.api.schemas import (
    LinksResponse,
    MarkerFlags,
    SearchLinkItem,
    SpeciesListItem,
    SpeciesListResponse,
    SpeciesLookupResponse,
    TaxonResponse,
)
from taxon.api.species import (
    build_breadcrumb,
    find_species_by_pair,
    list_species_page,
    parse_include,
)
from taxon.schema import Taxon
from taxon.search_links import SearchLink, build_search_links, load_templates

router = APIRouter(prefix="/api")


# Templates live next to the repo root. The path is resolved lazily on
# the first request so tests that don't touch /links don't pay the
# disk round-trip. Production callers can override ``TAXON_TEMPLATES``
# via the env var to point at a different file.
import os as _os

_TEMPLATES_PATH = PathLib(_os.environ.get("TAXON_TEMPLATES", "docs/sources/templates.md"))


def _load_templates() -> tuple[SearchLink, ...]:
    """Load and substitute the 12 dispatch URLs from the templates file.

    The substitution step is intentionally deferred to the endpoint
    body so the same template set is reused across requests.
    """
    templates = load_templates(_TEMPLATES_PATH)
    # ``build_search_links`` expects the species query; we substitute
    # later, so this helper returns the unsubstituted links with a
    # ``{q}`` placeholder kept verbatim.
    return tuple(SearchLink(source=t.source, label=t.source, url=t.url_template) for t in templates)


@router.get("/_meta")
def api_meta() -> dict[str, str]:
    """Smoke check that confirms the ``/api`` prefix is mounted."""
    return {"phase": "2C"}


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
    response_model=SpeciesListResponse,
)
def list_species(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    order_name: Annotated[str, Path(min_length=1, alias="order_name")],
    family_name: Annotated[str, Path(min_length=1, alias="family_name")],
    genus_name: Annotated[str, Path(min_length=1, alias="genus_name")],
    session: Annotated[Session, Depends(get_db)],
    include: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated inclusion classes "
                "(synonyms, extinct, uncertain, unassigned). "
                "Default is accepted-only."
            )
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(description="Pagination cursor returned in next_cursor."),
    ] = None,
) -> SpeciesListResponse:
    """Return direct species children of the genus, paginated.

    The response envelope carries ``items`` (up to 500 rows) and
    ``next_cursor`` (a non-empty string when more rows exist beyond
    the cap). The ``include`` query parameter widens the result set
    per the inclusion-filters spec; unknown values are silently
    ignored.

    Pagination semantics
    --------------------
    The first page is the alphabetically first 500 rows. The cursor
    is the canonical ``name`` of the last row in the previous page;
    the next request starts from rows whose canonical ``name`` is
    strictly greater than the cursor. Names (not ids) keep the
    cursor stable across database re-imports.
    """
    parent = _resolve_or_404(
        session,
        [kingdom, phylum, class_name, order_name, family_name, genus_name],
    )
    inclusion = parse_include(include)
    page = list_species_page(
        session,
        parent_id=parent.id,
        inclusion=inclusion,
        cursor=cursor,
    )
    return SpeciesListResponse(
        items=[SpeciesListItem.model_validate(row) for row in page.rows],
        next_cursor=page.next_cursor,
    )


# ---------------------------------------------------------------------------
# Sub-PR 2C — single-species lookup + links
# ---------------------------------------------------------------------------


def _lookup_species_by_breadcrumb(
    session: Session,
    *,
    parent_segments: list[str],
    epithet: str,
) -> TaxonRow:
    """Resolve ``(parent_segments, epithet)`` via the full breadcrumb path.

    The path anchors on the kingdom so the resolution is fully
    qualified; ambiguity cannot occur. Raises :class:`NotFoundError`
    when the genus or epithet does not resolve.
    """
    matches = find_species_by_pair(session, parent_segments=parent_segments, epithet=epithet)
    if not matches:
        genus = resolve_path(session, parent_segments)
        if genus is None:
            raise NotFoundError(f"taxon not found: {parent_segments[-1]!r}")
        raise NotFoundError(f"species not found: {epithet!r}")
    return matches[0]


def _lookup_species_by_pair(
    session: Session,
    *,
    genus_name: str,
    epithet: str,
) -> TaxonRow:
    """Resolve ``(genus_name, epithet)`` across every genus sharing the name.

    Scans the dataset for any taxon whose ``name`` equals ``genus_name``
    AND ``rank == 'genus'``; for each match, looks up the
    ``(genus, epithet)`` species under it. Returns the single matched
    species, raises :class:`NotFoundError` for zero matches, or
    :class:`AmbiguousError` with each candidate's full breadcrumb
    when multiple matches exist.
    """
    genus_stmt = (
        select(Taxon)
        .where(func.lower(Taxon.rank) == "genus")
        .where(func.lower(Taxon.name) == genus_name.lower())
    )
    candidate_genera = list(session.scalars(genus_stmt).all())
    if not candidate_genera:
        raise NotFoundError(f"taxon not found: {genus_name!r}")

    matches: list[TaxonRow] = []
    for genus in candidate_genera:
        # Walk the breadcrumb up to this genus so we can reuse the
        # canonical lookup helper.
        chain: list[str] = []
        current_id: int | None = genus.id
        seen: set[int] = set()
        while current_id is not None and current_id not in seen:
            seen.add(current_id)
            taxon = session.get(Taxon, current_id)
            if taxon is None:
                break
            parent_id = taxon.parent_id
            if parent_id is None:
                break
            parent = session.get(Taxon, parent_id)
            if parent is None:
                break
            chain.append(parent.name)
            current_id = parent.id
        chain.reverse()
        if chain and chain[0].lower() == "biota":
            chain = chain[1:]
        # The chain is the breadcrumb up to (but not including) the
        # genus. Append the genus to get the full lookup path.
        lookup_path = chain + [genus.name]
        matches.extend(find_species_by_pair(session, parent_segments=lookup_path, epithet=epithet))

    if not matches:
        raise NotFoundError(f"species not found: {epithet!r}")
    if len(matches) > 1:
        candidates = [
            {
                "id": m.id,
                "breadcrumb": build_breadcrumb(session, m.id),
                "canonical_name": m.name,
                "display_name": m.display_name,
            }
            for m in matches
        ]
        candidates.sort(key=lambda c: tuple(c["breadcrumb"]))  # type: ignore[arg-type]
        raise AmbiguousError(candidates, detail=f"ambiguous: {epithet!r}")
    return matches[0]


def _species_response(session: Session, taxon: TaxonRow) -> SpeciesLookupResponse:
    """Build a :class:`SpeciesLookupResponse` from a single taxon row."""
    return SpeciesLookupResponse(
        id=taxon.id,
        canonical_name=taxon.name,
        display_name=taxon.display_name,
        markers=MarkerFlags(
            is_synonym=taxon.is_synonym,
            is_extinct=taxon.is_extinct,
            is_uncertain=taxon.is_uncertain,
            is_unassigned=taxon.is_unassigned,
        ),
        breadcrumb=build_breadcrumb(session, taxon.id),
    )


@router.get(
    "/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/{epithet}",
    response_model=SpeciesLookupResponse,
)
def lookup_species(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    order_name: Annotated[str, Path(min_length=1, alias="order_name")],
    family_name: Annotated[str, Path(min_length=1, alias="family_name")],
    genus_name: Annotated[str, Path(min_length=1, alias="genus_name")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> SpeciesLookupResponse:
    """Resolve a (genus, epithet) pair via the full breadcrumb.

    The path's Kingdom → … → Genus segments anchor the resolution so
    the response is fully qualified; ambiguity cannot occur. 200 with
    full breadcrumb when the species resolves. 404 when the genus or
    epithet does not match.
    """
    taxon = _lookup_species_by_breadcrumb(
        session,
        parent_segments=[
            kingdom,
            phylum,
            class_name,
            order_name,
            family_name,
            genus_name,
        ],
        epithet=epithet,
    )
    return _species_response(session, taxon)


@router.get(
    "/species/{genus_name}/{epithet}",
    response_model=SpeciesLookupResponse,
)
def lookup_species_by_pair(
    genus_name: Annotated[str, Path(min_length=1, alias="genus_name")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> SpeciesLookupResponse:
    """Resolve a (genus, epithet) pair without a breadcrumb prefix.

    Scans every genus sharing the name; the response is one of:

    - **200** when exactly one species matches.
    - **404** when no species match.
    - **409** when multiple species match; the body carries
      ``candidates[]`` with each candidate's full breadcrumb.

    The breadcrumb lookup (``/{kingdom}/.../{genus}/{epithet}``) is
    the canonical entry point; this pair-only endpoint exists for
    flows that have not yet collected the parent path (e.g. a search
    box that resolves a name to a species before the user clicks a
    dropdown).
    """
    taxon = _lookup_species_by_pair(session, genus_name=genus_name, epithet=epithet)
    return _species_response(session, taxon)


@router.get(
    "/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/{epithet}/links",
    response_model=LinksResponse,
)
def species_links(
    kingdom: Annotated[str, Path(min_length=1)],
    phylum: Annotated[str, Path(min_length=1)],
    class_name: Annotated[str, Path(min_length=1, alias="class_name")],
    order_name: Annotated[str, Path(min_length=1, alias="order_name")],
    family_name: Annotated[str, Path(min_length=1, alias="family_name")],
    genus_name: Annotated[str, Path(min_length=1, alias="genus_name")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> LinksResponse:
    """Emit the 12 dispatch URLs for a resolved species.

    The lookup uses the full breadcrumb so ambiguity cannot occur
    here. A successful lookup returns the species record plus the 12
    URLs substituted with the URL-encoded species query. The order
    matches the row order in ``docs/sources/templates.md``.
    """
    taxon = _lookup_species_by_breadcrumb(
        session,
        parent_segments=[
            kingdom,
            phylum,
            class_name,
            order_name,
            family_name,
            genus_name,
        ],
        epithet=epithet,
    )

    templates = load_templates(_TEMPLATES_PATH)
    substituted = build_search_links(taxon.name, templates)
    return LinksResponse(
        species=_species_response(session, taxon),
        links=[
            SearchLinkItem(source=link.source, label=link.label, url=link.url)
            for link in substituted
        ],
    )
