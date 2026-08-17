"""RED-first contract tests for the eight workspace endpoints.

The species-folder-explorer change ships eight new endpoints,
all registered BEFORE the ``/{path:path}/taxon-links`` catch-all:

    POST   /api/explored/{g}/{e}             200 (with species row)
    DELETE /api/explored/{g}/{e}             204 (idempotent)
    GET    /api/explored/list                200 {species:[]}
    POST   /api/species-folder/{g}/{e}       201 / 409 / 404 / 500
    GET    /api/species-folder/{g}/{e}       200 / 404
    POST   /api/link-visited/{g}/{e}/{src}   204
    DELETE /api/link-visited/{g}/{e}/{src}   204 (idempotent)
    GET    /api/link-visited/{g}/{e}         200 {sources:[]}

Each test pins one shape from the spec; together they prove the
contract is intact and the resolver walks by ``(genus, epithet)``
rather than by ``taxa.id``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _fixture() -> str:
    """Tiny lineage with one unambiguous species for happy-path tests."""
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Mammalia [class] {ID=urn:3}\n"
        "        Carnivora [order] {ID=urn:4}\n"
        "          Felidae [family] {ID=urn:5}\n"
        "            Panthera [genus] {ID=urn:6}\n"
        "              Panthera tigris [species] {ID=urn:7}\n"
    )


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    """Build a FastAPI app backed by an in-memory SQLite imported from the fixture."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    # Pin AQUALIFE_ROOT into tmp_path so the folder endpoint never
    # touches the real on-disk ``./Proyecto-Aqualife/`` tree.
    aqualife = tmp_path / "Proyecto-Aqualife"
    os.environ["AQUALIFE_ROOT"] = str(aqualife)
    try:
        return create_app(database_url=f"sqlite:///{db}")
    finally:
        os.environ.pop("AQUALIFE_ROOT", None)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # The ``with`` block drives the ``lifespan`` context so
    # ``app.state.app_state`` is populated before the first request.
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# /api/explored
# ---------------------------------------------------------------------------


def test_post_explored_returns_species_row(client: TestClient) -> None:
    """First POST returns 200 with the species row + explored envelope fields."""
    response = client.post("/api/explored/Panthera/tigris")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["canonical_name"] == "Panthera tigris"
    assert body["genus"] == "Panthera"
    assert body["epithet"] == "tigris"
    assert body["explored_at"]


def test_post_explored_idempotent_refines_timestamp(client: TestClient) -> None:
    """Re-posting the same pair returns 200 (no 409) and refreshes the timestamp."""
    first = client.post("/api/explored/Panthera/tigris")
    assert first.status_code == 200
    second = client.post("/api/explored/Panthera/tigris")
    assert second.status_code == 200
    # Both succeed; the second row is still keyed on (Panthera, tigris).
    listing = client.get("/api/explored/list")
    assert listing.status_code == 200
    species = listing.json()["species"]
    assert len(species) == 1
    assert species[0]["genus"] == "Panthera"
    assert species[0]["epithet"] == "tigris"


def test_post_explored_404_when_unknown(client: TestClient) -> None:
    """POST on an unknown species returns 404 (not 500)."""
    response = client.post("/api/explored/Nonexistentus/species")
    assert response.status_code == 404, response.text


def test_delete_explored_returns_204(client: TestClient) -> None:
    """DELETE on an existing row returns 204."""
    client.post("/api/explored/Panthera/tigris")
    response = client.delete("/api/explored/Panthera/tigris")
    assert response.status_code == 204


def test_delete_explored_missing_returns_204(client: TestClient) -> None:
    """DELETE on a missing row is a no-op — 204, NOT 404."""
    response = client.delete("/api/explored/Panthera/tigris")
    assert response.status_code == 204


def test_get_explored_list_empty_envelope(client: TestClient) -> None:
    """Empty explored set returns 200 with ``{"species": []}`` (not 404)."""
    response = client.get("/api/explored/list")
    assert response.status_code == 200
    assert response.json() == {"species": []}


def test_get_explored_list_returns_rows(client: TestClient) -> None:
    """After POST, the list returns the row."""
    client.post("/api/explored/Panthera/tigris")
    response = client.get("/api/explored/list")
    assert response.status_code == 200
    body = response.json()
    assert len(body["species"]) == 1
    assert body["species"][0]["genus"] == "Panthera"
    assert body["species"][0]["epithet"] == "tigris"


# ---------------------------------------------------------------------------
# /api/species-folder
# ---------------------------------------------------------------------------


def test_post_species_folder_returns_201_with_path(client: TestClient) -> None:
    """First POST returns 201 with ``{"path": "...Panthera tigris"}``."""
    response = client.post("/api/species-folder/Panthera/tigris")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["genus"] == "Panthera"
    assert body["epithet"] == "tigris"
    assert body["exists"] is True
    assert body["path"].endswith("Panthera tigris")
    # The folder must exist on disk after the response.
    assert Path(body["path"]).is_dir()


