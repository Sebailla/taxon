"""FastAPI app factory and shared API-layer types.

Sub-PR 2A wires the factory, lifespan, ``/healthz`` probe, and the
``/api`` router placeholder. Sub-PRs 2B and 2C register concrete routes
against the same router. The HTTP-mapped exception classes live in
:mod:`taxon.api.errors` and are re-exported here for backwards
compatibility with callers that imported them from ``taxon.api``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from taxon.api.errors import AmbiguousError, APIError, NotFoundError
from taxon.api.router import router as api_router
from taxon.api.schemas import AmbiguityCandidate, ErrorResponse, HealthResponse

# Default on-disk location for the SQLite database produced by ``import_data``.
# Lives next to ``pyproject.toml`` so a single ``python -m taxon.main`` invocation
# finds the imported dataset without any extra config.
DEFAULT_DATABASE_URL = "sqlite:///./data/taxon.db"
_DATA_DIR = Path("data")


@dataclass
class AppState:
    """Container for objects attached to ``app.state``.

    Kept as a dataclass so mypy strict mode sees the types of the engine
    and session factory without ``# type: ignore`` noise.
    """

    engine: Engine
    SessionLocal: sessionmaker[Session]


def _resolve_database_url(database_url: str | None) -> str:
    """Resolve the database URL and ensure the on-disk parent directory exists.

    SQLite file URLs (``sqlite:///./data/taxon.db``) need the ``./data``
    directory to exist before the engine tries to open the file. We only
    touch the filesystem for ``sqlite`` URLs — non-sqlite URLs (memory,
    Postgres, etc.) are passed through untouched.
    """
    resolved = database_url or os.environ.get("TAXON_DATABASE_URL") or DEFAULT_DATABASE_URL
    if resolved.startswith("sqlite:///") and not resolved.startswith("sqlite:///:memory:"):
        path_part = resolved[len("sqlite:///") :]
        if path_part and path_part != ":memory:":
            Path(path_part).expanduser().parent.mkdir(parents=True, exist_ok=True)
    elif resolved == "sqlite:///:memory:":
        # In-memory SQLite still needs the data dir if the user later swaps
        # the URL — keep the directory present so the swap is seamless.
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return resolved


def _build_engine(database_url: str) -> Engine:
    """Create the SQLAlchemy engine with sensible defaults for SQLite."""
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        # Required so the same connection can be used across threads in
        # FastAPI's threadpool + lifespan teardown.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args, future=True)


def _error_response(
    status_code: int,
    detail: str,
    candidates: list[Any] | None,
) -> JSONResponse:
    """Render an ``ErrorResponse`` body for the exception handlers.

    The ``candidates`` payload is normalised through
    :class:`AmbiguityCandidate` so the response shape stays consistent
    even when the caller passes dicts with extra keys.
    """
    normalised = (
        [AmbiguityCandidate.model_validate(c) for c in candidates]
        if candidates is not None
        else None
    )
    body = ErrorResponse(detail=detail, candidates=normalised).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the engine + session factory on startup and dispose on shutdown.

    In-memory SQLite engines get their schema created so tests can hit
    endpoints without an import step. File-backed engines assume the
    schema already exists (it is produced by ``python -m taxon.import_data``).
    """
    database_url: str = app.state.database_url
    engine = _build_engine(database_url)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.state.app_state = AppState(engine=engine, SessionLocal=SessionLocal)

    if database_url == "sqlite:///:memory:":
        # Bootstrap the schema for tests so the app is usable without an
        # import step. Production callers build the DB out of band.
        from taxon.schema import Base

        Base.metadata.create_all(engine)

    try:
        yield
    finally:
        engine.dispose()


def create_app(database_url: str | None = None) -> FastAPI:
    """Build a FastAPI app instance bound to ``database_url``.

    Parameters
    ----------
    database_url:
        SQLAlchemy URL. Defaults to the on-disk SQLite path; pass
        ``"sqlite:///:memory:"`` for tests, or set the ``TAXON_DATABASE_URL``
        environment variable to override at runtime.
    """
    resolved_url = _resolve_database_url(database_url)
    app = FastAPI(
        title="Taxon Species Search Dispatcher",
        version="0.1.0",
        lifespan=_lifespan,
    )
    # DEV ONLY: allow any origin while the frontend is served from a local
    # Vite dev server. Replace with an explicit allow-list before deploying.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.database_url = resolved_url

    @app.exception_handler(NotFoundError)
    def _handle_not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(404, exc.detail, None)

    @app.exception_handler(AmbiguousError)
    def _handle_ambiguous(_request: Request, exc: AmbiguousError) -> JSONResponse:
        return _error_response(409, exc.detail, exc.candidates)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    app.include_router(api_router)

    return app


def get_session(app: FastAPI) -> Iterator[Session]:
    """Yield a session bound to the app's engine.

    Convenience for endpoints that want a request-scoped session without
    pulling in FastAPI's dependency system at module import time.
    """
    state: AppState = app.state.app_state
    session = state.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Re-export response models so ``from taxon.api import TaxonResponse`` works.
from taxon.api.schemas import (
    CandidateRef,
    SpeciesPathResponse,
    TaxonResponse,
)

__all__ = [
    "DEFAULT_DATABASE_URL",
    "APIError",
    "AmbiguousError",
    "AppState",
    "CandidateRef",
    "ErrorResponse",
    "HealthResponse",
    "NotFoundError",
    "SpeciesPathResponse",
    "TaxonResponse",
    "create_app",
    "get_session",
]
