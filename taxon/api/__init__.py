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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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
    """Create the SQLAlchemy engine with sensible defaults for SQLite.

    In-memory SQLite (``sqlite:///:memory:``) normally creates a
    fresh database per connection, which means a session opened on
    one thread cannot see the schema created by another thread's
    lifespan. We pin the engine to a single shared connection via
    ``StaticPool`` so the schema lives for the lifetime of the
    process. File-backed SQLite is unaffected.
    """
    connect_args: dict[str, Any] = {}
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url == "sqlite:///:memory:":
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    kwargs["connect_args"] = connect_args
    return create_engine(database_url, **kwargs)


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

    # Mount the production frontend bundle when ``frontend/dist``
    # exists on disk. The check is opt-in so the API keeps working
    # during development (where the SPA is served by Vite on :5173)
    # and during tests (where the bundle is irrelevant). The
    # ``html=True`` flag tells Starlette to fall back to
    # ``index.html`` for client-side routes that do not have a
    # corresponding file on disk — the React Router in the SPA
    # handles the actual 404/200 logic once the page loads.
    _mount_frontend(app)

    return app


def _mount_frontend(app: FastAPI) -> None:
    """Mount the SPA bundle when ``frontend/dist`` exists on disk.

    The mount order matters: the API router is included above this
    function so ``/api/*`` and ``/healthz`` always win. The
    StaticFiles handler matches every other path. SPA client-side
    routes that resolve to non-existent files fall back to
    ``index.html`` so the React app can handle the route.

    The fallback is wired through a 404 exception handler so we
    do not need to register a catch-all route that would shadow
    the API routes. The handler only fires for paths the API
    router did not claim.
    """
    dist_dir = Path("frontend/dist")
    if not dist_dir.is_dir():
        return
    index_html = dist_dir / "index.html"
    if not index_html.is_file():
        return
    app.mount(
        "/",
        StaticFiles(directory=str(dist_dir), html=False),
        name="frontend",
    )

    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(
        _request: Request, exc: StarletteHTTPException
    ) -> FileResponse | JSONResponse:
        # Only intercept 404s; let every other status through.
        if exc.status_code != 404:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        return FileResponse(str(index_html), media_type="text/html")


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
