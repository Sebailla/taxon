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
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _ORMBase(BaseModel):
    """Common config for response models that may be populated from ORM rows."""

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
    """

    id: int
    kingdom: str | None = None
    phylum: str | None = None
    # Python forbids ``class`` as an attribute name; the SQLAlchemy column is
    # ``class_name`` and the JSON field is also ``class_name`` for parity.
    class_name: str | None = Field(default=None, alias="class_")
    order_name: str | None = Field(default=None, alias="order_")
    family: str | None = None
    genus: str | None = None
    species: Annotated[str, Field(min_length=1)]
    display_name: str

    is_synonym: bool = False
    is_extinct: bool = False
    is_uncertain: bool = False
    is_unassigned: bool = False

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(_ORMBase):
    """Payload for ``GET /healthz``."""

    status: Literal["ok"]


class CandidateRef(_ORMBase):
    """Pointer used in 409 ambiguity responses.

    The breadcrumb is the canonical-path Kingdom → … → Species for the
    candidate so the UI can render a disambiguation list without an extra
    request.
    """

    id: int
    breadcrumb: list[str]


class ErrorResponse(_ORMBase):
    """Generic error payload.

    ``candidates`` is populated only for 409 ambiguity responses; all other
    error responses leave it ``None`` so the schema stays uniform.
    """

    detail: str
    candidates: list[CandidateRef] | None = None


__all__ = [
    "CandidateRef",
    "ErrorResponse",
    "HealthResponse",
    "SpeciesPathResponse",
    "TaxonResponse",
]
