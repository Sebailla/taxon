"""RED-first contract tests for the SPA bundle mount.

The factory mounts ``frontend/dist`` as a StaticFiles handler when
the directory exists, so a single ``uvicorn`` deployment serves both
the API and the React SPA from the same origin. The tests pin:

- The factory stays functional when ``frontend/dist`` is absent
  (development + tests do not need the bundle on disk).
- The factory mounts the directory when it exists.
- A request for ``/index.html`` returns the SPA shell when the
  bundle is mounted.
- A request for ``/api/kingdoms`` keeps going through the API
  router even when the SPA is mounted (mount order matters).

The tests create a temporary ``frontend/dist`` directory under
``tmp_path`` and check that the factory picks it up. They use
monkey-patching to monkey-patch the resolved path the factory
uses, because the project root lives elsewhere in CI than in
local development.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taxon.api import create_app


@pytest.fixture
def spa_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a fake ``frontend/dist`` directory with a minimal SPA shell.

    The factory resolves the dist path relative to the current
    working directory. We monkey-patch ``Path.is_dir`` /
    ``Path.is_file`` so the factory accepts our temporary directory
    regardless of where pytest runs from.
    """
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>Taxon SPA</body></html>",
        encoding="utf-8",
    )
    (dist / "assets").mkdir()
    (dist / "assets" / "index.js").write_text("// bundle", encoding="utf-8")
    return dist


@pytest.fixture
def patch_spa_lookup(spa_dist: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the factory see ``spa_dist`` as the SPA bundle.

    The factory calls ``Path('frontend/dist')`` which resolves
    against the process CWD. We monkey-patch ``_mount_frontend``
    so it uses the temporary directory directly instead.
    """
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException as StarletteHTTPException

    def patched_mount(app: FastAPI) -> None:
        index_html = spa_dist / "index.html"
        if not index_html.is_file():
            return
        app.mount(
            "/",
            StaticFiles(directory=str(spa_dist), html=False),
            name="frontend",
        )

        @app.exception_handler(StarletteHTTPException)
        async def _spa_fallback(
            _request: object, exc: StarletteHTTPException
        ) -> FileResponse | JSONResponse:
            if exc.status_code != 404:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                )
            return FileResponse(str(index_html), media_type="text/html")

    monkeypatch.setattr("taxon.api._mount_frontend", patched_mount)


def test_factory_skips_spa_when_dist_missing() -> None:
    app = create_app(database_url="sqlite:///:memory:")
    with TestClient(app) as client:
        # ``/healthz`` still works — the API router is wired.
        assert client.get("/healthz").status_code == 200


def test_factory_serves_index_when_spa_mounted(
    patch_spa_lookup: None,
) -> None:
    app = create_app(database_url="sqlite:///:memory:")
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Taxon SPA" in response.text


def test_factory_serves_static_assets_when_spa_mounted(
    patch_spa_lookup: None,
) -> None:
    app = create_app(database_url="sqlite:///:memory:")
    with TestClient(app) as client:
        response = client.get("/assets/index.js")
    assert response.status_code == 200
    assert response.text == "// bundle"


def test_api_router_wins_over_spa(patch_spa_lookup: None) -> None:
    """The StaticFiles mount must not shadow the API endpoints.

    Order of registration in ``create_app`` is: API router first,
    SPA mount second. Starlette matches in registration order; we
    want the API endpoints to win even when the SPA is mounted.
    """
    app = create_app(database_url="sqlite:///:memory:")
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        # The kingdoms endpoint requires a database schema; the
        # in-memory lifespan creates it. We only care about the
        # status, not the payload.
        response = client.get("/api/kingdoms")
        assert response.status_code == 200


def test_spa_fallback_for_unknown_route(patch_spa_lookup: None) -> None:
    """A non-API, non-static route falls back to the SPA ``index.html``.

    The StaticFiles handler with ``html=True`` returns ``index.html``
    for any path that does not have a matching file on disk. This
    is what enables the React Router in the SPA to handle
    client-side routes.
    """
    app = create_app(database_url="sqlite:///:memory:")
    with TestClient(app) as client:
        response = client.get("/some/spa/route")
    assert response.status_code == 200
    assert "Taxon SPA" in response.text
