"""RED-first contract tests for the ChecklistBank path resolver.

The resolver walks a path of canonical names against the CLB
``COL2024`` dataset and returns the direct children of the deepest
taxon. The CLB search endpoint has no ``higherTaxonKey`` filter, so
the resolver binds each segment to a CLB taxon id via
``/nameusage/search?q=&rank=`` and selects the first hit whose
canonical name matches the segment case-insensitively.

The cascade tier tuple is the locked nine-tier set
``(biota, kingdom, phylum, subphylum, class, order, family, genus,
species)``. PR #2a covers the core walk only — the subphylum
collapse rule (phylum with no subphylum children → return class
children directly) lands in PR #2b. In this slice, the resolver
returns subphylum children verbatim when the parent phylum has any
and emits ``next_rank_hint = "class"``.

The shape returned to the (future) API route is
:class:`PathChildrenResponse` with ``parent``, ``children``, and
``next_rank_hint``. ``parent`` and ``children`` carry
:class:`ChecklistBankTaxon` instances; PR #3's router swap is the
one that translates those into :class:`TaxonResponse` for the wire.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from taxon.api import clb_path_children
from taxon.checklistbank import ChecklistBankClient, ChecklistBankTaxon

# ---------------------------------------------------------------------------
# Test transport — a stub CLB that returns canned responses.
# ---------------------------------------------------------------------------


def _transport(responses: dict[tuple[str, str], httpx.Response]) -> httpx.MockTransport:
    """Build a transport that dispatches on (method, full URL).

    The match key includes the query string so search-by-name
    requests scoped to different parents or ranks resolve to
    different stubs. The CLB walk issues ``/nameusage/search``
    requests with ``rank=`` and ``q=`` query parameters and
    ``/tree/{id}/children`` requests with optional ``rank=``.
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


def _search_path(name: str, rank: str) -> str:
    """URL-encode a CLB search-by-name to a stable path.

    The resolver builds the params dict in this order so the test
    stub mirrors it exactly:

    1. ``q`` (the search term)
    2. ``limit`` and ``offset`` (paging — defaults)
    3. ``rank`` (cascade tier anchor)

    The order matters because ``urlencode`` preserves the dict's
    insertion order, and the test's transport dispatch matches on
    the full URL string.
    """
    params: dict[str, str | int] = {
        "q": name,
        "limit": 20,
        "offset": 0,
        "rank": rank,
    }
    return f"/dataset/COL2024/nameusage/search?{urlencode(params)}"


def _children_path(taxon_id: str, rank: str | None = None) -> str:
    """URL for the children endpoint with the cascade's standard paging.

    The resolver restricts the children query to the rank that
    matches the next cascade tier, so the test stub accepts an
    optional ``rank`` argument that is rendered into the URL when
    present.
    """
    params: dict[str, str | int] = {"limit": 300, "offset": 0}
    if rank is not None:
        params["rank"] = rank
    return f"/dataset/COL2024/tree/{taxon_id}/children?{urlencode(params)}"


