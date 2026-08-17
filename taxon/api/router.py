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

PR #58 (SQLite-only cascade) rewires the cascade endpoints
(``/api/kingdoms``, ``/api/path-children``, ``/api/species-list``) to
read from the local SQLite database via
:mod:`taxon.api.sqlite_resolver`. The CLB client modules remain
importable so legacy tests keep passing; the router itself no
longer depends on them. Wire shape is preserved 100% so the
cascade UI keeps working without frontend changes.

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

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taxon.api.db import get_db
from taxon.api.errors import AmbiguousError, NotFoundError
from taxon.api.hierarchy import (
    PATH_RANKS,
    TaxonRow,
    list_children,
    resolve_path,
    resolve_path_by_display_level,
)
from taxon.api.schemas import (
    ExploredListResponse,
    ExploredResponse,
    LinksResponse,
    LinkVisitedItem,
    LinkVisitedResponse,
    MarkerFlags,
    PathChildrenEnvelope,
    SearchLinkItem,
    SpeciesFolderResponse,
    SpeciesListItem,
    SpeciesListResponse,
    SpeciesLookupResponse,
    TaxonLinksResponse,
    TaxonResponse,
    TreeChildrenResponse,
    TreeNodeResponse,
    TreeSearchHit,
    TreeSearchResponse,
)
from taxon.api.species import (
    build_breadcrumb,
    find_species_by_pair,
    list_species_page,
    parse_include,
)
from taxon.api.sqlite_resolver import (
    list_kingdoms as sqlite_list_kingdoms,
)
from taxon.api.sqlite_resolver import (
    list_path_children as sqlite_list_path_children,
)
from taxon.api.sqlite_resolver import (
    list_species_under_path as sqlite_list_species_under_path,
)
from taxon.api.tree import (
    list_tree_children as sqlite_list_tree_children,
)
from taxon.api.tree import (
    search_taxon as sqlite_search_taxon,
)
from taxon.schema import Taxon
from taxon.search_links import SearchLink, build_search_links, load_templates

router = APIRouter(prefix="/api")


# Templates live next to the repo root. The path is resolved lazily on
# the first request so tests that don't touch /links don't pay the
# disk round-trip. Production callers can override ``TAXON_TEMPLATES``
# via the env var to point at a different file.
import os as _os
from datetime import UTC

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


