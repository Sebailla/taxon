"""RED-first contract tests for the hierarchy endpoints.

These tests cover Sub-PR 2B only:
- ``GET /api/kingdoms`` lists the root taxa (kingdoms) sorted by name.
- The path-name cascade ``GET /api/{kingdom}/{...}/{genus}/species`` resolves
  each segment case-insensitively against the canonical ``Taxon.name`` and
  returns only the direct children at the next rank down.
- ``display_name`` is preserved verbatim (including author citations and
  status markers) regardless of the case-normalised lookup key.
- Each lookup is rooted in the parent identified by the previous segment,
  so two same-named taxa under different parents never collide (the path's
  rank context disambiguates them by construction).
- A 404 is returned when any segment in the path does not match a taxon
  under the required parent at that rank. The error body identifies which
  segment failed to resolve.
- Children are sorted alphabetically by canonical ``name`` so the response
  is deterministic across requests.

Endpoint coverage matrix:

    GET /api/kingdoms
    GET /api/{kingdom}/phyla
    GET /api/{kingdom}/{phylum}/classes
    GET /api/{kingdom}/{phylum}/{class}/orders
    GET /api/{kingdom}/{phylum}/{class}/{order}/families
    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/genera
    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species

The species list is the leaf of the cascade and is what the frontend's
sixth scrolling panel renders; it deliberately ships in 2B so the
cascade UI has real data to render. Inclusion filters and per-species
links land in Sub-PR 2C.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

HIERARCHY_FIXTURE = (
    "Biota [superdomain] {ID=urn:0}\n"
    "  Animalia [kingdom] {ID=urn:1}\n"
    "    Chordata [phylum] {ID=urn:2}\n"
    "      Actinopterygii [class] {ID=urn:3}\n"
    "        Cyprinodontiformes [order] {ID=urn:4}\n"
    "          Goodeidae [family] {ID=urn:5}\n"
    "            Girardinichthys [genus] {ID=urn:6}\n"
    "              Girardinichthys multiradiatus [species] {ID=urn:7}\n"
    "              Girardinichthys viviparus [species] {ID=urn:8}\n"
    "            Ilyodon [genus] {ID=urn:9}\n"
    "              Ilyodon furcidens [species] {ID=urn:10}\n"
    "  Plantae [kingdom] {ID=urn:11}\n"
    "    Magnoliophyta [phylum] {ID=urn:12}\n"
    "      Magnoliopsida [class] {ID=urn:13}\n"
    "        Rosales [order] {ID=urn:14}\n"
    "          Rosaceae [family] {ID=urn:15}\n"
    "            Rubus [genus] {ID=urn:16}\n"
    "              Rubus idaeus [species] {ID=urn:17}\n"
)


@pytest.fixture
def seeded_app(tmp_path: Path) -> FastAPI:
    """Build an app whose DB is preloaded with ``HIERARCHY_FIXTURE``.

    The on-disk SQLite path lets ``import_dataset`` do a clean file write
    before the app's lifespan opens it for serving. The lifespan still
    creates the schema because ``Base.metadata.create_all`` is part of the
    in-memory bootstrap — but for an on-disk DB we drop+recreate first
    so the test starts from a known schema state.
    """
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db_path = tmp_path / "taxon.db"
    src_path = tmp_path / "dataset.txt"
    src_path.write_text(HIERARCHY_FIXTURE, encoding="utf-8")
    import_dataset(src_path, db_path, batch_size=64)

    app = create_app(database_url=f"sqlite:///{db_path}")
    return app


@pytest.fixture
def seeded_app_custom(tmp_path: Path) -> Any:
    """Factory for apps seeded with a caller-supplied fixture string."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    def _build(fixture_text: str) -> FastAPI:
        db_path = tmp_path / "taxon.db"
        src_path = tmp_path / "dataset.txt"
        src_path.write_text(fixture_text, encoding="utf-8")
        import_dataset(src_path, db_path, batch_size=64)
        return create_app(database_url=f"sqlite:///{db_path}")

    return _build


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/kingdoms
# ---------------------------------------------------------------------------


