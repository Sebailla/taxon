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

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taxon.api.schemas import (
    AmbiguityCandidate,
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


def _collect_paths(app: FastAPI) -> set[str]:
    """Recursively gather every concrete path mounted on ``app``.

    FastAPI wraps included routers in a private ``_IncludedRouter`` node
    that does not expose ``.path`` directly; the underlying ``APIRouter``
    is reachable via ``.original_router``. Walk both shapes.
    """
    paths: set[str] = set()
    pending: list[object] = list(app.routes)
    while pending:
        route = pending.pop()
        cls = type(route).__name__
        if cls == "APIRoute":
            # Every concrete APIRoute exposes ``path`` at runtime.
            paths.add(route.path)  # type: ignore[attr-defined]
            continue
        inner = getattr(route, "original_router", None)
        if inner is not None and hasattr(inner, "routes"):
            pending.extend(inner.routes)

    return paths


def test_api_router_is_registered_under_api_prefix() -> None:
    app = _build_app()

    paths = _collect_paths(app)
    # Sub-PR 2A only registers the router with the `/api` prefix; 2B/2C add
    # concrete routes. The placeholder `/_meta` endpoint proves the prefix
    # is wired before any real endpoint exists.
    assert any(path.startswith("/api") for path in paths)


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
        class_name="Archiacanthocephala",
        order_name="Acanthogyrida",
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
    assert breadcrumb.class_name == "Archiacanthocephala"
    assert breadcrumb.order_name == "Acanthogyrida"


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
        class_name=None,
        order_name=None,
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
        AmbiguityCandidate(
            id=1,
            canonical_name="Foo bar",
            display_name="Foo bar",
            breadcrumb=["Animalia", "Acanthocephala", "Foo"],
        ),
        AmbiguityCandidate(
            id=2,
            canonical_name="Foo baz",
            display_name="Foo baz",
            breadcrumb=["Animalia", "Arthropoda", "Foo"],
        ),
    ]
    with_candidates = ErrorResponse(detail="ambiguous", candidates=candidates)
    assert with_candidates.candidates is not None
    assert with_candidates.candidates[0].breadcrumb == [
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
        cast(Any, model)(
            id=1,
            rank="species",
            parent_id=None,
            **kwargs,
        )


def test_file_backed_lifespan_creates_projection_table(tmp_path: Path) -> None:
    """The FastAPI lifespan bootstraps ``taxon_descendant_counts`` on a fresh DB.

    Regression net for the descendant-counts-projection change: a
    fresh ``data/col.db`` boots with the projection table already on
    disk so the first ``GET /api/tree/children`` for an over-threshold
    parent does NOT raise ``OperationalError: no such table`` on the
    ``session.get(TaxonDescendantCount, ...)`` call inside
    :func:`materialize_for_parent`. Without this fix the operator
    must run ``python -m taxon.migrate apply`` before booting the API.
    """
    from sqlalchemy import create_engine, inspect

    from taxon.api import create_app
    from taxon.api.database_url import resolve_database_url

    db = tmp_path / "taxon.db"
    db.touch()
    url = f"sqlite:///{db}"
    # Sanity check: the URL resolver must not silently swap our fresh DB.
    assert resolve_database_url(None, fallback_url="sqlite:///fallback") != url
    app = create_app(database_url=url)

    with TestClient(app) as _:
        pass  # lifespan startup + shutdown

    inspector = inspect(create_engine(url))
    assert "taxon_descendant_counts" in set(inspector.get_table_names())


def test_rebuild_budget_default_is_15_seconds() -> None:
    """``REBUILD_BUDGET_SECONDS`` is 15s — empirically fits a CoL subtree rebuild.

    The previous default of 1.0s was too tight: a full recursive CTE
    walk on the CoL Eukaryota subtree (5.6M descendants) takes ~5-15s
    on a developer machine. With 1.0s the SLO guard always fired and
    the projection stayed empty for every over-threshold parent. 15s
    is the empirical wall-clock cost observed in the runtime harness
    during the original change's verification.
    """
    from taxon.api.projections import REBUILD_BUDGET_SECONDS

    assert REBUILD_BUDGET_SECONDS == 15.0
