"""RED-first contract tests for the per-species dispatch-URL endpoint.

Sub-PR 2C adds a new endpoint that emits the 12 search-source URLs
captured from the legacy spreadsheet for a resolved species:

    GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}/links

The endpoint consumes the templates loaded by
:mod:`taxon.search_links` and substitutes the species query with
:func:`urllib.parse.quote_plus` so spaces become `+` and special
characters are percent-encoded. The Sci-hub URL MUST use
`https://sci-hub.ru/match/{q}`.

The endpoint requires the species to resolve via the full breadcrumb;
the path anchors on the kingdom so ambiguity cannot occur here. A
404 fires when any segment fails to resolve.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

LINKS_PATH = (
    "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
    "Girardinichthys/multiradiatus/links"
)


def _fixture() -> str:
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


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Endpoint shape
# ---------------------------------------------------------------------------


def test_links_endpoint_returns_200_with_links_envelope(app: FastAPI) -> None:
    with _client(app) as client:
        response = client.get(LINKS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"links", "species"}


def test_links_envelope_emits_exactly_twelve_links(app: FastAPI) -> None:
    with _client(app) as client:
        body = client.get(LINKS_PATH).json()

    assert len(body["links"]) == 12
    # The species envelope identifies the resolved species.
    assert body["species"]["canonical_name"] == "Girardinichthys multiradiatus"


def test_links_each_item_has_source_label_url(app: FastAPI) -> None:
    with _client(app) as client:
        body = client.get(LINKS_PATH).json()

    for item in body["links"]:
        assert set(item.keys()) == {"source", "label", "url"}
        assert isinstance(item["source"], str)
        assert isinstance(item["label"], str)
        assert isinstance(item["url"], str)
        assert item["url"] != ""


def test_links_order_matches_templates_file(app: FastAPI) -> None:
    """The 12 links MUST be in the row order from docs/sources/templates.md."""
    with _client(app) as client:
        body = client.get(LINKS_PATH).json()

    # Read the expected order from the templates file.
    templates_path = Path("docs/sources/templates.md")
    import re

    table_row = re.compile(r"^\|\s*(?P<source>[^|]+?)\s*\|\s*`(?P<url>[^`]+)`")
    expected: list[str] = []
    with templates_path.open(encoding="utf-8") as file:
        for line in file:
            match = table_row.match(line)
            if match is None:
                continue
            expected.append(match.group("source").strip())

    actual = [item["source"] for item in body["links"]]
    assert actual == expected


# ---------------------------------------------------------------------------
# URL substitution
# ---------------------------------------------------------------------------


def test_links_substitute_species_with_plus_for_space(app: FastAPI) -> None:
    with _client(app) as client:
        body = client.get(LINKS_PATH).json()

    # Every link's URL must contain the URL-encoded species.
    for item in body["links"]:
        assert "Girardinichthys+multiradiatus" in item["url"]


def test_links_scihub_url_substitutes_species(app: FastAPI) -> None:
    with _client(app) as client:
        body = client.get(LINKS_PATH).json()

    scihub = next(item for item in body["links"] if item["source"] == "Sci-hub")
    assert scihub["url"] == ("https://sci-hub.ru/match/Girardinichthys+multiradiatus")


def test_links_substitute_percent_encodes_special_chars(tmp_path: Path) -> None:
    """Special characters in the species query are percent-encoded."""
    fixture = (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Genus [genus] {ID=urn:6}\n"
        # Species with parentheses — \`(\` → \`%28\`, \`)\` → \`%29\`.
        "              Genus (foo) [species] {ID=urn:7}\n"
    )
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    app = create_app(database_url=f"sqlite:///{db}")

    path = (
        "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/Genus/%28foo%29/links"
    )
    with TestClient(app) as client:
        body = client.get(path).json()

    for item in body["links"]:
        # Parentheses were already percent-encoded in the URL.
        # The species becomes "Genus+%28foo%29" after substitution.
        assert "Genus+%28foo%29" in item["url"]


def test_links_photos_url_keeps_tracking_parameters(app: FastAPI) -> None:
    r"""The Photos template carries fixed tracking parameters from cell M9;
    only the \`{q}\` segment is substituted.
    """
    with _client(app) as client:
        body = client.get(LINKS_PATH).json()

    photos = next(item for item in body["links"] if item["source"] == "Photos")
    # Tracking params from the captured template must remain verbatim.
    # The exact param list is captured in docs/sources/templates.md —
    # we assert the URL is non-trivial and contains \`{q}\` substitution.
    assert "?" in photos["url"]
    assert "Girardinichthys+multiradiatus" in photos["url"]


# ---------------------------------------------------------------------------
# Stability
# ---------------------------------------------------------------------------


def test_links_response_is_stable_across_requests(app: FastAPI) -> None:
    with _client(app) as client:
        a = client.get(LINKS_PATH).json()
        b = client.get(LINKS_PATH).json()

    assert a == b


def test_links_url_differs_per_species(tmp_path: Path) -> None:
    """Two different species produce different link sets."""
    fixture = (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Actinopterygii [class] {ID=urn:3}\n"
        "        Cyprinodontiformes [order] {ID=urn:4}\n"
        "          Goodeidae [family] {ID=urn:5}\n"
        "            Girardinichthys [genus] {ID=urn:6}\n"
        "              Girardinichthys multiradiatus [species] {ID=urn:7}\n"
        "              Girardinichthys viviparus [species] {ID=urn:8}\n"
    )
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    app = create_app(database_url=f"sqlite:///{db}")

    base = "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/Girardinichthys"
    with TestClient(app) as client:
        a = client.get(f"{base}/multiradiatus/links").json()
        b = client.get(f"{base}/viviparus/links").json()

    a_urls = [item["url"] for item in a["links"]]
    b_urls = [item["url"] for item in b["links"]]
    assert a_urls != b_urls


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_links_404_when_species_unknown(app: FastAPI) -> None:
    with _client(app) as client:
        response = client.get(
            "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
            "Girardinichthys/nonexistentus/links"
        )

    assert response.status_code == 404