def test_kingdoms_endpoint_lists_root_taxa_sorted_by_name(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/kingdoms")

    assert response.status_code == 200
    body = response.json()
    # Two kingdoms from the fixture: Animalia, Plantae.
    assert [item["name"] for item in body] == ["Animalia", "Plantae"]
    # Determinism: every item carries id/name/display_name.
    for item in body:
        assert set(item.keys()) >= {"id", "name", "display_name"}
        # ``display_name`` preserves the rank suffix added by the
        # parser (e.g. ``Animalia [kingdom]``); ``name`` is the clean
        # canonical key for lookup. They MUST stay independent.
        assert item["name"] != item["display_name"]
        assert item["name"] in item["display_name"]


def test_kingdoms_endpoint_excludes_non_root_taxa(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        body = client.get("/api/kingdoms").json()

    names = {item["name"] for item in body}
    # Chordata is a phylum (not a kingdom) so it MUST NOT appear at the root.
    assert "Chordata" not in names
    assert "Biota" not in names  # Biota is a superdomain, not a kingdom


# ---------------------------------------------------------------------------
# /api/{kingdom}/phyla
# ---------------------------------------------------------------------------


def test_phyla_endpoint_returns_direct_children_of_kingdom(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/Animalia/phyla")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == ["Chordata"]


def test_phyla_endpoint_is_case_insensitive(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/animalia/phyla")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Chordata"]


def test_phyla_endpoint_404_when_kingdom_unknown(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/Marsupialia/phyla")

    assert response.status_code == 404
    body = response.json()
    assert "Marsupialia" in body["detail"]


# ---------------------------------------------------------------------------
# /api/{kingdom}/{phylum}/classes
# ---------------------------------------------------------------------------


def test_classes_endpoint_returns_direct_children_of_phylum(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/Animalia/Chordata/classes")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Actinopterygii"]


def test_classes_endpoint_404_when_phylum_does_not_belong_to_kingdom(
    seeded_app: FastAPI,
) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/Plantae/Chordata/classes")

    assert response.status_code == 404
    assert "Chordata" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/{kingdom}/{phylum}/{class}/orders
# ---------------------------------------------------------------------------


def test_orders_endpoint_returns_direct_children_of_class(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/Animalia/Chordata/Actinopterygii/orders")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Cyprinodontiformes"]


# ---------------------------------------------------------------------------
# /api/{kingdom}/{phylum}/{class}/{order}/families
# ---------------------------------------------------------------------------


def test_families_endpoint_returns_direct_children_of_order(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/families")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Goodeidae"]


# ---------------------------------------------------------------------------
# /api/{kingdom}/{phylum}/{class}/{order}/{family}/genera
# ---------------------------------------------------------------------------


def test_genera_endpoint_returns_direct_children_of_family_sorted(
    seeded_app: FastAPI,
) -> None:
    with _client(seeded_app) as client:
        response = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/genera"
        )

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    # Two genera: Girardinichthys, Ilyodon — alphabetical.
    assert names == ["Girardinichthys", "Ilyodon"]


def test_genera_endpoint_is_case_insensitive(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get(
            "/api/animalia/chordata/actinopterygii/cyprinodontiformes/goodeidae/genera"
        )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "Girardinichthys",
        "Ilyodon",
    ]


# ---------------------------------------------------------------------------
# /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species
# ---------------------------------------------------------------------------


def test_species_endpoint_returns_direct_children_of_genus(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Girardinichthys/species"
        )

    assert response.status_code == 200
    body = response.json()
    names = [item["name"] for item in body]
    # Two species under Girardinichthys, alphabetical.
    assert names == [
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
    ]
    # Every species row carries the rank marker and its parent genus id.
    for item in body:
        assert item["rank"] == "species"
        assert item["parent_id"] is not None


def test_species_endpoint_404_when_genus_unknown(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Nonexistentus/species"
        )

    assert response.status_code == 404
    assert "Nonexistentus" in response.json()["detail"]


def test_species_endpoint_404_when_family_does_not_belong_to_order(
    seeded_app: FastAPI,
) -> None:
    with _client(seeded_app) as client:
        response = client.get(
            "/api/Plantae/Magnoliophyta/Magnoliopsida/Rosales/Rosaceae/Girardinichthys/species"
        )

    assert response.status_code == 404
    # The "wrong parent" path is still a not-found; the detail identifies the
    # last segment because the resolver walks the path segment-by-segment.
    assert "Girardinichthys" in response.json()["detail"]


# ---------------------------------------------------------------------------
# display_name preservation and case-insensitive semantics
# ---------------------------------------------------------------------------


def test_display_name_preserved_verbatim_in_lookup(seeded_app_custom: Any) -> None:
    """A taxon whose canonical name has been normalised must still surface
    its source label including author citations in ``display_name``.
    """
    fixture = (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Girardinichthys [genus] {ID=urn:6}\n"
        "              Girardinichthys multiradiatus (Meek, 1904) [species] "
        "{ID=urn:7}\n"
    )
    app = seeded_app_custom(fixture)

    with _client(app) as client:
        body = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Girardinichthys/species"
        ).json()

    # ``name`` is the canonical key without author citation.
    assert body[0]["name"] == "Girardinichthys multiradiatus"
    # ``display_name`` keeps the citation plus the rank suffix the parser
    # appends; it is verbatim from the source row.
    assert body[0]["display_name"] == ("Girardinichthys multiradiatus (Meek, 1904) [species]")


def test_path_resolution_walks_segment_by_segment(seeded_app: FastAPI) -> None:
    """A name that appears at multiple ranks MUST still resolve correctly
    because each segment is searched only under its required parent.

    The fixture has ``Chordata`` only under Animalia; if the resolver
    accepted any taxon named ``Chordata`` regardless of parent, the
    second call below would still 200 (it happens to exist), but the
    Plantae path proves the resolver rejects mismatched parents.
    """
    with _client(seeded_app) as client:
        wrong_parent = client.get("/api/Plantae/Chordata/classes")

    assert wrong_parent.status_code == 404


# ---------------------------------------------------------------------------
# Empty-results contract
# ---------------------------------------------------------------------------


def test_children_endpoint_returns_empty_list_when_parent_has_no_children(
    seeded_app_custom: Any,
) -> None:
    """A parent with no children at the requested rank returns ``[]`` with
    status 200, not 404. This keeps the cascade UI from having to special-
    case ``phylum with no classes`` vs ``phylum does not exist``.
    """
    fixture = (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
    )
    app = seeded_app_custom(fixture)

    with _client(app) as client:
        body = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/genera"
        )

    assert body.status_code == 200
    assert body.json() == []


# ---------------------------------------------------------------------------
# Marker flags survive the lookup
# ---------------------------------------------------------------------------


def test_species_endpoint_preserves_marker_flags_from_db(
    seeded_app_custom: Any,
) -> None:
    """A species marked extinct or synonym must surface those flags in the
    response so the UI can filter without re-querying.
    """
    fixture = (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Girardinichthys [genus] {ID=urn:6}\n"
        "              †Girardinichthys multiradiatus [species] {ID=urn:7}\n"
        "              =Girardinichthys viviparus [species] {ID=urn:8}\n"
    )
    app = seeded_app_custom(fixture)

    with _client(app) as client:
        body = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Girardinichthys/species"
        ).json()

    by_name = {item["name"]: item for item in body}
    assert by_name["Girardinichthys multiradiatus"]["is_extinct"] is True
    assert by_name["Girardinichthys viviparus"]["is_synonym"] is True
