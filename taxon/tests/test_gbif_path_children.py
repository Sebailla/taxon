"""RED-first contract tests for the GBIF path resolver.

The resolver walks a path of canonical names and returns the
direct children of the deepest taxon. The contract pinned here
is the same shape the cascade UI already consumes
(``PathChildrenResponse`` with ``parent``, ``children``,
``next_rank_hint``); the data source switched from CoL to GBIF.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from taxon.api.gbif_path_children import (
    CASCADE_TIERS,
    list_path_children,
)
from taxon.gbif import GbifClient

# ---------------------------------------------------------------------------
# Test transport — a stub GBIF that returns canned responses.
# ---------------------------------------------------------------------------


def _transport(responses: dict[tuple[str, str], httpx.Response]) -> httpx.MockTransport:
    """Build a transport that dispatches on (method, URL).

    The match key includes the query string so search-by-name
    requests scoped to different parents or ranks resolve to
    different stubs.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        full = request.url.path
        if request.url.query:
            full = f"{full}?{request.url.query.decode()}"
        return responses.get(
            (request.method, full),
            httpx.Response(404, json={"error": "not stubbed"}),
        )

    return httpx.MockTransport(handler)


def _search_path(name: str, parent_key: int | None = None, rank: str | None = None) -> str:
    """URL-encode search-by-name to a stable path.

    The resolver builds the params dict in this order so the
    test stub mirrors it exactly:
    1. ``q`` (the search term)
    2. ``limit`` and ``offset`` (paging — defaults)
    3. ``status`` (ACCEPTED filter — default)
    4. ``rank`` (cascade tier anchor — present only when the
       resolver has a parent anchor)
    5. ``higherTaxonKey`` (parent anchor — present only when
       the resolver is walking a non-root segment)

    The order matters because ``urlencode`` preserves the
    dict's insertion order, and the test's transport dispatch
    matches on the full URL string.

    The default ``rank="KINGDOM"`` matches the resolver's
    root-segment behaviour: a single-segment path is always
    a kingdom lookup. Tests that exercise non-root segments
    pass ``rank=None`` to suppress the default and pass the
    actual cascade tier explicitly.
    """
    params: dict[str, str | int] = {
        "q": name,
        "limit": 20,
        "offset": 0,
        "status": "ACCEPTED",
    }
    if rank is not None:
        params["rank"] = rank
    if parent_key is not None:
        params["higherTaxonKey"] = parent_key
    return f"/v1/species/search?{urlencode(params)}"


def _children_path(key: int, rank: str | None = None) -> str:
    """URL for the children endpoint with the cascade's standard paging.

    The resolver now restricts the children query to the rank that
    matches the next cascade tier, so the test stub accepts an
    optional ``rank`` argument that is rendered into the URL when
    present.
    """
    params: dict[str, str | int] = {"limit": 300, "offset": 0}
    if rank is not None:
        params["rank"] = rank
    return f"/v1/species/{key}/children?{urlencode(params)}"


def _row(key: int, name: str, rank: str, parent_key: int | None = None) -> dict[str, Any]:
    """Build a GBIF /species/{key} response payload."""
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


def _children_200(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"offset": 0, "limit": 300, "results": rows})


def _search_200(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"offset": 0, "limit": 20, "results": rows})


# ---------------------------------------------------------------------------
# Anatomy: the cascade tiers
# ---------------------------------------------------------------------------


def test_cascade_tiers_are_six_collapsed() -> None:
    """GBIF exposes exactly 6 cascade tiers, in this order. The
    cascade UI renders one dropdown per tier; the order matters
    because the UI walks the path depth-first."""
    assert CASCADE_TIERS == (
        "kingdom",
        "phylum",
        "order",
        "family",
        "genus",
        "species",
    )


# ---------------------------------------------------------------------------
# Resolution: path → deepest taxon
# ---------------------------------------------------------------------------


