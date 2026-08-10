"""HTTP API layer for the taxonomy + species search dispatcher.

This package hosts the FastAPI app factory, response schemas, and the
versioned ``/api`` router. Sub-PR 2A ships the factory, schemas, and the
``/healthz`` probe only; the hierarchy, species list, links, and 409
ambiguity routes land in Sub-PRs 2B and 2C.
"""

from taxon.api.schemas import (
    CandidateRef,
    ErrorResponse,
    HealthResponse,
    SpeciesPathResponse,
    TaxonResponse,
)

__all__ = [
    "CandidateRef",
    "ErrorResponse",
    "HealthResponse",
    "SpeciesPathResponse",
    "TaxonResponse",
    "create_app",
]
