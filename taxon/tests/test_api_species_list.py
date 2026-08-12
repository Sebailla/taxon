r"""RED-first contract tests for the species-list endpoint.

Sub-PR 2C extends the \`/species\` leaf endpoint shipped by Sub-PR 2B
with two new behaviours:

1. Inclusion filters via the \`include\` query parameter (CSV of
   \`synonyms,extinct,uncertain,unassigned\`). Default behaviour stays
   accepted-only. Unknown values are silently ignored.
2. Pagination with a 500-item cap. A response that exceeds 500 items
   returns \`next_cursor\` so the client can request the next page;
   subsequent requests with that cursor return the next batch in a
   deterministic order.

The response shape from Sub-PR 2B (\`list[TaxonResponse]\`) is wrapped
in an envelope \`{items, next_cursor}\` so the pagination cursor has
somewhere to live. The leaf endpoint therefore no longer returns a
bare array — every test in this file expects the envelope.

Endpoint under test:

    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SPECIES_PATH = (
    "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/Girardinichthys/species"
)


def _species_fixture() -> str:
    r"""Two accepted species, one synonym, one extinct, under Girardinichthys.

    The marker prefixes (\`=\`, \`†\`) come from the WoRMS parser and
    translate to \`is_synonym\` / \`is_extinct\` flags on the row.
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
        "              Girardinichthys viviparus [species] {ID=urn:8}\n"
        "              =Girardinichthys synonymus [species] {ID=urn:9}\n"
        "              †Girardinichthys extinctus [species] {ID=urn:10}\n"
    )


def _empty_species_fixture() -> str:
    """Genus exists but has no species under it."""
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Girardinichthys [genus] {ID=urn:6}\n"
    )


def _wide_species_fixture(*, count: int) -> str:
    """One genus with ``count`` accepted species — drives the pagination cap."""
    lines = [
        "Biota [superdomain] {ID=urn:0}",
        "  Animalia [kingdom] {ID=urn:1}",
        "    Chordata [phylum] {ID=urn:2}",
        "      Actinopterygii [class] {ID=urn:3}",
        "        Cyprinodontiformes [order] {ID=urn:4}",
        "          Goodeidae [family] {ID=urn:5}",
        "            Girardinichthys [genus] {ID=urn:6}",
    ]
    for i in range(count):
        lines.append(f"              Girardinichthys sp{i:04d} [species] {{ID=urn:{7 + i}}}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def app_with_species(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_species_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_empty_species(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_empty_species_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_wide_species(tmp_path: Path) -> Any:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    def _build(count: int) -> FastAPI:
        db = tmp_path / f"taxon-{count}.db"
        src = tmp_path / f"dataset-{count}.txt"
        src.write_text(_wide_species_fixture(count=count), encoding="utf-8")
        import_dataset(src, db, batch_size=64)
        return create_app(database_url=f"sqlite:///{db}")

    return _build


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Default accepted-only behaviour
# ---------------------------------------------------------------------------


def test_species_list_default_returns_only_accepted(app_with_species: FastAPI) -> None:
    with _client(app_with_species) as client:
        body = client.get(SPECIES_PATH).json()

    names = [item["name"] for item in body["items"]]
    # Two accepted species; synonym + extinct excluded by default.
    assert names == [
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
    ]
    assert body["next_cursor"] is None


def test_species_list_envelope_shape(app_with_species: FastAPI) -> None:
    with _client(app_with_species) as client:
        body = client.get(SPECIES_PATH).json()

    assert set(body.keys()) == {"items", "next_cursor"}
    for item in body["items"]:
        # Each item keeps the Sub-PR 2B shape: id, name, display_name,
        # rank, parent_id + four marker booleans.
        assert set(item.keys()) >= {
            "id",
            "name",
            "display_name",
            "rank",
            "parent_id",
            "is_synonym",
            "is_extinct",
            "is_uncertain",
            "is_unassigned",
        }
        assert item["rank"] == "species"


def test_species_list_empty_genus_returns_empty_items(app_empty_species: FastAPI) -> None:
    with _client(app_empty_species) as client:
        body = client.get(SPECIES_PATH).json()

    assert body == {"items": [], "next_cursor": None}


# ---------------------------------------------------------------------------
# include filters
# ---------------------------------------------------------------------------


def test_species_list_include_synonyms_widens_result(app_with_species: FastAPI) -> None:
    with _client(app_with_species) as client:
        body = client.get(SPECIES_PATH, params={"include": "synonyms"}).json()

    names = {item["name"] for item in body["items"]}
    assert names == {
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
        "Girardinichthys synonymus",
    }


def test_species_list_include_extinct_widens_result(app_with_species: FastAPI) -> None:
    with _client(app_with_species) as client:
        body = client.get(SPECIES_PATH, params={"include": "extinct"}).json()

    names = {item["name"] for item in body["items"]}
    assert "Girardinichthys extinctus" in names


def test_species_list_include_multiple_combines_with_or_semantics(
    app_with_species: FastAPI,
) -> None:
    with _client(app_with_species) as client:
        body = client.get(
            SPECIES_PATH,
            params={"include": "synonyms,extinct"},
        ).json()

    names = {item["name"] for item in body["items"]}
    # All four classes returned: accepted + synonym + extinct.
    assert names == {
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
        "Girardinichthys synonymus",
        "Girardinichthys extinctus",
    }


def test_species_list_include_unknown_values_ignored(app_with_species: FastAPI) -> None:
    with _client(app_with_species) as client:
        body = client.get(
            SPECIES_PATH,
            params={"include": "nonsense,more-nonsense"},
        ).json()

    # Unknown values fall through to default accepted-only.
    names = {item["name"] for item in body["items"]}
    assert names == {
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
    }


def test_species_list_include_empty_value_keeps_default(app_with_species: FastAPI) -> None:
    with _client(app_with_species) as client:
        body = client.get(SPECIES_PATH, params={"include": ""}).json()

    names = {item["name"] for item in body["items"]}
    assert names == {
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
    }


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_species_list_under_cap_returns_no_cursor(app_wide_species: Any) -> None:
    app = app_wide_species(50)

    with _client(app) as client:
        body = client.get(SPECIES_PATH).json()

    assert len(body["items"]) == 50
    assert body["next_cursor"] is None


def test_species_list_at_cap_returns_no_cursor(app_wide_species: Any) -> None:
    """500 items is the inclusive cap — exactly 500 yields no cursor."""
    app = app_wide_species(500)

    with _client(app) as client:
        body = client.get(SPECIES_PATH).json()

    assert len(body["items"]) == 500
    assert body["next_cursor"] is None


def test_species_list_over_cap_returns_cursor(app_wide_species: Any) -> None:
    """501 items triggers pagination — first page is 500, cursor is set."""
    app = app_wide_species(501)

    with _client(app) as client:
        body = client.get(SPECIES_PATH).json()

    assert len(body["items"]) == 500
    assert isinstance(body["next_cursor"], str)
    assert body["next_cursor"] != ""


def test_species_list_cursor_advances_to_remaining_items(app_wide_species: Any) -> None:
    """Following the cursor returns the remaining items, no overlap."""
    app = app_wide_species(750)

    with _client(app) as client:
        first = client.get(SPECIES_PATH).json()
        assert len(first["items"]) == 500
        cursor = first["next_cursor"]
        assert cursor is not None

        second = client.get(SPECIES_PATH, params={"cursor": cursor}).json()

    assert len(second["items"]) == 250
    # No overlap between pages.
    first_names = {item["name"] for item in first["items"]}
    second_names = {item["name"] for item in second["items"]}
    assert first_names.isdisjoint(second_names)
    assert second["next_cursor"] is None


def test_species_list_pagination_order_is_deterministic(app_wide_species: Any) -> None:
    """Same query twice returns the same first page (cursor stable)."""
    app = app_wide_species(600)

    with _client(app) as client:
        a = client.get(SPECIES_PATH).json()
        b = client.get(SPECIES_PATH).json()

    assert a["items"] == b["items"]
    assert a["next_cursor"] == b["next_cursor"]


def test_species_list_pagination_works_with_include(app_wide_species: Any) -> None:
    """Pagination cap is total items, not accepted-only items."""
    app = app_wide_species(600)

    with _client(app) as client:
        body = client.get(SPECIES_PATH, params={"include": "extinct"}).json()

    assert len(body["items"]) == 500
    assert body["next_cursor"] is not None
