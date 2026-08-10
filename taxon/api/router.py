"""Versioned ``/api`` router placeholder.

Hierarchy endpoints (``/api/kingdoms``, ``/api/.../{name}``) land in Sub-PR
2B; species list, links, and the 409 ambiguity candidate endpoint land in
Sub-PR 2C. This file only registers the ``/api`` prefix and exposes a
``/_meta`` probe so we can prove the prefix is wired before any real
endpoint exists.

The ``/_meta`` route is intentionally minimal and MUST NOT be removed by
Sub-PRs 2B or 2C — it is the smoke check for the router being mounted at
all.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/_meta")
def api_meta() -> dict[str, str]:
    """Smoke check that confirms the ``/api`` prefix is mounted."""
    return {"phase": "2A"}