def test_post_species_folder_repeat_returns_409(client: TestClient) -> None:
    """Repeat POST returns 409 with an ErrorResponse detail."""
    client.post("/api/species-folder/Panthera/tigris")
    response = client.post("/api/species-folder/Panthera/tigris")
    assert response.status_code == 409, response.text
    assert "detail" in response.json()


def test_post_species_folder_404_when_unknown(client: TestClient) -> None:
    """POST on an unknown species returns 404."""
    response = client.post("/api/species-folder/Nonexistentus/species")
    assert response.status_code == 404, response.text


def test_get_species_folder_returns_path(client: TestClient) -> None:
    """After POST, GET returns the same path."""
    created = client.post("/api/species-folder/Panthera/tigris").json()
    response = client.get("/api/species-folder/Panthera/tigris")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"] == created["path"]
    assert body["exists"] is True


def test_get_species_folder_missing_returns_404(client: TestClient) -> None:
    """GET on a missing row returns 404."""
    response = client.get("/api/species-folder/Panthera/tigris")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# /api/link-visited
# ---------------------------------------------------------------------------


def test_post_link_visited_returns_204(client: TestClient) -> None:
    """First POST returns 204 and persists the row."""
    response = client.post("/api/link-visited/Panthera/tigris/Wikipedia")
    assert response.status_code == 204, response.text


def test_post_link_visited_idempotent(client: TestClient) -> None:
    """Re-posting the same source returns 204 (no 409)."""
    first = client.post("/api/link-visited/Panthera/tigris/Wikipedia")
    second = client.post("/api/link-visited/Panthera/tigris/Wikipedia")
    assert first.status_code == 204
    assert second.status_code == 204


def test_post_link_visited_404_when_unknown_species(client: TestClient) -> None:
    """POST on an unknown species returns 404."""
    response = client.post("/api/link-visited/Nonexistentus/species/Wikipedia")
    assert response.status_code == 404, response.text


def test_delete_link_visited_returns_204(client: TestClient) -> None:
    """DELETE on an existing row returns 204."""
    client.post("/api/link-visited/Panthera/tigris/Wikipedia")
    response = client.delete("/api/link-visited/Panthera/tigris/Wikipedia")
    assert response.status_code == 204


def test_delete_link_visited_missing_returns_204(client: TestClient) -> None:
    """DELETE on a missing row is a no-op — 204, NOT 404."""
    response = client.delete("/api/link-visited/Panthera/tigris/Wikipedia")
    assert response.status_code == 204


def test_get_link_visited_empty_envelope(client: TestClient) -> None:
    """Empty visited set returns 200 with ``{"sources": []}`` (not 404)."""
    response = client.get("/api/link-visited/Panthera/tigris")
    assert response.status_code == 200
    body = response.json()
    assert body["genus"] == "Panthera"
    assert body["epithet"] == "tigris"
    assert body["sources"] == []


def test_get_link_visited_returns_rows(client: TestClient) -> None:
    """After POST, the visit list carries the source label and timestamp."""
    client.post("/api/link-visited/Panthera/tigris/Wikipedia")
    client.post("/api/link-visited/Panthera/tigris/Google")
    response = client.get("/api/link-visited/Panthera/tigris")
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 2
    labels = sorted(item["source"] for item in sources)
    assert labels == ["Google", "Wikipedia"]
    for item in sources:
        assert item["visited_at"]


def test_get_link_visited_keys_on_source_label_not_url(client: TestClient) -> None:
    """The endpoint keys on the source label (canonical name), not the substituted URL."""
    # The endpoint URL is ``/Wikipedia`` (canonical name); the resolver
    # never decodes a substituted URL because URLs change per query.
    response = client.post("/api/link-visited/Panthera/tigris/Wikipedia")
    assert response.status_code == 204
    listing = client.get("/api/link-visited/Panthera/tigris").json()
    assert listing["sources"][0]["source"] == "Wikipedia"


# ---------------------------------------------------------------------------
# Registration order — workspace endpoints come BEFORE the catch-all
# ---------------------------------------------------------------------------


def test_workspace_endpoints_registered_before_taxon_links_catchall(
    client: TestClient,
) -> None:
    """The eight workspace endpoints MUST beat the ``/{path:path}/taxon-links`` catch-all.

    Without the right registration order, FastAPI would match the
    catch-all path parameter against the literal ``explored``,
    ``species-folder``, or ``link-visited`` segment and return 404
    instead of the workspace handler's 200/201. This test pins that
    discipline so a future regression that reorders the routes fails
    loudly here.
    """
    explored = client.post("/api/explored/Panthera/tigris")
    folder_get = client.get("/api/species-folder/Panthera/tigris")
    link_get = client.get("/api/link-visited/Panthera/tigris")

    assert explored.status_code == 200, explored.text
    assert folder_get.status_code in (200, 404), folder_get.text
    assert link_get.status_code == 200, link_get.text


def test_workspace_endpoints_do_not_shadow_tree_endpoints(
    client: TestClient,
) -> None:
    """The workspace registration must NOT shadow the existing tree endpoints."""
    # The /api/tree/children endpoint has its own regression test in
    # test_api_router_tree. We only assert it stays reachable here.
    kingdoms = client.get("/api/kingdoms")
    assert kingdoms.status_code == 200, kingdoms.text
