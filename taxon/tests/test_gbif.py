"""RED-first contract tests for the GBIF client.

The cascade resolver composes three GBIF calls per dropdown:
1. ``get_taxon(parent_key)`` to resolve the deepest segment.
2. ``get_children(parent_key)`` to fetch the children for the
   next dropdown.

These tests pin the wire shape via httpx ``MockTransport`` so the
client can run without hitting the real GBIF API.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from taxon.gbif import (
    DEFAULT_CHILD_LIMIT,
    GBIF_BASE_URL,
    GbifClient,
    _parse_taxon,
)

# ---------------------------------------------------------------------------
# _parse_taxon
# ---------------------------------------------------------------------------


def test_parse_taxon_keeps_only_cascade_relevant_fields() -> None:
    """The cascade uses 13 fields; the rest of the GBIF response
    (issues, habitats, threatStatuses, synonym, ...) is dropped."""
    raw = {
        "key": 1,
        "nubKey": 1,
        "canonicalName": "Animalia",
        "scientificName": "Animalia",
        "rank": "KINGDOM",
        "kingdom": "Animalia",
        "phylum": None,
        "order": None,
        "family": None,
        "genus": None,
        "species": None,
        "parentKey": None,
        "parent": None,
        "numDescendants": 2981931,
        # All of these should be ignored:
        "issues": [],
        "habitats": [],
        "threatStatuses": [],
        "synonym": False,
        "taxonomicStatus": "ACCEPTED",
    }
    taxon = _parse_taxon(raw)
    assert taxon.key == 1
    assert taxon.canonical_name == "Animalia"
    assert taxon.rank == "KINGDOM"
    assert taxon.num_children == 2981931


def test_parse_taxon_for_species_row_includes_full_breadcrumb() -> None:
    """A species row carries the kingdom/phylum/order/family/genus
    pre-resolved in the GBIF response. The cascade uses these to
    label dropdowns without re-walking the chain."""
    raw = {
        "key": 107312362,
        "nubKey": 107312362,
        "canonicalName": "Gadus morhua",
        "scientificName": "Gadus morhua",
        "rank": "SPECIES",
        "kingdom": "Metazoa",
        "phylum": "Chordata",
        "order": "Gadiformes",
        "family": "Gadidae",
        "genus": "Gadus",
        "species": "Gadus morhua",
        "parentKey": 2335052,
        "parent": "Gadus",
        "numDescendants": 0,
    }
    taxon = _parse_taxon(raw)
    assert taxon.canonical_name == "Gadus morhua"
    assert taxon.kingdom == "Metazoa"
    assert taxon.phylum == "Chordata"
    assert taxon.order == "Gadiformes"
    assert taxon.family == "Gadidae"
    assert taxon.genus == "Gadus"
    assert taxon.species == "Gadus morhua"
    assert taxon.parent_key == 2335052


# ---------------------------------------------------------------------------
# Test transport — a stub GBIF that returns canned responses.
# ---------------------------------------------------------------------------


def _stub_transport(responses: dict[tuple[str, str], httpx.Response]) -> httpx.MockTransport:
    """Build a :class:`MockTransport` that dispatches on (method, path).

    The cascade resolver issues GET requests to ``/species/{key}``
    and ``/species/{key}/children?limit=...&offset=...``. The
    transport returns the pre-registered response for the
    matching (method, path) tuple, or 404 for everything else.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key in responses:
            return responses[key]
        # Strip query when looking up the children endpoint.
        return httpx.Response(404, json={"error": "not stubbed"})

    return httpx.MockTransport(handler)


def _animalia_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "key": 1,
            "nubKey": 1,
            "canonicalName": "Animalia",
            "scientificName": "Animalia",
            "rank": "KINGDOM",
            "kingdom": "Animalia",
            "numDescendants": 2981931,
        },
    )


def _children_response(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"offset": 0, "limit": 300, "results": rows})


# ---------------------------------------------------------------------------
# GbifClient.get_taxon
# ---------------------------------------------------------------------------


