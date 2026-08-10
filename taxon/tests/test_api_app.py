"""RED-first contract tests for the FastAPI app factory and Pydantic schemas.

These tests cover Sub-PR 2A only:
- `create_app` builds a usable FastAPI instance with `/healthz` and a registered
  placeholder `/api` router.
- `TaxonResponse` and `SpeciesPathResponse` accept canonical names, keep
  display names with author citations, and default marker flags to False.
- `ErrorResponse` is valid with or without ambiguity `candidates`.
- The generated OpenAPI schema exposes `/healthz`.

The endpoint layer for hierarchy, species list, links, and 409 candidates
lives in Sub-PRs 2B and 2C and is deliberately not exercised here.
"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taxon.api.schemas import (
    CandidateRef,
    ErrorResponse,
    HealthResponse,
    SpeciesPathResponse,
    TaxonResponse,
)


def _build_app(database_url: str = "sqlite:///:memory:") -> FastAPI:
    """Build a fresh app instance for every test to keep lifespans isolated."""
    from taxon.api import create_app

    return create_app(database_url=database_url)


def test_create_app_returns_fastapi_instance() -> None:
    app = _build_app()

    assert isinstance(app, FastAPI)
    # Lifespan must be wired so the engine + session factory come up/down.
    assert app.router.lifespan_context is not None


def test_healthz_returns_ok() -> None:
    app = _build_app()

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_includes_healthz_path() -> None:
    app = _build_app()

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    assert "/healthz" in schema["paths"]
    assert schema["paths"]["/healthz"]["get"]["responses"]["200"] is not None


def test_api_router_is_registered_under_api_prefix() -> None:
    app = _build_app()

    # Sub-PR 2A only registers the router with the `/api` prefix; 2B/2C add
    # concrete routes. The prefix must exist on at least one route.
    assert any(
        route.path.startswith("/api") for route in app.routes if hasattr(route, "path")
    )


def test_health_response_schema_is_literal_ok() -> None:
    payload = HealthResponse(status="ok").model_dump()

    assert payload == {"status": "ok"}


def test_taxon_response_schema_validates_canonical_and_display() -> None:
    payload = TaxonResponse(
        id=42,
        name="Acanthogyrus",
        display_name="Acanthogyrus (Cable & Quick, 1954)",
        rank="genus",
        parent_id=7,
        is_synonym=False,
        is_extinct=False,
        is_uncertain=False,
        is_unassigned=False,
    )

    assert payload.name == "Acanthogyrus"
    assert payload.display_name == "Acanthogyrus (Cable & Quick, 1954)"
    # The schema MUST carry both names independently — name is the lookup key,
    # display_name preserves the citation.
    assert payload.name != payload.display_name

    dumped = payload.model_dump()
    assert dumped["parent_id"] == 7
    assert dumped["name"] == "Acanthogyrus"
    assert dumped["rank"] == "genus"


def test_taxon_response_accepts_none_parent() -> None:
    payload = TaxonResponse(
        id=1,
        name="Animalia",
        display_name="Animalia",
        rank="kingdom",
        parent_id=None,
    )

    assert payload.parent_id is None


def test_species_path_response_uses_canonical_names_for_lookup() -> None:
    breadcrumb = SpeciesPathResponse(
        id=100,
        kingdom="Animalia",
        phylum="Acanthocephala",
        class_="Archiacanthocephala",
        order_="Acanthogyrida",
        family="Acanthogyridae",
        genus="Acanthogyrus",
        species="Acanthogyrus malawiensis",
        display_name="Acanthogyrus malawiensis Amin & Heckmann, 2018",
        is_synonym=False,
        is_extinct=False,
        is_uncertain=False,
        is_unassigned=False,
    )

    # `species` is the canonical lookup key without author citation.
    assert breadcrumb.species == "Acanthogyrus malawiensis"
    # `display_name` keeps the citation for the UI.
    assert "Amin" in breadcrumb.display_name
    assert breadcrumb.species != breadcrumb.display_name
    # Every rank that anchors a breadcrumb hop is present.
    assert breadcrumb.kingdom == "Animalia"
    assert breadcrumb.genus == "Acanthogyrus"


def test_marker_flags_default_to_false() -> None:
    payload = TaxonResponse(
        id=1,
        name="Foo",
        display_name="Foo",
        rank="species",
        parent_id=None,
    )

    assert payload.is_synonym is False
    assert payload.is_extinct is False
    assert payload.is_uncertain is False
    assert payload.is_unassigned is False

    species = SpeciesPathResponse(
        id=2,
        kingdom="Animalia",
        phylum=None,
        class_=None,
        order_=None,
        family=None,
        genus="Foo",
        species="Foo bar",
        display_name="Foo bar",
    )
    assert species.is_synonym is False
    assert species.is_extinct is False
    assert species.is_uncertain is False
    assert species.is_unassigned is False


def test_error_response_with_candidates_optional() -> None:
    without = ErrorResponse(detail="not found")
    assert without.detail == "not found"
    assert without.candidates is None

    candidates = [
        CandidateRef(id=1, breadcrumb=["Animalia", "Acanthocephala", "Foo"]),
        CandidateRef(id=2, breadcrumb=["Animalia", "Arthropoda", "Foo"]),
    ]
    with_candidates = ErrorResponse(detail="ambiguous", candidates=candidates)
    assert with_candidates.candidates is not None
    assert cast(list[CandidateRef], with_candidates.candidates)[0].breadcrumb == [
        "Animalia",
        "Acanthocephala",
        "Foo",
    ]


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (TaxonResponse, {"name": "", "display_name": "Foo"}),
        (SpeciesPathResponse, {"species": "", "display_name": "Foo"}),
    ],
)
def test_schema_rejects_empty_canonical_names(model: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        model(  # type: ignore[call-arg]
            id=1,
            rank="species",
            parent_id=None,
            **kwargs,
        )
