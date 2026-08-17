"""Pydantic response models for the API layer.

These models are the public contract for every JSON response served by
``taxon.api``. The design keeps ``name`` (canonical) and ``display_name``
(verbatim source label, including author citations) as independent fields so
the cascade UI can show citations while path-name lookups stay clean.

Markers carry through both `Taxon` and `SpeciesPath` rows so the inclusion
filters (extinct, synonyms, uncertain, unassigned) have a stable response
shape regardless of which endpoint emits the row.

`ErrorResponse` carries an optional `candidates` list — present on 409
ambiguity responses (Sub-PR 2C) and absent on plain 404s.

Sub-PR 2C adds three new response shapes:

- ``SpeciesListResponse`` envelopes the species list with a pagination
  cursor (``items`` + ``next_cursor``) so the leaf endpoint can grow
  beyond the 500-item cap without changing the wire shape.
- ``SpeciesLookupResponse`` carries a single species plus its full
  Kingdom → … → Genus breadcrumb for the cascade UI to render the
  resolved path.
- ``LinksResponse`` wraps the 12 search-source URLs emitted for a
  resolved species so the UI can render them as a fixed button grid.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _ORMBase(BaseModel):
    """Common config for response models that may be populated from ORM rows.

    ``from_attributes=True`` lets endpoints construct the model directly
    from a SQLAlchemy row (``Model.model_validate(row)``). The class
    columns of ``SpeciesPath`` (``class_name``, ``order_name``) match
    these field names so no alias is required.
    """

    model_config = ConfigDict(from_attributes=True)


class TaxonResponse(_ORMBase):
    """Single taxon in the hierarchy.

    ``name`` is the citation-free canonical key used for path-name lookups;
    ``display_name`` preserves the verbatim source label including any author
    citation so the UI can render it.

    ``id`` and ``parent_id`` accept ``int | str`` because the cascade
    backend's two backends disagree: local SQLite rows emit autoincrement
    ``int`` ids, while the ChecklistBank-backed cascade emits opaque
    string IDs (e.g. ``"N"`` for Animalia, ``"5T6MX"`` for Biota). The
    union type keeps both contract surfaces honest.
    """

    id: int | str
    name: Annotated[str, Field(min_length=1)]
    display_name: str
    rank: str
    parent_id: int | str | None = None

    is_synonym: bool = False
    is_extinct: bool = False
    is_uncertain: bool = False
    is_unassigned: bool = False


class SpeciesPathResponse(_ORMBase):
    """Fully materialized breadcrumb for a species row.

    Ranks that did not exist in the source lineage surface as ``None``;
    ``species`` itself is always present and is the canonical lookup key.

    The public field names match the SQLAlchemy columns (``class_name``,
    ``order_name``). ``class`` and ``order`` shadow Python built-ins, so
    the column names already do the work — JSON consumers see the same
    strings the DB stores.
    """

    id: int
    kingdom: str | None = None
    phylum: str | None = None
    class_name: str | None = None
    order_name: str | None = None
    family: str | None = None
    genus: str | None = None
    species: Annotated[str, Field(min_length=1)]
    display_name: str

    is_synonym: bool = False
    is_extinct: bool = False
    is_uncertain: bool = False
    is_unassigned: bool = False


class HealthResponse(_ORMBase):
    """Payload for ``GET /healthz``."""

    status: Literal["ok"]


class CandidateRef(_ORMBase):
    """Pointer used in 409 ambiguity responses.

    The breadcrumb is the canonical-path Kingdom → … → Genus for the
    candidate so the UI can render a disambiguation list without an extra
    request.
    """

    id: int
    breadcrumb: list[str]


class ErrorResponse(_ORMBase):
    """Generic error payload.

    ``candidates`` is populated only for 409 ambiguity responses; all other
    error responses leave it ``None`` so the schema stays uniform.

    The candidate shape for 409s carries the full breadcrumb so the
    UI can render a disambiguation list without re-walking the cascade.
    ``canonical_name`` and ``display_name`` are present alongside ``id``
    so the UI can render each candidate immediately.
    """

    detail: str
    candidates: list[AmbiguityCandidate] | None = None


# ---------------------------------------------------------------------------
# Sub-PR 2C additions
# ---------------------------------------------------------------------------


class MarkerFlags(_ORMBase):
    """Inclusion-class flags grouped under a single ``markers`` object.

    The species-list and species-lookup responses expose the four flags
    as a nested object so the UI can map them to toggle state without
    flattening each one onto the top level.
    """

    is_synonym: bool = False
    is_extinct: bool = False
    is_uncertain: bool = False
    is_unassigned: bool = False


class SpeciesListItem(_ORMBase):
    """One row in the species-list envelope.

    Same shape as :class:`TaxonResponse` for the per-row payload; we
    keep a separate name so future fields (e.g. taxonomy-version
    markers) can be added without breaking ``TaxonResponse``.

    ``id`` and ``parent_id`` accept ``int | str`` to mirror
    :class:`TaxonResponse` — local rows emit ``int``, ChecklistBank
    rows emit opaque strings.
    """

    id: int | str
    name: Annotated[str, Field(min_length=1)]
    display_name: str
    rank: str
    parent_id: int | str | None = None
    parent_segments: list[str] = Field(default_factory=list)

    is_synonym: bool = False
    is_extinct: bool = False
    is_uncertain: bool = False
    is_unassigned: bool = False


class SpeciesListResponse(_ORMBase):
    """Envelope for the paginated species-list endpoint.

    ``next_cursor`` is ``None`` when the page is complete; a non-empty
    string means more rows exist and the client should request the
    next page with ``?cursor=<value>``. The cursor is opaque to the
    client.
    """

    items: list[SpeciesListItem]
    next_cursor: str | None = None


class SpeciesLookupResponse(_ORMBase):
    """Single-species resolution response.

    ``canonical_name`` is the citation-free lookup key; ``display_name``
    preserves the source label including author citations. ``breadcrumb``
    is the full Kingdom → … → Genus path so the UI can render the
    resolved lineage without re-walking the cascade.
    """

    id: int
    canonical_name: Annotated[str, Field(min_length=1)]
    display_name: str
    markers: MarkerFlags
    breadcrumb: list[str]


class AmbiguityCandidate(_ORMBase):
    """Single candidate in a 409 ambiguity response.

    Carries the full breadcrumb so the UI can render a disambiguation
    list that already shows the resolved path; no extra request is
    needed.
    """

    id: int
    canonical_name: Annotated[str, Field(min_length=1)]
    display_name: str
    breadcrumb: list[str]


class SearchLinkItem(_ORMBase):
    """One of the 12 dispatch URLs emitted for a resolved species.

    ``source`` is the canonical name from ``docs/sources/templates.md``
    (e.g. ``"WoRMS"``, ``"Sci-hub"``); ``label`` is the user-visible
    button label; ``url`` is the fully substituted URL with the
    species query URL-encoded inside.
    """

    source: str
    label: str
    url: str


class LinksResponse(_ORMBase):
    """Envelope for the per-species dispatch-URL endpoint.

    The ``species`` payload echoes the resolved species so the UI can
    pin the links to a known record without a second lookup. ``links``
    is always exactly 12 items in the row order from the templates
    file.
    """

    species: SpeciesLookupResponse
    links: list[SearchLinkItem]


class TaxonLinksResponse(_ORMBase):
    """Envelope for the per-taxon dispatch-URL endpoint.

    Mirrors :class:`LinksResponse` for any cascade-path-resolved taxon
    (kingdom → genus, no epithet). ``taxon`` echoes the deepest
    resolved row so the UI can pin the substitution to a known record
    without a second lookup. ``links`` is always exactly 13 items in
    the row order from the templates file -- substitution uses the
    canonical ``Taxon.name`` (never ``display_name``) so author
    citations never leak into the emitted URLs.
    """

    taxon: TaxonResponse
    links: list[SearchLinkItem]


class NextTier(_ORMBase):
    """One available tier below the parent in
    ``GET /api/path-children?path=A|B|C``.

    CLB / CoL publishes children at multiple ranks between any
    two tuple tiers (``infraphylum`` and ``parvphylum`` between
    subphylum and class; ``subclass`` between class and order;
    ``suborder`` between order and family). The best-effort
    resolver groups children by their actual CLB rank label
    and emits one ``NextTier`` per rank group.

    The frontend renders one cascade dropdown per group, with
    the dropdown's label taken from :attr:`label`.
    """

    rank: str
    """CLB rank label, verbatim (``"infraphylum"``, ``"suborder"``, ...)."""

    label: str
    """User-facing dropdown label, capitalised from :attr:`rank`."""

    examples: list[str] = []
    """First few children names; convenience for tests + tooltips."""

    children: list[TaxonResponse] = []
    """Children at this rank; the frontend extends the path by
    one segment per tier group."""


class PathChildrenEnvelope(_ORMBase):
    """Envelope for ``GET /api/path-children?path=A|B|C``.

    The best-effort resolver (Issue #43) returns ``parent`` (the
    deepest taxon the path resolved to), ``children`` (every
    direct child flattened and de-duplicated by taxon id), and
    ``next_tiers`` (one :class:`NextTier` per distinct rank
    group below the parent; ``None`` at the leaf).

    The cascade UI renders one dropdown per ``next_tiers``
    entry; the dropdown label is :attr:`NextTier.label`. The
    flattened ``children`` list stays so legacy callers that
    iterate every child without grouping keep working.
    """

    parent: TaxonResponse
    children: list[TaxonResponse]
    next_tiers: list[NextTier] | None = None


# ---------------------------------------------------------------------------
# Taxonomic-tree-browse (PR 1 of ``arbol-col-browse``)
# ---------------------------------------------------------------------------


class TreeNodeResponse(TaxonResponse):
    """Taxon row enriched with the derived fields the tree UI needs.

    ``has_children`` is the EXISTS pre-filter so the caret renders
    without a second round-trip. ``species_count`` is the descendant
    count at species-rank for non-leaf parents; ``None`` for leaves
    and for parents whose subtree is too expensive to walk
    (> :data:`SPECIES_COUNT_LAZY_NULL_THRESHOLD` direct children).
    ``authorship`` carries the citation tail split from
    ``display_name`` so the row format ``rank: Name Authorship • N spp.``
    can render without a second column.
    """

    has_children: bool
    species_count: int | None
    authorship: str


class TreeChildrenResponse(_ORMBase):
    """Envelope for ``GET /api/tree/children?parent_id={id}``.

    ``parent`` is the resolved TaxonResponse (or ``None`` when the
    caller asked for the roots with ``parent_id=0``). ``children``
    is the ordered list of direct children carrying every
    :class:`TreeNodeResponse` field. ``next_cursor`` is non-empty
    when the result set exceeded the page ``limit``; absent
    otherwise.
    """

    parent: TaxonResponse | None
    children: list[TreeNodeResponse]
    next_cursor: str | None = None


class TreeSearchHit(_ORMBase):
    """Single hit in the ``GET /api/tree/search?q=`` response.

    ``id`` and ``parent_id`` mirror :class:`TaxonResponse` — local
    rows emit ``int``, ChecklistBank rows would emit opaque strings
    (the tree browse never queries CLB, but the contract stays
    symmetric with the rest of the cascade surface). ``relevance``
    names the match tier so the UI can label badges if it ever
    wants to: ``"exact"``, ``"prefix"``, or ``"substring"``.
    """

    id: int | str
    name: Annotated[str, Field(min_length=1)]
    display_name: str
    rank: str
    parent_id: int | str | None = None
    has_children: bool = False
    relevance: str


class TreeSearchResponse(_ORMBase):
    """Envelope for ``GET /api/tree/search?q={q}``.

    ``items`` carries the ranked hits (exact > prefix > substring,
    then by ``display_name`` length ascending); the wire shape stays
    bounded to 8 entries so the autocomplete stays snappy on
    :file:`data/col.db`.
    """

    items: list[TreeSearchHit]


# ---------------------------------------------------------------------------
# species-folder-explorer (PR 1 of issue #68)
# ---------------------------------------------------------------------------


class ExploredResponse(_ORMBase):
    """Response for ``POST /api/explored/{genus}/{epithet}``.

    Echoes the resolved species row in the same shape as
    :class:`SpeciesLookupResponse` so the SPA can pin the explored flag
    to the row it was toggled from without a second lookup.
    """

    id: int
    canonical_name: Annotated[str, Field(min_length=1)]
    display_name: str
    markers: MarkerFlags
    breadcrumb: list[str]
    genus: Annotated[str, Field(min_length=1)]
    epithet: Annotated[str, Field(min_length=1)]
    explored_at: str


class ExploredListResponse(_ORMBase):
    """Envelope for ``GET /api/explored/list``.

    The frontend ``workspaceStore.hydrate`` action consumes this on
    App mount; ``species`` is empty (not 404) when the database has no
    explored rows.
    """

    species: list[ExploredResponse]


class SpeciesFolderResponse(_ORMBase):
    """Response for ``POST``/``GET /api/species-folder/{genus}/{epithet}``.

    ``path`` is the absolute on-disk path of the breadcrumb-mirror
    folder under ``AQUALIFE_ROOT``. ``exists`` mirrors the row's
    presence so the GET existence check does not need a separate
    status-code round-trip in the SPA.
    """

    genus: Annotated[str, Field(min_length=1)]
    epithet: Annotated[str, Field(min_length=1)]
    path: str
    exists: bool = True


class LinkVisitedItem(_ORMBase):
    """One entry in the per-species visited-set list.

    ``source`` is the canonical name from ``docs/sources/templates.md``
    (e.g. ``"Wikipedia"``); ``visited_at`` is the ISO-8601 timestamp
    the row was last refreshed.
    """

    source: str
    visited_at: str


class LinkVisitedResponse(_ORMBase):
    """Envelope for ``GET /api/link-visited/{genus}/{epithet}``.

    ``sources`` is empty (not 404) when the species has no visited
    rows. The frontend hydrates per species, lazily, when its row
    mounts.
    """

    genus: Annotated[str, Field(min_length=1)]
    epithet: Annotated[str, Field(min_length=1)]
    sources: list[LinkVisitedItem]


__all__ = [
    "AmbiguityCandidate",
    "CandidateRef",
    "ErrorResponse",
    "ExploredListResponse",
    "ExploredResponse",
    "HealthResponse",
    "LinkVisitedItem",
    "LinkVisitedResponse",
    "LinksResponse",
    "MarkerFlags",
    "NextTier",
    "PathChildrenEnvelope",
    "SearchLinkItem",
    "SpeciesFolderResponse",
    "SpeciesListItem",
    "SpeciesListResponse",
    "SpeciesLookupResponse",
    "SpeciesPathResponse",
    "TaxonLinksResponse",
    "TaxonResponse",
    "TreeChildrenResponse",
    "TreeNodeResponse",
    "TreeSearchHit",
    "TreeSearchResponse",
]