@router.get(
    "/path-children",
    response_model=PathChildrenEnvelope,
)
def path_children(
    path: Annotated[
        str,
        Query(
            description=(
                "Pipe-separated path of canonical names. The endpoint "
                "walks the segments against the local SQLite hierarchy "
                "and returns the direct children of the deepest "
                "resolved taxon. Off-tuple intermediate ranks "
                "(infraphylum, parvphylum, megaclass, subclass, "
                "suborder, subfamily, tribe, subtribe, infratribe) "
                "fold into the parent display bucket via the "
                "display-level resolver, so the walk keeps advancing "
                "on real-world data shapes. The resolver groups "
                "every child by its actual rank label and emits one "
                "``NextTier`` per group in ``next_tiers``. The "
                "cascade UI renders one dropdown per group with the "
                "dropdown label taken from the rank itself. Example: "
                "?path=Animalia%7CChordata%7CVertebrata"
            ),
            min_length=1,
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> PathChildrenEnvelope:
    """Return the children of the deepest taxon the path resolves to.

    The resolver walks the path against the local SQLite hierarchy
    and returns the direct children of the deepest resolved taxon.
    Each segment is matched against a row whose ``display_level``
    matches the expected bucket for the segment's position in the
    path; the first match anchors the next segment on its ``id`` so
    same-named taxa under different parents cannot collide.

    The children fetch drops the ``rank=`` filter and groups the
    response by the children's actual rank labels. The wire envelope
    exposes ``next_tiers`` (one ``NextTier`` per group) so the
    cascade UI renders one dropdown per rank group.
    """
    segments = [segment for segment in path.split("|") if segment]
    response = sqlite_list_path_children(session, segments)
    if response is None:
        raise NotFoundError(f"taxon not found: {segments[-1]!r}")
    return response


@router.get(
    "/species-list",
    response_model=SpeciesListResponse,
)
def species_list(
    path: Annotated[
        str,
        Query(
            description=(
                "Pipe-separated path of canonical names. The endpoint "
                "walks the segments against the local SQLite hierarchy "
                "and returns the species-tier descendants of the "
                "deepest resolved taxon. The deepest segment must be "
                "a genus; the resolver walks up the path to find its "
                "row, then asks for every descendant at the species "
                "display bucket (species, subspecies, variety, form). "
                "Example: ?path=Animalia%7CChordata%7CVertebrata%7C"
                "Mammalia%7CCarnivora%7CFelidae%7CPanthera"
            ),
            min_length=1,
        ),
    ],
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
    """Return the species list at the deepest taxon the path resolves to.

    The path-aware resolver walks the segments against the local
    SQLite hierarchy and asks for every descendant at the species
    display bucket. The cascade UI consumes this once the user
    picks a genus — the species list fills the leaf panel without
    further interaction.

    The ``include`` query parameter widens the result set per the
    inclusion-filters spec; unknown values are silently ignored.
    The ``cursor`` query parameter is the pagination cursor
    returned in ``next_cursor`` when the result set exceeds the
    500-row cap.
    """
    segments = [segment for segment in path.split("|") if segment]
    return sqlite_list_species_under_path(
        session,
        segments,
        include=include,
        cursor=cursor,
    )


@router.get("/kingdoms", response_model=list[TaxonResponse])
def list_kingdoms(
    session: Annotated[Session, Depends(get_db)],
) -> list[TaxonResponse]:
    """Return the synthesized Biota + Viruses root-tier taxa.

    The cascade UI's first dropdown shows exactly two rows: Biota
    (id ``"5T6MX"``, parent of every cellular kingdom) and Viruses
    (id ``"V"``, parent of the virus realms). The local SQLite
    does not carry these rows (the GBIF backbone ships neither
    Viruses nor a true Biota superdomain), so the endpoint
    synthesises both rows server-side with the CLB-canonical ids
    so the cascade UI keeps working without frontend changes.
    """
    return sqlite_list_kingdoms(session)


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


# ---------------------------------------------------------------------------
# Per-taxon dispatch endpoint (breadcrumb-dinamico PR1)
# ---------------------------------------------------------------------------


# Hard cap on the number of cascade-path segments the breadcrumb-taxon's
# ``/taxon-links`` endpoint accepts. The cascade tuple has exactly seven
# display buckets (kingdom, phylum, class, order, family, genus, species),
# so off-tuple intermediates plus the deepest bucket yield up to seven
# segments; an eighth indicates malformed input or an attempted route
# collision with the species-links endpoint.
_TAXON_LINKS_MAX_SEGMENTS: int = 7


# ---------------------------------------------------------------------------
# Taxonomic-tree-browse endpoints (arbol-col-browse PR 1)
# NOTE: registered BEFORE ``/{path:path}/taxon-links`` (declared further
# down) so the catch-all does NOT shadow ``/api/tree/*`` by matching the
# literal ``tree/children`` / ``tree/search`` segments against the path
# parameter. FastAPI matches routes in registration order; the order
# matters. The regression test
# ``test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall``
# pins the contract.
# ---------------------------------------------------------------------------


@router.get(
    "/tree/children",
    response_model=TreeChildrenResponse,
)
def get_tree_children(
    parent_id: Annotated[
        int,
        Query(
            description=(
                "Integer taxon id. ``parent_id=0`` returns every row with "
                "``parent_id IS NULL`` (the CoL tree roots: Archaea + "
                "Bacteria + Eukaryota + Viruses + ?incertae sedis). The "
                "endpoint walks direct children only -- it does NOT "
                "synthesize a Biota superdomain. Returns 404 when "
                "``parent_id`` matches no taxon."
            )
        ),
    ],
    include_extinct: Annotated[
        bool,
        Query(description="Whether extinct taxa appear in the result."),
    ] = True,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Hard cap on the number of children returned."),
    ] = 200,
    cursor: Annotated[
        int | None,
        Query(description="Pagination cursor; reserved for future expansion."),
    ] = None,
    session: Annotated[Session, Depends(get_db)] = ...,  # type: ignore[assignment]
) -> TreeChildrenResponse:
    """Return the direct children of ``parent_id`` enriched for the tree UI.

    Each child carries ``has_children`` (the EXISTS pre-filter so the
    caret renders without a second round-trip), ``species_count``
    (descendant count at species rank via recursive CTE, lazy-nulled
    above the threshold for breadth cost), and ``authorship``
    (citation tail split from ``display_name`` so the row format
    renders without a second column).

    The endpoint returns the data the React tree component needs to
    render one caret row per direct child; the recursive descent is
    the responsibility of the frontend when the user expands a caret.
    """
    _ = cursor  # pagination wired in follow-up PR
    parent_row, children = sqlite_list_tree_children(
        session,
        parent_id,
        include_extinct=include_extinct,
        limit=limit,
        cursor=cursor,
    )
    if parent_id != 0 and parent_row is None:
        raise NotFoundError(f"parent not found: parent_id={parent_id}")
    parent_response: TaxonResponse | None = (
        TreeNodeResponse(
            id=parent_row.id,
            name=parent_row.name,
            display_name=parent_row.display_name,
            rank=parent_row.rank,
            parent_id=parent_row.parent_id,
            authorship=parent_row.authorship,
            has_children=parent_row.has_children,
            species_count=parent_row.species_count,
            is_synonym=parent_row.is_synonym,
            is_extinct=parent_row.is_extinct,
            is_uncertain=parent_row.is_uncertain,
            is_unassigned=parent_row.is_unassigned,
        )
        if parent_row is not None
        else None
    )
    child_responses = [
        TreeNodeResponse(
            id=child.id,
            name=child.name,
            display_name=child.display_name,
            rank=child.rank,
            parent_id=child.parent_id,
            authorship=child.authorship,
            has_children=child.has_children,
            species_count=child.species_count,
            is_synonym=child.is_synonym,
            is_extinct=child.is_extinct,
            is_uncertain=child.is_uncertain,
            is_unassigned=child.is_unassigned,
        )
        for child in children
    ]
    return TreeChildrenResponse(
        parent=parent_response,
        children=child_responses,
        next_cursor=None,
    )


@router.get(
    "/tree/search",
    response_model=TreeSearchResponse,
)
def get_tree_search(
    q: Annotated[
        str,
        Query(
            description=(
                "Free-text search against ``Taxon.name`` and "
                "``Taxon.display_name``. Ranked exact > prefix > "
                "substring; ties break by ``display_name`` length "
                "ascending. Empty / whitespace queries return "
                "``items: []`` with no SQL round-trip. Hard cap is "
                "``limit`` (8 default)."
            ),
            min_length=0,
            max_length=200,
        ),
    ] = "",
    limit: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum number of hits returned."),
    ] = 8,
    include_extinct: Annotated[
        bool,
        Query(description="Whether extinct taxa appear in the result."),
    ] = True,
    session: Annotated[Session, Depends(get_db)] = ...,  # type: ignore[assignment]
) -> TreeSearchResponse:
    """Return ranked hits for the "Find taxon" autocomplete.

    The 200ms debounce and the 8-row cap live in the frontend
    (this endpoint always returns synchronously); the backend keeps
    the LIKE matches tight by over-fetching a small multiple and
    re-ranking client-side. The p95 latency target is 200ms against
    ``data/col.db``; the bench in ``design.md`` (search latency
    section) confirms it.
    """
    hits = sqlite_search_taxon(
        session,
        q,
        limit=limit,
        include_extinct=include_extinct,
    )
    return TreeSearchResponse(
        items=[
            TreeSearchHit(
                id=hit.id,
                name=hit.name,
                display_name=hit.display_name,
                rank=hit.rank,
                parent_id=hit.parent_id,
                has_children=hit.has_children,
                relevance=hit.relevance,
            )
            for hit in hits
        ]
    )


# ---------------------------------------------------------------------------
# species-folder-explorer (PR 1 of issue #68)
# ---------------------------------------------------------------------------
# These eight endpoints MUST be registered BEFORE the ``/{path:path}/taxon-links``
# catch-all below so the catch-all does not shadow them. The regression
# discipline is pinned by ``test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall``
# for the tree endpoints; we extend the same discipline to the workspace
# endpoints in ``test_api_router_workspace::test_workspace_endpoints_registered_before_taxon_links_catchall``.
#
# Every read and write walks by ``(genus, epithet)`` (and ``source_label`` for
# ``link_visited``); no endpoint reaches into ``taxa.id`` because the
# workspace tables are orthogonal to the ``taxa`` primary key.


@router.post(
    "/explored/{genus}/{epithet}",
    response_model=ExploredResponse,
)
def set_explored_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> ExploredResponse:
    """Upsert the explored flag for ``(genus, epithet)`` and echo the species row.

    The endpoint returns the species row (same shape as
    :class:`SpeciesLookupResponse`) so the SPA can pin the toggle to
    the row it was clicked from without a second lookup. Re-posting
    the same pair refreshes ``explored_at`` and is idempotent (no 409).
    """
    from taxon.api.router import _species_response  # local import to avoid cycles
    from taxon.api.workspace import set_explored

    species = set_explored(session, genus=genus, epithet=epithet)
    response = _species_response(session, species)
    return ExploredResponse(
        id=response.id,
        canonical_name=response.canonical_name,
        display_name=response.display_name,
        markers=response.markers,
        breadcrumb=response.breadcrumb,
        genus=genus,
        epithet=epithet,
        explored_at=_utcnow_iso(),
    )


@router.delete("/explored/{genus}/{epithet}", status_code=204)
def unset_explored_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    """Remove the explored flag if present; idempotent — no 404."""
    from taxon.api.workspace import unset_explored

    unset_explored(session, genus=genus, epithet=epithet)
    return Response(status_code=204)


@router.get("/explored/list", response_model=ExploredListResponse)
def list_explored_endpoint(
    session: Annotated[Session, Depends(get_db)],
) -> ExploredListResponse:
    """Return every explored row ordered by ``(genus, epithet)``."""
    from taxon.api.workspace import list_explored

    rows = list_explored(session)
    return ExploredListResponse(
        species=[
            ExploredResponse(
                id=-1,  # the workspace store keys on (genus, epithet); id is not used
                canonical_name=f"{row.genus} {row.epithet}",
                display_name=f"{row.genus} {row.epithet}",
                markers=MarkerFlags(),
                breadcrumb=[],
                genus=row.genus,
                epithet=row.epithet,
                explored_at=row.explored_at,
            )
            for row in rows
        ]
    )


@router.post(
    "/species-folder/{genus}/{epithet}",
    response_model=SpeciesFolderResponse,
    status_code=201,
)
def create_species_folder_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> SpeciesFolderResponse:
    """Create the breadcrumb-mirror folder under ``AQUALIFE_ROOT`` and persist the row.

    201 on first create; 409 on repeat create; 404 when the species
    cannot be resolved; 500 when the resolved ``AQUALIFE_ROOT`` is
    unwritable. The folder is created with ``parents=True`` so missing
    intermediate directories are auto-built.
    """
    from taxon.api.workspace import create_species_folder

    row = create_species_folder(session, genus=genus, epithet=epithet)
    return SpeciesFolderResponse(
        genus=row.genus,
        epithet=row.epithet,
        path=row.path,
        exists=True,
    )


@router.get(
    "/species-folder/{genus}/{epithet}",
    response_model=SpeciesFolderResponse,
)
def get_species_folder_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> SpeciesFolderResponse:
    """Return the folder row when present; 404 otherwise.

    ``exists`` mirrors the row's presence so the SPA can render the
    badge vs. the create button from a single 200 response when the
    folder exists.
    """
    from taxon.api.workspace import get_species_folder

    row = get_species_folder(session, genus=genus, epithet=epithet)
    if row is None:
        raise NotFoundError(f"species folder not found: {genus} {epithet!r}")
    return SpeciesFolderResponse(
        genus=row.genus,
        epithet=row.epithet,
        path=row.path,
        exists=True,
    )


@router.post(
    "/link-visited/{genus}/{epithet}/{source}",
    status_code=204,
)
def record_link_visited_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    source: Annotated[str, Path(min_length=1, alias="source")],
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    """Upsert the visited marker for ``(genus, epithet, source)``.

    ``source`` is the canonical name from ``docs/sources/templates.md``
    (e.g. ``"Wikipedia"``); URLs are NOT part of the key. The endpoint
    is idempotent — re-posting refreshes ``visited_at``.
    """
    from taxon.api.workspace import record_link_visited

    record_link_visited(session, genus=genus, epithet=epithet, source=source)
    return Response(status_code=204)


@router.delete(
    "/link-visited/{genus}/{epithet}/{source}",
    status_code=204,
)
def unrecord_link_visited_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    source: Annotated[str, Path(min_length=1, alias="source")],
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    """Remove the visited marker; idempotent — no 404."""
    from taxon.api.workspace import unrecord_link_visited

    unrecord_link_visited(session, genus=genus, epithet=epithet, source=source)
    return Response(status_code=204)


@router.get(
    "/link-visited/{genus}/{epithet}",
    response_model=LinkVisitedResponse,
)
def list_link_visited_endpoint(
    genus: Annotated[str, Path(min_length=1, alias="genus")],
    epithet: Annotated[str, Path(min_length=1, alias="epithet")],
    session: Annotated[Session, Depends(get_db)],
) -> LinkVisitedResponse:
    """Return every visited row for ``(genus, epithet)`` ordered by ``source``."""
    from taxon.api.workspace import list_link_visited

    rows = list_link_visited(session, genus=genus, epithet=epithet)
    return LinkVisitedResponse(
        genus=genus,
        epithet=epithet,
        sources=[
            LinkVisitedItem(source=row.source_label, visited_at=row.visited_at) for row in rows
        ],
    )


def _utcnow_iso() -> str:
    """ISO-8601 UTC timestamp used by the explored list endpoint.

    The store's ``explored_at`` column carries the same format so the
    hydrate-on-mount payload stays self-consistent.
    """
    from datetime import datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


@router.get(
    "/{path:path}/taxon-links",
    response_model=TaxonLinksResponse,
)
def taxon_links(
    path: Annotated[
        str,
        Path(
            description=(
                "Pipe-separated path of canonical names. The endpoint "
                "walks the segments against the local SQLite hierarchy "
                "via the display-level resolver, then emits the 13 "
                "search-source URLs substituted with the deepest "
                "resolved taxon's canonical name. The path MUST contain "
                "between one and seven segments; eight or more returns "
                "404. The deepest segment may sit at any rank from "
                "kingdom through genus. Example: ``Animalia%7CChordata`` "
                "resolves to the phylum ``Chordata``."
            ),
            min_length=1,
        ),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> TaxonLinksResponse:
    """Emit the 13 dispatch URLs for the deepest resolved taxon.

    The path is walked via :func:`resolve_path_by_display_level` so
    off-tuple intermediates (subphylum, infraphylum, subfamily, ...)
    fold into the parent bucket and the walk keeps advancing on
    real-world data shapes. The substitution target is the canonical
    :attr:`Taxon.name` -- never :attr:`Taxon.display_name` -- so
    author citations never leak into the emitted URLs.

    The seven-segment cap is enforced before the resolver so a path
    longer than the cascade tuple can never reach the database. 404
    is the chosen status (not 422) so the breadcrumb-taxon's failure
    mode mirrors every other 404 in the cascade surface.

    The route is registered AFTER ``/kingdoms``, ``/path-children``,
    and the species-links route so the ``{path:path}`` catch-all does
    NOT shadow those endpoints.
    """
    segments = [segment for segment in path.split("|") if segment]
    if not (1 <= len(segments) <= _TAXON_LINKS_MAX_SEGMENTS):
        raise NotFoundError(
            f"path has {len(segments)} segments; max is {_TAXON_LINKS_MAX_SEGMENTS}"
        )

    taxon = resolve_path_by_display_level(session, segments)
    if taxon is None:
        raise NotFoundError(f"taxon not found: {segments[-1]!r}")

    templates = load_templates(_TEMPLATES_PATH)
    substituted = build_search_links(taxon.name, templates)
    return TaxonLinksResponse(
        taxon=TaxonResponse.model_validate(taxon),
        links=[
            SearchLinkItem(source=link.source, label=link.label, url=link.url)
            for link in substituted
        ],
    )