def _row(
    taxon_id: str,
    name: str,
    rank: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Build a CLB ``/tree/{id}/children``-style row.

    CLB returns the flat shape here (``id``, ``name``, ``rank``,
    ``parentId``, ``datasetKey``, ``labelHtml``, ``childCount``,
    ``status``). The parser converts these to
    :class:`ChecklistBankTaxon` via ``usage`` wrapping in the live
    API; the resolver's parser handles both shapes.
    """
    return {
        "datasetKey": 299029,
        "id": taxon_id,
        "rank": rank,
        "status": "accepted",
        "name": name,
        "labelHtml": f"<i>{name}</i>",
        "parentId": parent_id,
        "count": 0,
        "childCount": 0,
    }


def _children_200(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"offset": 0, "limit": 300, "total": len(rows), "result": rows})


def _search_200(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"offset": 0, "limit": 20, "total": len(rows), "result": rows})


# ---------------------------------------------------------------------------
# Anatomy: the cascade tiers
# ---------------------------------------------------------------------------


def test_cascade_tiers_are_nine_with_subphylum() -> None:
    """CLB exposes exactly 9 cascade tiers, in this order. The
    cascade UI renders one dropdown per tier; the order matters
    because the UI walks the path depth-first.

    The nine tiers include the ``biota`` root (above kingdom)
    and ``subphylum`` between ``phylum`` and ``class``. Locked
    decision in the proposal.
    """
    assert clb_path_children.CASCADE_TIERS == (
        "biota",
        "kingdom",
        "phylum",
        "subphylum",
        "class",
        "order",
        "family",
        "genus",
        "species",
    )


# ---------------------------------------------------------------------------
# Resolution: path → deepest taxon
# ---------------------------------------------------------------------------


def test_root_path_returns_biota_children() -> None:
    """``list_path_children(["Biota"])`` resolves Biota and returns
    its seven kingdoms in the children list with
    ``next_rank_hint = "kingdom"``.

    The walk issues exactly one search (Biota at rank=biota) and
    one get_children call (Biota's children at rank=kingdom).
    """
    biota_row = _row("5T6MX", "Biota", "biota")
    kingdoms = [
        _row("N", "Animalia", "kingdom", parent_id="5T6MX"),
        _row("B", "Bacteria", "kingdom", parent_id="5T6MX"),
        _row("AR", "Archaea", "kingdom", parent_id="5T6MX"),
        _row("F", "Fungi", "kingdom", parent_id="5T6MX"),
        _row("P", "Plantae", "kingdom", parent_id="5T6MX"),
        _row("PR", "Protozoa", "kingdom", parent_id="5T6MX"),
        _row("C", "Chromista", "kingdom", parent_id="5T6MX"),
    ]
    transport = _transport(
        {
            ("GET", _search_path("Biota", rank="biota")): _search_200([biota_row]),
            ("GET", _children_path("5T6MX", rank="kingdom")): _children_200(kingdoms),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Biota"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "5T6MX"
    assert response.parent.canonical_name == "Biota"
    assert response.parent.rank == "biota"
    assert {child.canonical_name for child in response.children} == {
        "Animalia",
        "Bacteria",
        "Archaea",
        "Fungi",
        "Plantae",
        "Protozoa",
        "Chromista",
    }
    assert response.next_rank_hint == "kingdom"


def test_resolves_animalia_to_clb_taxon_n() -> None:
    """A single-segment ``["Animalia"]`` path resolves to the
    CLB Animalia taxon (``taxon_id == "N"``) — the standard
    opaque CLB id.

    The walk issues one search (Animalia at rank=kingdom). The
    resolver picks the first hit whose canonical name matches
    case-insensitively.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _children_path("N", rank="phylum")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "N"
    assert response.parent.canonical_name == "Animalia"


def test_resolves_chordata_to_clb_taxon_ch2() -> None:
    """A two-segment ``["Animalia", "Chordata"]`` path resolves to
    the CLB Chordata taxon (``taxon_id == "CH2"``).

    The walk issues two searches (Animalia at rank=kingdom;
    Chordata at rank=phylum) and picks the first hit each time
    whose canonical name matches the segment.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            ("GET", _children_path("CH2", rank="subphylum")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Chordata"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "CH2"
    assert response.parent.canonical_name == "Chordata"


def test_resolves_mammalia_via_subphylum_tier() -> None:
    """The full Mammalia chain via the subphylum tier works:
    Animalia → Chordata (phylum) → Vertebrata (subphylum) →
    Mammalia (class).

    Each segment is searched by name + rank; the resolver picks
    the first hit whose canonical name matches. The path's
    depth is 4, so the resolver walks 4 search calls before
    issuing the children fetch.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            ("GET", _search_path("Vertebrata", rank="subphylum")): _search_200(
                [_row("V", "Vertebrata", "subphylum", parent_id="CH2")]
            ),
            ("GET", _search_path("Mammalia", rank="class")): _search_200(
                [_row("MA", "Mammalia", "class", parent_id="V")]
            ),
            ("GET", _children_path("MA", rank="order")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(
        ["Animalia", "Chordata", "Vertebrata", "Mammalia"], client=client
    )
    assert response is not None
    assert response.parent.taxon_id == "MA"
    assert response.parent.canonical_name == "Mammalia"
    assert response.parent.rank == "class"
    assert response.next_rank_hint == "order"


def test_returns_12_panthera_species_via_subphylum() -> None:
    """Full Panthera chain via the subphylum tier:
    ``Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera``
    returns the 12 Panthera species at the leaf.

    The path is 7 segments long (kingdom → … → genus), so the
    resolver walks 7 search calls and 1 children fetch. The
    next-rank hint for a genus is ``"species"``.
    """
    chain = [
        ("N", "Animalia", "kingdom", None),
        ("CH2", "Chordata", "phylum", "N"),
        ("V", "Vertebrata", "subphylum", "CH2"),
        ("MA", "Mammalia", "class", "V"),
        ("CA", "Carnivora", "order", "MA"),
        ("FE", "Felidae", "family", "CA"),
        ("PA", "Panthera", "genus", "FE"),
    ]
    responses: dict[tuple[str, str], httpx.Response] = {}
    for taxon_id, name, rank, parent in chain:
        responses[("GET", _search_path(name, rank=rank))] = _search_200(
            [_row(taxon_id, name, rank, parent_id=parent)]
        )
    panthera_species = [
        _row(f"SP{i}", f"Panthera {epithet}", "species", parent_id="PA")
        for i, epithet in enumerate(
            [
                "leo",
                "onca",
                "pardus",
                "tigris",
                "uncia",
            ]
        )
    ]
    # 12 species per the success criteria (5 accepted + 7 historical synonyms).
    panthera_species += [
        _row(f"SY{i}", f"Panthera {synonym}", "species", parent_id="PA")
        for i, synonym in enumerate(
            [
                "spelaea",
                "atrox",
                "fossilis",
                "palustris",
                "balica",
                "sondaica",
                "virgata",
            ]
        )
    ]
    responses[("GET", _children_path("PA", rank="species"))] = _children_200(panthera_species)

    client = ChecklistBankClient(client=httpx.Client(transport=_transport(responses)))
    response = clb_path_children.list_path_children(
        [
            "Animalia",
            "Chordata",
            "Vertebrata",
            "Mammalia",
            "Carnivora",
            "Felidae",
            "Panthera",
        ],
        client=client,
    )
    assert response is not None
    assert response.parent.taxon_id == "PA"
    assert response.parent.canonical_name == "Panthera"
    assert len(response.children) == 12
    assert response.next_rank_hint == "species"
    # Verify the species are Panthera-named (the contract is 12
    # Panthera species at the leaf).
    assert all(child.canonical_name.startswith("Panthera ") for child in response.children)


def test_walk_stops_when_segment_does_not_resolve() -> None:
    """A bad segment mid-path returns ``None``. The resolver does
    NOT return the deepest match — the contract for CLB is that
    a partial path produces ``None`` so the router emits 404.

    Uses Absentia as the failing phylum: a search for "Absentia"
    at rank=phylum returns no hits, so the resolver cannot
    continue past the second segment.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Absentia", rank="phylum")): _search_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Absentia"], client=client)
    assert response is None


def test_path_match_is_case_insensitive() -> None:
    """CLB canonical names are case-sensitive at the API level
    but the cascade UI may submit a path with mixed case
    (``animalia`` vs ``Animalia``). The resolver matches the
    segment to the hit's canonical name case-insensitively so
    hand-edited URLs still resolve.
    """
    transport = _transport(
        {
            ("GET", _search_path("animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _children_path("N", rank="phylum")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["animalia"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "N"
    assert response.parent.canonical_name == "Animalia"


def test_empty_path_returns_none() -> None:
    """An empty path is the API's way of asking for the root
    kingdom list — the resolver does not handle that here. The
    router's separate ``/api/kingdoms`` endpoint covers the root.
    """
    client = ChecklistBankClient(client=httpx.Client(transport=_transport({})))
    assert clb_path_children.list_path_children([], client=client) is None


# ---------------------------------------------------------------------------
# Helpers: the resolver's data carriers
# ---------------------------------------------------------------------------


def test_to_taxon_row_carries_clb_id_strings() -> None:
    """The resolver's :class:`PathChildrenResponse` carries
    :class:`ChecklistBankTaxon` instances whose ``taxon_id`` is
    the opaque CLB string (e.g. ``"N"``, ``"CH2"``).

    This pins the public type so PR #3's router swap can rely
    on ``PathChildrenResponse.parent.taxon_id`` being a string
    rather than an integer.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _children_path("N", rank="phylum")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia"], client=client)
    assert response is not None
    # The parent and children are ChecklistBankTaxon dataclasses,
    # not dicts or any other shape.
    assert isinstance(response.parent, ChecklistBankTaxon)
    assert isinstance(response.children, list)
    for child in response.children:
        assert isinstance(child, ChecklistBankTaxon)
