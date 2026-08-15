"""RED-first contract tests for the per-taxon dispatch-URL endpoint.

The breadcrumb-dinamico change adds a new endpoint that emits the
same 13-link substitution the species row produces, but for any
taxon resolved via a 1-7-segment cascade path (no epithet):

    GET /api/{path}/taxon-links

Where ``{path}`` is the pipe-joined segments captured by FastAPI's
``{path:path}`` route parameter (e.g. ``Animalia%7CChordata`` for
``["Animalia", "Chordata"]``).

The endpoint reuses :func:`taxon.search_links.build_search_links` so
the substitution target is the deepest resolved taxon's canonical
``name`` (never ``display_name``). The 13-link invariant is enforced
upstream by :func:`taxon.search_links.load_templates` which raises
on a count != 13.

The endpoint is registered after ``/kingdoms`` and ``/path-children``
so its ``{path:path}`` catch-all does NOT shadow the existing
species-links endpoint ``/api/{k}/.../{epithet}/links`` -- 1.6 pins
that contract.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote_plus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Two-segment path that resolves to the phylum ``Chordata`` under
# ``Animalia``. The pipe is URL-encoded as ``%7C``.
TAXON_LINKS_PATH = "/api/Animalia%7CChordata/taxon-links"

# Path used by the regression test for the existing species-links
# endpoint. Must still return exactly 13 items after the new route
# is registered -- otherwise the new route shadowed it.
SPECIES_LINKS_PATH = (
    "/api/Animalia/Chordata/Actinopterygii/Cyprinodontiformes/Goodeidae/"
    "Girardinichthys/multiradiatus/links"
)

# The templates file lives at the repo root and drives both endpoints.
TEMPLATES_PATH = Path("docs/sources/templates.md")


def _two_segment_fixture() -> str:
    """Minimal lineage that resolves ``Animalia/Chordata`` to phylum rank.

    Layout (depth increases by 2 spaces per level):

    - Biota (superdomain)
      - Animalia (kingdom)
        - Chordata (phylum)
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
    )


def _seven_segment_fixture() -> str:
    """Lineage that resolves a 7-segment path to genus ``Panthera``.

    Layout:

    - Biota -> Animalia (kingdom)
    - Chordata (phylum) -> Mammalia (class)
    - Carnivora (order) -> Felidae (family)
    - Panthera (genus)
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Mammalia [class] {ID=urn:3}\n"
        "        Carnivora [order] {ID=urn:4}\n"
        "          Felidae [family] {ID=urn:5}\n"
        "            Panthera [genus] {ID=urn:6}\n"
    )


def _species_links_fixture() -> str:
    """Lineage for the species-links regression test."""
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


def _eight_segment_fixture() -> str:
    """Eight-segment lineage used to exercise the cap test."""
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Mammalia [class] {ID=urn:3}\n"
        "        Carnivora [order] {ID=urn:4}\n"
        "          Felidae [family] {ID=urn:5}\n"
        "            Panthera [genus] {ID=urn:6}\n"
        "              Panthera leo [species] {ID=urn:7}\n"
        "                Panthera leo subspecies [subspecies] {ID=urn:8}\n"
    )


def _build_app(tmp_path: Path, fixture: str) -> FastAPI:
    """Build a FastAPI app backed by an in-memory SQLite imported from ``fixture``."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_two_segment(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _two_segment_fixture())


@pytest.fixture
def app_seven_segment(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _seven_segment_fixture())


@pytest.fixture
def app_eight_segment(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _eight_segment_fixture())


@pytest.fixture
def app_species_links(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _species_links_fixture())


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1.1 Endpoint shape
# ---------------------------------------------------------------------------


def test_taxon_links_endpoint_returns_200_with_taxon_and_links(app_two_segment: FastAPI) -> None:
    """The endpoint emits 200 + a ``TaxonLinksResponse`` envelope with two keys."""
    with _client(app_two_segment) as client:
        response = client.get(TAXON_LINKS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"taxon", "links"}


def test_taxon_links_taxon_is_the_phylum_chordata(app_two_segment: FastAPI) -> None:
    """The ``taxon`` payload identifies the deepest resolved row, not the path."""
    with _client(app_two_segment) as client:
        body = client.get(TAXON_LINKS_PATH).json()

    assert body["taxon"]["name"] == "Chordata"
    assert body["taxon"]["rank"] == "phylum"


def test_taxon_links_emits_exactly_thirteen_links(app_two_segment: FastAPI) -> None:
    """Every response MUST carry exactly 13 link items in templates order."""
    with _client(app_two_segment) as client:
        body = client.get(TAXON_LINKS_PATH).json()

    assert len(body["links"]) == 13


def test_taxon_links_each_item_has_source_label_url(app_two_segment: FastAPI) -> None:
    """Each item carries ``source``, ``label``, ``url`` mirroring ``SearchLinkItem``."""
    with _client(app_two_segment) as client:
        body = client.get(TAXON_LINKS_PATH).json()

    for item in body["links"]:
        assert set(item.keys()) == {"source", "label", "url"}
        assert isinstance(item["source"], str)
        assert isinstance(item["label"], str)
        assert isinstance(item["url"], str)
        assert item["url"] != ""


