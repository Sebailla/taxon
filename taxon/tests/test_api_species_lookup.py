"""RED-first contract tests for the species-lookup endpoints.

Sub-PR 2C ships two lookup endpoints that resolve a species by name:

1. ``GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}``
   — lookup by **full breadcrumb**. The path's Kingdom → … → Genus
   anchors the resolution, so two species sharing a ``(genus, epithet)``
   pair under different parents are reachable as distinct URLs. This
   endpoint returns 200 with the species record + breadcrumb or 404
   when any segment fails to resolve.

2. ``GET /api/species/{genus}/{epithet}`` — lookup by **pair only**.
   The endpoint scans every genus named ``{genus}`` and returns one of
   three responses:
   - **200** when exactly one species matches.
   - **404** when no species match.
   - **409** when multiple species match; the response carries
     ``candidates[]`` with each candidate's full breadcrumb so the
     UI can render a disambiguation picker.

3. ``GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}/links``
   — emits the 12 dispatch URLs for a fully-resolved species. Returns
   404 when the breadcrumb fails; the path anchors the species so
   ambiguity cannot occur at this endpoint.

Both lookup paths are case-insensitive on the genus and epithet
segments.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BREADCRUMB_LOOKUP = (
    "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
    "Girardinichthys/multiradiatus"
)
PAIR_LOOKUP = "/api/species/Girardinichthys/multiradiatus"
LINKS_PATH = BREADCRUMB_LOOKUP + "/links"


def _unambiguous_fixture() -> str:
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Girardinichthys [genus] {ID=urn:6}\n"
        "              Girardinichthys multiradiatus [species] {ID=urn:7}\n"
    )


def _ambiguous_fixture() -> str:
    """Two independent hierarchies where the (genus, epithet) pair repeats.

    The pair ``(Girardinichthys, multiradiatus)`` exists both under
    Goodeidae (Animalia/Chordata) and under Rosaceae
    (Plantae/Magnoliophyta). The pair-only lookup therefore returns 409.
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Girardinichthys [genus] {ID=urn:6}\n"
        "              Girardinichthys multiradiatus [species] {ID=urn:7}\n"
        "  Plantae [kingdom] {ID=urn:11}\n"
        "    Magnoliophyta [phylum] {ID=urn:12}\n"
        "      Magnoliopsida [class] {ID=urn:13}\n"
        "        Rosales [order] {ID=urn:14}\n"
        "          Rosaceae [family] {ID=urn:15}\n"
        "            Girardinichthys [genus] {ID=urn:16}\n"
        "              Girardinichthys multiradiatus [species] {ID=urn:17}\n"
    )


@pytest.fixture
def app_unambiguous(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_unambiguous_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_ambiguous(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_ambiguous_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/{path}/{genus}/{epithet} — full-breadcrumb lookup (200/404)
# ---------------------------------------------------------------------------


def test_breadcrumb_lookup_returns_200_with_full_record(
    app_unambiguous: FastAPI,
) -> None:
    with _client(app_unambiguous) as client:
        response = client.get(BREADCRUMB_LOOKUP)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {
        "id",
        "canonical_name",
        "display_name",
        "markers",
        "breadcrumb",
    }
    assert body["canonical_name"] == "Girardinichthys multiradiatus"
    assert "Girardinichthys multiradiatus" in body["display_name"]
    assert set(body["markers"].keys()) == {
        "is_synonym",
        "is_extinct",
        "is_uncertain",
        "is_unassigned",
    }
    # Breadcrumb walks Kingdom → Genus (6 segments).
    assert body["breadcrumb"] == [
        "Animalia",
        "Chordata",
        "Actinopterygii",
        "Cyprinodontiformes",
        "Goodeidae",
        "Girardinichthys",
    ]


def test_breadcrumb_lookup_is_case_insensitive(app_unambiguous: FastAPI) -> None:
    with _client(app_unambiguous) as client:
        mixed = client.get(
            "/api/ANIMALIA/chordata/Actinopterygii/cyprinodontiformes/Goodeidae/"
            "GIRARDINICHTHYS/MULTIRADIATUS"
        )
        canonical = client.get(BREADCRUMB_LOOKUP)

    assert mixed.status_code == 200
    assert mixed.json()["id"] == canonical.json()["id"]


def test_breadcrumb_lookup_404_when_genus_unknown(app_unambiguous: FastAPI) -> None:
    with _client(app_unambiguous) as client:
        response = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Nonexistentus/multiradiatus"
        )

    assert response.status_code == 404
    assert "Nonexistentus" in response.json()["detail"]


def test_breadcrumb_lookup_404_when_epithet_unknown(
    app_unambiguous: FastAPI,
) -> None:
    with _client(app_unambiguous) as client:
        response = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Girardinichthys/nonexistentus"
        )

    assert response.status_code == 404
    assert "nonexistentus" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/species/{genus}/{epithet} — pair-only lookup (200/404/409)