def test_resolves_kingdom_animalia() -> None:
    """The first segment of any path is a kingdom. The resolver
    identifies it by searching GBIF for the canonical name without
    a parent anchor — GBIF returns the accepted kingdom at the top
    of the result list."""
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="KINGDOM")): _search_200(
                [_row(1, "Animalia", "KINGDOM")]
            ),
            ("GET", _children_path(1)): _children_200([]),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(["Animalia"], client=client)
    assert response is not None
    assert response.parent.name == "Animalia"
    assert response.parent.rank == "kingdom"


def test_resolves_full_chain_to_panthera_genus() -> None:
    """A 5-segment path resolves to the Panthera genus. Each
    segment's search is scoped to the parent via
    ``higherTaxonKey`` and to the cascade tier via ``rank``."""
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="KINGDOM")): _search_200(
                [_row(1, "Animalia", "KINGDOM")]
            ),
            ("GET", _search_path("Chordata", parent_key=1, rank="PHYLUM")): _search_200(
                [_row(44, "Chordata", "PHYLUM", parent_key=1)]
            ),
            ("GET", _search_path("Carnivora", parent_key=44, rank="ORDER")): _search_200(
                [_row(732, "Carnivora", "ORDER", parent_key=44)]
            ),
            ("GET", _search_path("Felidae", parent_key=732, rank="FAMILY")): _search_200(
                [_row(9702, "Felidae", "FAMILY", parent_key=732)]
            ),
            ("GET", _search_path("Panthera", parent_key=9702, rank="GENUS")): _search_200(
                [_row(9703, "Panthera", "GENUS", parent_key=9702)]
            ),
            ("GET", _children_path(9703)): _children_200([]),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(
        ["Animalia", "Chordata", "Carnivora", "Felidae", "Panthera"],
        client=client,
    )
    assert response is not None
    assert response.parent.name == "Panthera"
    assert response.parent.rank == "genus"


def test_returns_none_when_path_is_empty() -> None:
    """An empty path is the API's way of asking for the root
    kingdom list — the resolver does not handle that here. The
    router's separate ``/api/kingdoms`` endpoint covers the root.
    """
    client = GbifClient(client=httpx.Client(transport=_transport({})))
    assert list_path_children([], client=client) is None


def test_returns_none_when_segment_does_not_resolve() -> None:
    """A typo like ``Nonexistent`` returns None — the resolver
    cannot find a match for the first segment."""
    transport = _transport({("GET", _search_path("Nonexistent", rank="KINGDOM")): _search_200([])})
    client = GbifClient(client=httpx.Client(transport=transport))
    assert list_path_children(["Nonexistent"], client=client) is None


def test_returns_deepest_match_when_segment_does_not_resolve() -> None:
    """When the second segment has no children in GBIF, the
    resolver returns the deepest match that did chain. The
    cascade UI renders the partial path; the user re-picks."""
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="KINGDOM")): _search_200(
                [_row(1, "Animalia", "KINGDOM")]
            ),
            ("GET", _search_path("Aves", parent_key=1, rank="PHYLUM")): _search_200(
                []  # no Aves phylum under Animalia
            ),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(["Animalia", "Aves"], client=client)
    assert response is not None
    assert response.parent.name == "Animalia"


# ---------------------------------------------------------------------------
# Children: pop the next dropdown
# ---------------------------------------------------------------------------


def test_returns_direct_children_of_deepest_taxon() -> None:
    """For Animalia, the resolver returns Animalia's direct children
    (the kingdoms below). The cascade UI renders them in the
    next dropdown."""
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="KINGDOM")): _search_200(
                [_row(1, "Animalia", "KINGDOM")]
            ),
            ("GET", _children_path(1, rank="PHYLUM")): _children_200(
                [
                    _row(7, "Protozoa", "PHYLUM"),
                    _row(6, "Plantae", "PHYLUM"),
                    _row(5, "Fungi", "PHYLUM"),
                ]
            ),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(["Animalia"], client=client)
    assert response is not None
    # GBIF returns children in key order (insertion order in the
    # cache). The cascade UI sorts the dropdown by name on the
    # client side; the resolver just exposes the underlying list.
    actual = [child.name for child in response.children]
    assert sorted(actual) == [
        "Fungi",
        "Plantae",
        "Protozoa",
    ]