# ---------------------------------------------------------------------------
# 1.2 Substitution vs templates.md
# ---------------------------------------------------------------------------


def _templates_table_sources() -> list[str]:
    """Parse the source column from ``docs/sources/templates.md``."""
    table_row = re.compile(r"^\|\s*(?P<source>[^|]+?)\s*\|\s*`(?P<url>[^`]+)`")
    expected: list[str] = []
    with TEMPLATES_PATH.open(encoding="utf-8") as file:
        for line in file:
            match = table_row.match(line)
            if match is None:
                continue
            expected.append(match.group("source").strip())
    return expected


def test_taxon_links_order_matches_templates_file(app_two_segment: FastAPI) -> None:
    """The 13 links MUST be in the row order from docs/sources/templates.md."""
    with _client(app_two_segment) as client:
        body = client.get(TAXON_LINKS_PATH).json()

    actual = [item["source"] for item in body["links"]]
    expected = _templates_table_sources()
    assert actual == expected


def test_taxon_links_urls_match_templates_byte_for_byte(app_two_segment: FastAPI) -> None:
    """Every URL equals the template row's URL with ``{q}`` replaced by the encoded taxon name."""
    expected = quote_plus("Chordata", safe="")
    table_row = re.compile(r"^\|\s*(?P<source>[^|]+?)\s*\|\s*`(?P<url>[^`]+)`")

    templates_by_source: dict[str, str] = {}
    with TEMPLATES_PATH.open(encoding="utf-8") as file:
        for line in file:
            match = table_row.match(line)
            if match is None:
                continue
            templates_by_source[match.group("source").strip()] = match.group("url")

    with _client(app_two_segment) as client:
        body = client.get(TAXON_LINKS_PATH).json()

    for item in body["links"]:
        template = templates_by_source[item["source"]]
        assert item["url"] == template.replace("{q}", expected)


# ---------------------------------------------------------------------------
# 1.3 Canonical name, not display_name
# ---------------------------------------------------------------------------


def _citation_fixture() -> str:
    """Lineage where ``Chordata`` carries a citation in its display_name.

    The parser strips the trailing author-year citation from ``name``
    (so ``name == "Chordata"``) but preserves it in ``display_name``
    (``"Chordata Bateson, 1885 [phylum]"``). The endpoint MUST emit
    the canonical ``name`` only -- the citation MUST NOT leak into any
    substituted URL.
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata Bateson, 1885 [phylum] {ID=urn:2}\n"
    )


def test_taxon_links_use_canonical_name_not_display_name(tmp_path: Path) -> None:
    """Author citation in display_name MUST NOT appear in any emitted URL."""
    app = _build_app(tmp_path, _citation_fixture())
    with _client(app) as client:
        body = client.get(TAXON_LINKS_PATH).json()

    for item in body["links"]:
        assert "Bateson" not in item["url"], item
        assert "1885" not in item["url"], item
    # The taxon still reports its citation-bearing display_name.
    assert "Chordata Bateson, 1885" in body["taxon"]["display_name"]
    assert body["taxon"]["name"] == "Chordata"


# ---------------------------------------------------------------------------
# 1.4 404 on unknown kingdom / bad segment
# ---------------------------------------------------------------------------


def test_taxon_links_404_when_kingdom_unknown(app_two_segment: FastAPI) -> None:
    """An unknown kingdom returns 404 and the body names the bad segment."""
    with _client(app_two_segment) as client:
        response = client.get("/api/Atlantis/taxon-links")

    assert response.status_code == 404
    assert "Atlantis" in response.json()["detail"]


def test_taxon_links_404_when_phylum_unknown(app_two_segment: FastAPI) -> None:
    """A valid kingdom + bad phylum returns 404 and the body names the bad segment."""
    with _client(app_two_segment) as client:
        response = client.get("/api/Animalia%7CBadPhylum/taxon-links")

    assert response.status_code == 404
    assert "BadPhylum" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 1.5 Cap on path length
# ---------------------------------------------------------------------------


def test_taxon_links_404_when_path_exceeds_seven_segments(app_eight_segment: FastAPI) -> None:
    """A path of eight segments returns 404 whose body explains the seven-segment cap."""
    eight_segment_path = (
        "/api/Biota%7CAnimalia%7CChordata%7CMammalia%7CCarnivora%7CFelidae"
        "%7CPanthera%7CPanthera%20leo/taxon-links"
    )
    with _client(app_eight_segment) as client:
        response = client.get(eight_segment_path)

    assert response.status_code == 404
    detail = response.json()["detail"]
    # The body MUST explain the seven-segment cap (not just a generic 404).
    assert "7" in detail


# ---------------------------------------------------------------------------
# 1.6 Regression: species-links endpoint unchanged
# ---------------------------------------------------------------------------


def test_species_links_endpoint_unaffected_by_taxon_links_route(app_species_links: FastAPI) -> None:
    """Registering ``/{path:path}/taxon-links`` must NOT shadow ``/{k}/.../{epithet}/links``."""
    with _client(app_species_links) as client:
        response = client.get(SPECIES_LINKS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert len(body["links"]) == 13
