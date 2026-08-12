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
    """

    id: int
    name: Annotated[str, Field(min_length=1)]
    display_name: str
    rank: str
    parent_id: int | None = None

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
    """

    id: int
    name: Annotated[str, Field(min_length=1)]
    display_name: str
    rank: str
    parent_id: int | None = None

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


__all__ = [
    "AmbiguityCandidate",
    "CandidateRef",
    "ErrorResponse",
    "HealthResponse",
    "LinksResponse",
    "MarkerFlags",
    "SearchLinkItem",
    "SpeciesListItem",
    "SpeciesListResponse",
    "SpeciesLookupResponse",
    "SpeciesPathResponse",
    "TaxonResponse",
]