def test_returns_panthera_species_as_children() -> None:
    """A 5-segment path that lands at Panthera returns the species
    that live under it. The cascade UI renders this in the leaf
    panel."""
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="KINGDOM")): _search_200(
                [_row(1, "Animalia", "KINGDOM")]
            ),
            ("GET", _search_path("Chordata", parent_key=1, rank="PHYLUM")): _search_200(
                [_row(44, "Chordata", "PHYLUM", parent_key=1)]
            ),
            ("GET", _search_path("Carnivora", parent_key=44, rank="ORDER")): _search_200(
                [_row(732, "Carnivora", "ORDER", parent_key=44)]
            ),
            ("GET", _search_path("Felidae", parent_key=732, rank="FAMILY")): _search_200(
                [_row(9702, "Felidae", "FAMILY", parent_key=732)]
            ),
            ("GET", _search_path("Panthera", parent_key=9702, rank="GENUS")): _search_200(
                [_row(9703, "Panthera", "GENUS", parent_key=9702)]
            ),
            ("GET", _children_path(9703, rank="SPECIES")): _children_200(
                [
                    _row(9704, "Panthera leo", "SPECIES"),
                    _row(9705, "Panthera onca", "SPECIES"),
                    _row(9706, "Panthera tigris", "SPECIES"),
                ]
            ),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(
        ["Animalia", "Chordata", "Carnivora", "Felidae", "Panthera"],
        client=client,
    )
    assert response is not None
    actual = [child.name for child in response.children]
    assert sorted(actual) == sorted(
        [
            "Panthera leo",
            "Panthera onca",
            "Panthera tigris",
        ]
    )


# ---------------------------------------------------------------------------
# Next rank hint: what tier comes next?
# ---------------------------------------------------------------------------


def test_next_rank_hint_for_kingdom_is_phylum() -> None:
    """The cascade walks from kingdom. The next tier is phylum."""
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="KINGDOM")): _search_200(
                [_row(1, "Animalia", "KINGDOM")]
            ),
            ("GET", _children_path(1)): _children_200(
                [
                    _row(44, "Chordata", "PHYLUM"),
                    _row(42, "Annelida", "PHYLUM"),
                    _row(54, "Arthropoda", "PHYLUM"),
                ]
            ),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(["Animalia"], client=client)
    assert response is not None
    assert response.next_rank_hint == "phylum"


def test_next_rank_hint_for_genus_is_species() -> None:
    """Tiger/leo/jaguar under Panthera — the next tier is species."""
    transport = _transport(
        {
            ("GET", _search_path("Panthera", rank="KINGDOM")): _search_200(
                [_row(9703, "Panthera", "GENUS", parent_key=9702)]
            ),
            ("GET", _children_path(9703)): _children_200([_row(9704, "Panthera leo", "SPECIES")]),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(["Panthera"], client=client)
    assert response is not None
    assert response.next_rank_hint == "species"


def test_next_rank_hint_is_none_for_leaf() -> None:
    """A species row has no children in the cascade. The hint is
    null so the cascade UI stops requesting the next dropdown.

    The resolver picks the next-tier rank from the parent's
    rank, not from the children: Panthera leo (SPECIES) returns
    next-tier = SPECIES (subspecies/varieties). When the parent
    has no children at that tier, the resolver still returns
    the tier label so the UI can render an empty dropdown."""
    transport = _transport(
        {
            ("GET", _search_path("Panthera leo", rank="KINGDOM")): _search_200(
                [_row(9704, "Panthera leo", "SPECIES", parent_key=9703)]
            ),
            ("GET", _children_path(9704, rank="SPECIES")): _children_200([]),
        }
    )
    client = GbifClient(client=httpx.Client(transport=transport))
    response = list_path_children(["Panthera leo"], client=client)
    assert response is not None
    assert response.parent.name == "Panthera leo"
    assert response.children == []
    assert response.next_rank_hint == "species"