def test_get_taxon_returns_parsed_taxon() -> None:
    """The client surfaces a GBIF row as a :class:`GbifTaxon`."""
    transport = _stub_transport({("GET", "/v1/species/1"): _animalia_response()})
    client = GbifClient(client=httpx.Client(transport=transport))
    taxon = client.get_taxon(1)
    assert taxon is not None
    assert taxon.key == 1
    assert taxon.canonical_name == "Animalia"
    assert taxon.rank == "KINGDOM"
    assert taxon.num_children == 2981931


def test_get_taxon_returns_none_on_404() -> None:
    """A 404 from GBIF means the key does not exist. The resolver
    branches without exception handling, so 404 → None."""
    transport = _stub_transport({})  # every path returns 404
    client = GbifClient(client=httpx.Client(transport=transport))
    taxon = client.get_taxon(9999999)
    assert taxon is None


def test_get_taxon_raises_on_5xx() -> None:
    """A 5xx from GBIF is a real failure (not a missing key). The
    resolver propagates the error so the FastAPI handler renders
    a 502 with the upstream status."""
    transport = _stub_transport(
        {("GET", "/v1/species/1"): httpx.Response(503, json={"error": "down"})}
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    with pytest.raises(httpx.HTTPStatusError):
        client.get_taxon(1)


# ---------------------------------------------------------------------------
# GbifClient.get_children
# ---------------------------------------------------------------------------


def test_get_children_returns_parsed_list() -> None:
    """Children endpoint returns a paginated envelope. The client
    surfaces only the rows."""
    rows = [
        {
            "key": 67,
            "nubKey": 67,
            "canonicalName": "Acanthocephala",
            "scientificName": "Acanthocephala",
            "rank": "PHYLUM",
            "kingdom": "Animalia",
            "numDescendants": 1917,
        },
        {
            "key": 42,
            "nubKey": 42,
            "canonicalName": "Annelida",
            "scientificName": "Annelida",
            "rank": "PHYLUM",
            "kingdom": "Animalia",
            "numDescendants": 41152,
        },
    ]
    transport = _stub_transport({("GET", "/v1/species/1/children"): _children_response(rows)})
    client = GbifClient(client=httpx.Client(transport=transport))
    children = client.get_children(1)
    assert len(children) == 2
    assert children[0].canonical_name == "Acanthocephala"
    assert children[1].canonical_name == "Annelida"


def test_get_children_returns_empty_list_when_no_results() -> None:
    """A leaf taxon returns an empty children list. The cascade
    renders it as "no children" rather than 404."""
    transport = _stub_transport({("GET", "/v1/species/12345/children"): _children_response([])})
    client = GbifClient(client=httpx.Client(transport=transport))
    children = client.get_children(12345)
    assert children == []


def test_get_children_passes_limit_and_offset() -> None:
    """The cascade renders the first page in a dropdown. The
    caller can pass offset to fetch the next page (e.g. for a
    genus with thousands of species)."""
    transport = _stub_transport({("GET", "/v1/species/1/children"): _children_response([])})
    client = GbifClient(client=httpx.Client(transport=transport))
    client.get_children(1, limit=50, offset=200)
    # The transport doesn't expose the request URL directly,
    # so we re-stub with a recorder to verify the query string.
    captured: dict[str, str] = {}

    def rec_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _children_response([])

    recording = httpx.MockTransport(rec_handler)
    client = GbifClient(client=httpx.Client(transport=recording))
    client.get_children(1, limit=50, offset=200)
    assert "limit=50" in captured["url"]
    assert "offset=200" in captured["url"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_child_limit_is_a_cascade_comfortable_cap() -> None:
    """The cascade dropdown renders the first page. 300 rows
    fits comfortably in a single page and keeps the JSON payload
    under 100 KB for typical taxa."""
    assert DEFAULT_CHILD_LIMIT == 300


def test_gbif_base_url_is_public() -> None:
    """The base URL points at the public GBIF API. No auth, no
    proxy, no rate-limit adjustments needed for read-only access."""
    assert GBIF_BASE_URL == "https://api.gbif.org/v1"
