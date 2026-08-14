"""RED-first contract tests for the GBIF-backed router endpoints.

The router takes a :class:`GbifClient` per request via FastAPI's
``Depends`` so tests can inject a transport-stubbed client and
exercise the HTTP shape without hitting the public GBIF API.

The tests pin three contracts:

- ``GET /api/kingdoms`` returns the kingdom list.
- ``GET /api/path-children?path=A|B|C`` returns the children of
  the deepest resolved taxon.
- ``GET /api/species-list?path=A|B|C|...|GENUS`` returns the
  species children of the deepest resolved genus.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taxon.api.router import _get_gbif_client

# ---------------------------------------------------------------------------
# Stub client and transport — a tiny in-process GBIF mock.
# ---------------------------------------------------------------------------


class _StubClient:
    """Drop-in :class:`GbifClient` that serves canned responses.

    The tests construct a transport (a dict of URL → response),
    wrap it in an httpx Client, and pass the client to the stub.
    The stub forwards ``search`` and ``get_children`` to the
    transport and skips the actual HTTP call.
    """

    def __init__(self, transport: httpx.MockTransport) -> None:
        # Pin the base URL so the stub can match full URLs
        # without the path being misinterpreted as relative.
        self._client = httpx.Client(
            transport=transport,
            base_url="https://api.gbif.org",
        )
        self._requests: list[str] = []

    def search(
        self,
        name: str,
        rank: str | None = None,
        higher_taxon_key: int | None = None,
        accepted_only: bool = True,
        limit: int = 20,
    ) -> list[Any]:
        params: dict[str, Any] = {
            "q": name,
            "limit": limit,
            "offset": 0,
            "status": "ACCEPTED",
        }
        if rank is not None:
            params["rank"] = rank
        if higher_taxon_key is not None:
            params["higherTaxonKey"] = higher_taxon_key
        url = f"/v1/species/search?{urlencode(params)}"
        self._requests.append(url)
        r = self._client.get(url)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [self._parse(row) for row in r.json().get("results", [])]

    def get_children(
        self,
        key: int,
        limit: int = 300,
        offset: int = 0,
        rank: str | None = None,
    ) -> list[Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if rank is not None:
            params["rank"] = rank
        url = f"/v1/species/{key}/children?{urlencode(params)}"
        self._requests.append(url)
        r = self._client.get(url)
        r.raise_for_status()
        return [self._parse(row) for row in r.json().get("results", [])]

    @staticmethod
    def _parse(row: dict[str, Any]) -> Any:
        """Translate a GBIF row into a ``GbifTaxon`` dataclass."""
        from taxon.gbif import GbifTaxon

        return GbifTaxon(
            key=row["key"],
            nub_key=row.get("nubKey", row["key"]),
            canonical_name=row.get("canonicalName") or row["scientificName"],
            scientific_name=row["scientificName"],
            rank=row["rank"],
            kingdom=row.get("kingdom"),
            phylum=row.get("phylum"),
            order=row.get("order"),
            family=row.get("family"),
            genus=row.get("genus"),
            species=row.get("species"),
            parent_key=row.get("parentKey"),
            parent=row.get("parent"),
            num_children=row.get("numDescendants"),
        )


def _app_with_client(client: _StubClient) -> FastAPI:
    """Build an app with the GBIF client dependency overridden."""
    from taxon.api import create_app

    app = create_app(database_url="sqlite:///:memory:")
    app.dependency_overrides[_get_gbif_client] = lambda: client
    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _row(key: int, name: str, rank: str, parent_key: int | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "nubKey": key,
        "canonicalName": name,
        "scientificName": name,
        "rank": rank,
        "parentKey": parent_key,
        "parent": None,
        "numDescendants": 0,
    }


def _search_url(name: str, rank: str | None = None, parent_key: int | None = None) -> str:
    params: dict[str, Any] = {"q": name, "limit": 20, "offset": 0, "status": "ACCEPTED"}
    if rank is not None:
        params["rank"] = rank
    if parent_key is not None:
        params["higherTaxonKey"] = parent_key
    return f"/v1/species/search?{urlencode(params)}"


def _children_url(key: int) -> str:
    return f"/v1/species/{key}/children?{urlencode({'limit': 300, 'offset': 0})}"


# ---------------------------------------------------------------------------
# /api/kingdoms
# ---------------------------------------------------------------------------


def test_kingdoms_returns_root_taxa() -> None:
    """GBIF exposes 8 canonical kingdoms. The endpoint returns
    them sorted by canonical name."""
    transport = httpx.MockTransport(
        lambda req: (
            httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [
                        _row(1, "Animalia", "KINGDOM"),
                        _row(5, "Fungi", "KINGDOM"),
                        _row(6, "Plantae", "KINGDOM"),
                    ],
                },
            )
            if req.url.path == "/v1/species/search"
            else httpx.Response(404)
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/kingdoms")
    assert response.status_code == 200
    body = response.json()
    names = [item["name"] for item in body]
    assert names == sorted(names)
    assert "Animalia" in names


# ---------------------------------------------------------------------------
# /api/path-children
# ---------------------------------------------------------------------------


def test_path_children_returns_direct_children() -> None:
    """For Animalia, the endpoint returns its direct children."""
    transport = httpx.MockTransport(
        lambda req: {
            ("GET", _search_url("Animalia", rank="KINGDOM")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [_row(1, "Animalia", "KINGDOM")],
                },
            ),
            ("GET", _children_url(1) + "&rank=PHYLUM"): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "results": [
                        _row(44, "Chordata", "PHYLUM"),
                        _row(42, "Annelida", "PHYLUM"),
                        _row(54, "Arthropoda", "PHYLUM"),
                    ],
                },
            ),
        }.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/path-children?path=Animalia")
    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Animalia"
    names = {child["name"] for child in body["children"]}
    assert {"Chordata", "Annelida", "Arthropoda"} <= names
    assert body["next_rank_hint"] == "phylum"


def test_path_children_404_when_segment_unknown() -> None:
    """A typo returns 404 — the cascade UI surfaces the failing
    segment in the error body so the user can re-pick."""
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/path-children?path=Nonexistent")
    assert response.status_code == 404
    assert "Nonexistent" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/species-list
# ---------------------------------------------------------------------------


def test_species_list_returns_species_under_genus() -> None:
    """A 6-segment path that lands at Panthera returns its species."""
    transport = httpx.MockTransport(
        lambda req: {
            ("GET", _search_url("Animalia", rank="KINGDOM")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [_row(1, "Animalia", "KINGDOM")],
                },
            ),
            ("GET", _search_url("Chordata", rank="PHYLUM", parent_key=1)): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [_row(44, "Chordata", "PHYLUM", parent_key=1)],
                },
            ),
            ("GET", _search_url("Carnivora", rank="ORDER", parent_key=44)): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [_row(732, "Carnivora", "ORDER", parent_key=44)],
                },
            ),
            ("GET", _search_url("Felidae", rank="FAMILY", parent_key=732)): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [_row(9702, "Felidae", "FAMILY", parent_key=732)],
                },
            ),
            ("GET", _search_url("Panthera", rank="GENUS", parent_key=9702)): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "results": [_row(9703, "Panthera", "GENUS", parent_key=9702)],
                },
            ),
            ("GET", _children_url(9703) + "&rank=SPECIES"): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "results": [
                        _row(9704, "Panthera leo", "SPECIES"),
                        _row(9705, "Panthera onca", "SPECIES"),
                    ],
                },
            ),
        }.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get(
            "/api/species-list?path=Animalia%7CChordata%7CCarnivora%7CFelidae%7CPanthera"
        )
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert {"Panthera leo", "Panthera onca"} <= names