# ---------------------------------------------------------------------------


def test_pair_lookup_returns_200_when_unique(app_unambiguous: FastAPI) -> None:
    with _client(app_unambiguous) as client:
        response = client.get(PAIR_LOOKUP)

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_name"] == "Girardinichthys multiradiatus"
    assert body["breadcrumb"][0] == "Animalia"


def test_pair_lookup_is_case_insensitive(app_unambiguous: FastAPI) -> None:
    with _client(app_unambiguous) as client:
        response = client.get("/api/species/GIRARDINICHTHYS/MULTIRADIATUS")

    assert response.status_code == 200
    assert response.json()["canonical_name"] == "Girardinichthys multiradiatus"


def test_pair_lookup_404_when_genus_unknown(app_unambiguous: FastAPI) -> None:
    with _client(app_unambiguous) as client:
        response = client.get("/api/species/Nonexistentus/species")

    assert response.status_code == 404
    assert "Nonexistentus" in response.json()["detail"]


def test_pair_lookup_404_when_epithet_unknown(app_unambiguous: FastAPI) -> None:
    with _client(app_unambiguous) as client:
        response = client.get("/api/species/Girardinichthys/nonexistentus")

    assert response.status_code == 404
    assert "nonexistentus" in response.json()["detail"]


def test_pair_lookup_distinguishes_404_from_409(app_unambiguous: FastAPI) -> None:
    """Zero matches → 404, never 409. The 409 path requires ≥2 matches."""
    with _client(app_unambiguous) as client:
        response = client.get("/api/species/Girardinichthys/nonexistentus")

    assert response.status_code == 404


def test_pair_lookup_returns_409_when_pair_collides(app_ambiguous: FastAPI) -> None:
    with _client(app_ambiguous) as client:
        response = client.get(PAIR_LOOKUP)

    assert response.status_code == 409
    body = response.json()
    assert "candidates" in body
    assert len(body["candidates"]) >= 2
    for candidate in body["candidates"]:
        assert set(candidate.keys()) >= {
            "id",
            "canonical_name",
            "display_name",
            "breadcrumb",
        }
        # Breadcrumb walks Kingdom → Genus (6 segments).
        assert len(candidate["breadcrumb"]) == 6


def test_pair_lookup_candidate_order_is_stable(app_ambiguous: FastAPI) -> None:
    with _client(app_ambiguous) as client:
        first = client.get(PAIR_LOOKUP).json()
        second = client.get(PAIR_LOOKUP).json()

    assert first["candidates"] == second["candidates"]
    # Order is alphabetical by Kingdom → Phylum → … → Genus.
    breadcrumbs = [c["breadcrumb"] for c in first["candidates"]]
    sorted_breadcrumbs = sorted(breadcrumbs, key=lambda b: tuple(b))
    assert breadcrumbs == sorted_breadcrumbs


def test_pair_lookup_disambiguates_with_full_path(app_ambiguous: FastAPI) -> None:
    """After a 409, the client can request either branch's full path
    and receive 200 — the breadcrumb lookup anchors on the kingdom so
    the resolution is fully qualified.
    """
    with _client(app_ambiguous) as client:
        animalia = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Girardinichthys/multiradiatus"
        )
        plantae = client.get(
            "/api/Plantae/Magnoliophyta/Magnoliopsida/Rosales/Rosaceae/"
            "Girardinichthys/multiradiatus"
        )

    assert animalia.status_code == 200
    assert plantae.status_code == 200
    assert animalia.json()["breadcrumb"][0] == "Animalia"
    assert plantae.json()["breadcrumb"][0] == "Plantae"
    # Each branch is a distinct row.
    assert animalia.json()["id"] != plantae.json()["id"]
