"""Database session dependency for FastAPI endpoints.

Endpoints declared in :mod:`taxon.api.router` depend on ``get_db`` to
receive a request-scoped SQLAlchemy session bound to the engine the
lifespan opened. The session is closed when the request finishes,
even when the endpoint raises.

The dependency reads the session factory from
``request.app.state.app_state`` so the helper stays decoupled from
the concrete ``create_app`` factory — the only contract is that the
active app exposes an ``app_state`` attribute on its ``state`` namespace
with a ``SessionLocal`` callable.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    """Yield a session bound to ``request.app.state.app_state.engine``.

    FastAPI injects the active ``Request`` so we can reach the engine
    without the router module depending on the lifespan internals. The
    ``app_state`` attribute is duck-typed — anything exposing
    ``SessionLocal`` works, so tests can swap the factory without
    going through the real ``create_app`` factory.
    """
    state = request.app.state.app_state
    session = state.SessionLocal()
    try:
        yield session
    finally:
        session.close()


__all__ = ["get_db"]
