"""Uvicorn entrypoint for the FastAPI app.

Run with ``python -m taxon.main`` (or ``uvicorn taxon.api:create_app
--factory --reload`` directly). Sub-PR 2A only wires the factory, lifespan,
and ``/healthz`` probe — concrete endpoints land in Sub-PRs 2B and 2C.
"""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "taxon.api:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
