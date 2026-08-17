"""HTTP-mapped exception classes raised by API endpoints.

Sub-PR 2A defined these exception types in :mod:`taxon.api` together
with the app factory. Sub-PR 2B moves them here so the router module
can import :class:`NotFoundError` without triggering a circular import
through :mod:`taxon.api`. The factory still re-exports them so callers
keep ``from taxon.api import NotFoundError`` working.
"""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    """Base class for HTTP-mapped domain errors raised by API endpoints."""

    status_code: int = 500
    detail: str = "internal server error"

    def __init__(self, detail: str | None = None, status_code: int | None = None) -> None:
        super().__init__(detail or self.detail)
        if detail is not None:
            self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(APIError):
    """Resource was not found; maps to HTTP 404."""

    status_code = 404
    detail = "not found"


class AmbiguousError(APIError):
    """Lookup matched multiple rows; maps to HTTP 409.

    The ``candidates`` payload is the breadcrumb list expected by the
    ambiguity picker UI in Sub-PR 5; endpoints raise this with the
    already-resolved list.
    """

    status_code = 409
    detail = "ambiguous"

    def __init__(
        self,
        candidates: list[dict[str, Any]],
        detail: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.candidates = candidates


__all__ = ["APIError", "AmbiguousError", "NotFoundError"]
