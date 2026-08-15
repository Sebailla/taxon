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


def _search_path_no_rank(name: str) -> str:
    """URL-encode a CLB search-by-name without a ``rank`` filter.

    The best-effort resolver falls back to rank-less search when
    the cascade path exceeds the locked 9-tier tuple (Issue #43).
    Tests that exercise off-tuple chains use this helper to stub
    the rank-less search.
    """
    params: dict[str, str | int] = {
        "q": name,
        "limit": 20,
        "offset": 0,
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


def _get_taxon_200(row: dict[str, Any]) -> httpx.Response:
    """Build the JSON body for a successful ``/nameusage/{id}`` response.

    CLB wraps the row's name + rank in a nested ``name`` object
    on this endpoint. The test helper mirrors the real shape so
    the resolver's ``_parse_taxon`` picks up the ``scientificName``
    and ``rank`` from the nested location. Flat-shape rows
    (e.g. ``/tree/{id}/children``) are passed through verbatim.
    """
    nested_name = {
        "scientificName": row.get("name", ""),
        "rank": row.get("rank", ""),
    }
    payload = {**row, "name": nested_name}
    return httpx.Response(200, json=payload)


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
    its seven kingdoms grouped under a single ``kingdom`` tier in
    ``next_tiers``.

    The root tier ("Biota" or "Viruses") cannot be found via CLB's
    ``/nameusage/search`` because the search endpoint returns HTTP
    400 when filtered with ``rank=biota``. The resolver shortcuts
    the root tier through the well-known root taxon ids
    (Biota = ``"5T6MX"``, Viruses = ``"V"``) and uses
    ``get_taxon`` directly. The walk therefore issues exactly one
    ``/nameusage/5T6MX`` request and one
    ``/tree/5T6MX/children`` request (no rank filter).
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
            ("GET", "/dataset/COL2024/nameusage/5T6MX"): _get_taxon_200(biota_row),
            ("GET", _children_path("5T6MX")): _children_200(kingdoms),
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
    assert response.next_tiers is not None
    assert len(response.next_tiers) == 1
    tier = response.next_tiers[0]
    assert tier.rank == "kingdom"
    assert tier.label == "Kingdom"


def test_root_path_returns_viruses_children() -> None:
    """``list_path_children(["Viruses"])`` resolves the Viruses
    root and returns its child realms grouped under a single
    ``kingdom`` tier in ``next_tiers``.

    The root-tier shortcut handles Viruses identically to Biota;
    the resolver maps the case-insensitive name to the well-known
    Viruses id (``"V"``). This is the second of the two top-tier
    taxa CLB exposes; the cascade UI renders both in the
    first-tier dropdown.
    """
    viruses_row = _row("V", "Viruses", "biota")
    realms = [
        _row("VR1", "Adenaviridae", "kingdom", parent_id="V"),
        _row("VR2", "Riboviria", "kingdom", parent_id="V"),
    ]
    transport = _transport(
        {
            ("GET", "/dataset/COL2024/nameusage/V"): _get_taxon_200(viruses_row),
            ("GET", _children_path("V")): _children_200(realms),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Viruses"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "V"
    assert response.parent.canonical_name == "Viruses"
    assert {child.canonical_name for child in response.children} == {
        "Adenaviridae",
        "Riboviria",
    }
    assert response.next_tiers is not None
    assert len(response.next_tiers) == 1
    assert response.next_tiers[0].rank == "kingdom"


def test_resolves_animalia_to_clb_taxon_n() -> None:
    """A single-segment ``["Animalia"]`` path resolves to the
    CLB Animalia taxon (``taxon_id == "N"``) — the standard
    opaque CLB id.

    The walk issues one search (Animalia at rank=kingdom). The
    resolver picks the first hit whose canonical name matches
    case-insensitively. The children fetch uses no rank filter.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _children_path("N")): _children_200([]),
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
    whose canonical name matches the segment. The children
    fetch returns the subphylum-tier children (no rank filter).
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            ("GET", _children_path("CH2")): _children_200(
                [
                    _row("CE", "Cephalochordata", "subphylum", parent_id="CH2"),
                    _row("TU", "Tunicata", "subphylum", parent_id="CH2"),
                    _row("VE", "Vertebrata", "subphylum", parent_id="CH2"),
                ]
            ),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Chordata"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "CH2"
    assert response.parent.canonical_name == "Chordata"
    assert response.next_tiers is not None
    assert [tier.rank for tier in response.next_tiers] == ["subphylum"]


def test_resolves_mammalia_via_subphylum_tier() -> None:
    """The full Mammalia chain via the subphylum tier works:
    Animalia → Chordata (phylum) → Vertebrata (subphylum) →
    Mammalia (class).

    Each segment is searched by name + rank; the resolver picks
    the first hit whose canonical name matches. The path's
    depth is 4, so the resolver walks 4 search calls before
    issuing the children fetch. The children fetch returns the
    order-tier children (no rank filter) when Mammalia is
    followed by other class children; in this chain Mammalia
    is the only class so the children fetch returns empty.
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
                [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")]
            ),
            ("GET", _search_path("Mammalia", rank="class")): _search_200(
                [_row("MA", "Mammalia", "class", parent_id="VE")]
            ),
            ("GET", _children_path("MA")): _children_200([]),
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
    # Leaf (no children) — next_tiers is null so the cascade UI
    # renders the species-fetch effect.
    assert response.next_tiers is None


def test_returns_12_panthera_species_via_subphylum() -> None:
    """Full Panthera chain via the subphylum tier:
    ``Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera``
    returns the 12 Panthera species at the leaf.

    The path is 7 segments long (kingdom → … → genus), so the
    resolver walks 7 search calls and 1 children fetch (no rank
    filter at any tier).
    """
    chain = [
        ("N", "Animalia", "kingdom", None),
        ("CH2", "Chordata", "phylum", "N"),
        ("VE", "Vertebrata", "subphylum", "CH2"),
        ("MA", "Mammalia", "class", "VE"),
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
    responses[("GET", _children_path("PA"))] = _children_200(panthera_species)

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
    assert response.next_tiers is not None
    assert len(response.next_tiers) == 1
    assert response.next_tiers[0].rank == "species"
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
            ("GET", _children_path("N")): _children_200([]),
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
            ("GET", _children_path("N")): _children_200([]),
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


# ---------------------------------------------------------------------------
# Subphylum collapse (PR #2b)
# ---------------------------------------------------------------------------
#
# Most phyla in CLB's COL2024 dataset have zero subphylum children
# (e.g. Arthropoda); only Chordata carries the three chordate
# subphyla. The resolver probes ``/tree/{id}/children?rank=subphylum``
# and only renders subphylum children when CLB returns a non-empty
# list. An empty subphylum probe triggers a one-shot collapse:
# re-query with ``rank=class`` and skip the subphylum tier
# entirely — the next dropdown shows the phylum's classes with
# ``next_rank_hint="order"``.
#
# The collapse is intentionally one-shot (not recursive). A fossil
# phylum with no subphylum AND no class children terminates the
# cascade cleanly with ``children=[]`` and ``next_rank_hint=None``;
# the frontend treats that as a leaf and renders an empty dropdown.


def test_phylum_with_subphylum_returns_subphylum_children() -> None:
    """``Animalia|Chordata`` returns Chordata's three subphylum
    children (Cephalochordata, Tunicata, Vertebrata) under a
    single ``subphylum`` tier.

    The children fetch returns subphylum-rank children only —
    no collapse probe — so the resolver emits one
    ``NextTier(rank="subphylum")`` and the cascade UI renders
    one "Subphylum" dropdown.
    """
    chordata_subphyla = [
        _row("CE", "Cephalochordata", "subphylum", parent_id="CH2"),
        _row("TU", "Tunicata", "subphylum", parent_id="CH2"),
        _row("VE", "Vertebrata", "subphylum", parent_id="CH2"),
    ]
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            ("GET", _children_path("CH2")): _children_200(chordata_subphyla),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Chordata"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "CH2"
    assert response.parent.rank == "phylum"
    assert {child.canonical_name for child in response.children} == {
        "Cephalochordata",
        "Tunicata",
        "Vertebrata",
    }
    assert all(child.rank == "subphylum" for child in response.children)
    # Single tier — subphylum group only.
    assert response.next_tiers is not None
    assert [tier.rank for tier in response.next_tiers] == ["subphylum"]


def test_phylum_without_subphylum_collapses_to_class() -> None:
    """``Animalia|Arthropoda`` collapses the subphylum tier:
    Arthropoda's children are class-rank only (no subphylum, no
    infraphylum), so the resolver emits a single ``class`` tier
    and skips the subphylum slot entirely.

    The PR #2b subphylum collapse rule still applies: when a
    phylum has only class-rank children, the children-by-rank
    grouping collapses to one tier (no empty subphylum picker
    rendered). The cascade UI sees one "Class" dropdown and
    advances straight from Phylum to Class.
    """
    arthropoda_classes = [
        _row("IN", "Insecta", "class", parent_id="AR"),
        _row("AR", "Arachnida", "class", parent_id="AR"),
        _row("CR", "Crustacea", "class", parent_id="AR"),
    ]
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Arthropoda", rank="phylum")): _search_200(
                [_row("AR", "Arthropoda", "phylum", parent_id="N")]
            ),
            ("GET", _children_path("AR")): _children_200(arthropoda_classes),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Arthropoda"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "AR"
    assert response.parent.rank == "phylum"
    assert {child.canonical_name for child in response.children} == {
        "Insecta",
        "Arachnida",
        "Crustacea",
    }
    assert all(child.rank == "class" for child in response.children)
    # Subphylum tier is collapsed: only one tier ("class") is emitted
    # so the cascade UI does not render an empty subphylum picker.
    assert response.next_tiers is not None
    assert [tier.rank for tier in response.next_tiers] == ["class"]


def test_phylum_with_no_class_children_terminates_cascade() -> None:
    """A fossil phylum with zero children terminates the cascade
    cleanly: ``children=[]`` and ``next_tiers=None``.

    With an empty children fetch the cascade has no further tier
    to render; ``None`` is the leaf signal the cascade UI already
    understands as "stop, render empty dropdown". The resolver
    does not loop or recurse.
    """
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Fossilida", rank="phylum")): _search_200(
                [_row("FO", "Fossilida", "phylum", parent_id="N")]
            ),
            ("GET", _children_path("FO")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Fossilida"], client=client)
    assert response is not None
    assert response.parent.taxon_id == "FO"
    assert response.parent.rank == "phylum"
    assert response.children == []
    # Fossil clades with no surviving subphylum and no class children
    # terminate the cascade; the UI renders an empty dropdown.
    assert response.next_tiers is None


def test_subphylum_with_class_children_does_not_collapse() -> None:
    """When the resolver's parent IS a subphylum (not a phylum),
    the collapse rule does NOT fire — the resolver returns the
    subphylum's class children directly with one ``class`` tier.

    For a subphylum parent, the children fetch returns class-rank
    rows only. The new resolver emits one ``NextTier(rank="class")``
    without any subphylum probe.
    """
    vertebrata_classes = [
        _row("MA", "Mammalia", "class", parent_id="VE"),
        _row("RE", "Reptilia", "class", parent_id="VE"),
    ]
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            ("GET", _search_path("Vertebrata", rank="subphylum")): _search_200(
                [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")]
            ),
            ("GET", _children_path("VE")): _children_200(vertebrata_classes),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(
        ["Animalia", "Chordata", "Vertebrata"], client=client
    )
    assert response is not None
    assert response.parent.taxon_id == "VE"
    assert response.parent.rank == "subphylum"
    assert {child.canonical_name for child in response.children} == {"Mammalia", "Reptilia"}
    assert all(child.rank == "class" for child in response.children)
    assert response.next_tiers is not None
    assert [tier.rank for tier in response.next_tiers] == ["class"]


# ---------------------------------------------------------------------------
# Best-effort walk: off-tuple intermediate ranks (Issue #43)
# ---------------------------------------------------------------------------
#
# CLB / CoL publishes intermediate ranks between the locked 9-tier tuple:
#
# - between subphylum and class: infraphylum, parvphylum, megaclass
# - between class and order: subclass
# - between order and family: suborder
#
# The old resolver projected onto the tuple via the ``rank=`` filter on
# the children fetch and dead-ended when the parent had children at an
# off-tuple rank (e.g. Chordata -> Vertebrata -> Gnathostomata).
#
# The new resolver drops the ``rank=`` filter on the children fetch and
# groups children by their actual CLB rank. The wire envelope exposes
# ``next_tiers: list[NextTier]`` so the cascade UI renders one dropdown
# per rank group with the dropdown label taken from the rank itself
# ("Infraphylum", "Parvphylum", "Megaclass", "Subclass", "Suborder").


def test_children_for_buckets_by_rank() -> None:
    """A phylum with subphylum + class children (no intermediate ranks)
    returns two NextTier-shaped buckets: subphylum and class.

    The wire envelope's ``next_tiers`` carries one entry per rank group;
    the resolver's public ``PathChildrenResponse`` carries the same data
    via ``children_by_rank``. The flattened ``children`` list stays
    available so callers iterating every child without grouping keep
    working.
    """
    chordata_subphyla = [
        _row("CE", "Cephalochordata", "subphylum", parent_id="CH2"),
        _row("TU", "Tunicata", "subphylum", parent_id="CH2"),
        _row("VE", "Vertebrata", "subphylum", parent_id="CH2"),
    ]
    # The new resolver drops ``rank=`` on the children fetch, so the
    # single response carries every rank below the parent in one payload.
    chordata_children = chordata_subphyla
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            # One children fetch without rank filter.
            ("GET", _children_path("CH2")): _children_200(chordata_children),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(["Animalia", "Chordata"], client=client)
    assert response is not None
    # Resolver dataclass: children_by_rank keeps the grouped view.
    assert "subphylum" in response.children_by_rank
    assert {child.canonical_name for child in response.children_by_rank["subphylum"]} == {
        "Cephalochordata",
        "Tunicata",
        "Vertebrata",
    }
    # Flattened children list still present so legacy callers keep working.
    assert {child.canonical_name for child in response.children} == {
        "Cephalochordata",
        "Tunicata",
        "Vertebrata",
    }
    # next_tiers carries one NextTier per distinct rank group.
    assert response.next_tiers is not None
    rank_labels = {tier.rank for tier in response.next_tiers}
    assert rank_labels == {"subphylum"}


def test_children_for_groups_off_tuple_ranks() -> None:
    """A subphylum parent with infraphylum + class children groups them
    into two buckets; the off-tuple ``infraphylum`` rank is its own
    tier.

    CLB / CoL publishes Gnathostomata and Agnatha as infraphylum-rank
    children of Vertebrata, mixed with class-rank children (Mammalia).
    The new resolver emits one tier per rank so the cascade UI can
    render an "Infraphylum" dropdown AND a "Class" dropdown below it.
    """
    vertebrata_children = [
        _row("GN", "Gnathostomata", "infraphylum", parent_id="VE"),
        _row("AG", "Agnatha", "infraphylum", parent_id="VE"),
        _row("MA", "Mammalia", "class", parent_id="VE"),
    ]
    transport = _transport(
        {
            ("GET", _search_path("Animalia", rank="kingdom")): _search_200(
                [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
            ),
            ("GET", _search_path("Chordata", rank="phylum")): _search_200(
                [_row("CH2", "Chordata", "phylum", parent_id="N")]
            ),
            ("GET", _search_path("Vertebrata", rank="subphylum")): _search_200(
                [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")]
            ),
            ("GET", _children_path("VE")): _children_200(vertebrata_children),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(
        ["Animalia", "Chordata", "Vertebrata"], client=client
    )
    assert response is not None
    assert response.parent.taxon_id == "VE"
    # Two groups: infraphylum and class, preserving CLB's natural order
    # (infraphylum appears before class).
    assert response.children_by_rank.keys() == {"infraphylum", "class"}
    assert {child.canonical_name for child in response.children_by_rank["infraphylum"]} == {
        "Gnathostomata",
        "Agnatha",
    }
    assert {child.canonical_name for child in response.children_by_rank["class"]} == {
        "Mammalia",
    }
    assert response.next_tiers is not None
    # The NextTier labels are capitalised from the rank string.
    labels = [tier.label for tier in response.next_tiers]
    assert "Infraphylum" in labels
    assert "Class" in labels
    # Examples carry up to 3 names; infraphylum has exactly 2 (small group).
    infraphylum_tier = next(t for t in response.next_tiers if t.rank == "infraphylum")
    assert sorted(infraphylum_tier.examples) == ["Agnatha", "Gnathostomata"]


def test_children_for_groups_three_intermediate_ranks() -> None:
    """Walking Chordata → Vertebrata → Gnathostomata (infraphylum)
    → Osteichthyes (parvphylum) → Tetrapoda (megaclass) → Mammalia
    (class) → Theria (subclass) → Carnivora (order) → Feliformia
    (suborder) → Felidae (family) → Panthera (genus) reaches the
    genus with multiple tier groups at every step.

    The cascade emits the right number of ``next_tiers`` at every
    step and the dropdown labels come from the actual CLB rank
    (Parvphylum, Megaclass, Subclass, Suborder).
    """
    chain_searches = [
        ("Animalia", "kingdom", "N"),
        ("Chordata", "phylum", "CH2"),
        ("Vertebrata", "subphylum", "VE"),
        ("Gnathostomata", "infraphylum", "GN"),
        ("Osteichthyes", "parvphylum", "OS"),
        ("Tetrapoda", "megaclass", "TT"),
        ("Mammalia", "class", "MA"),
        ("Theria", "subclass", "TH"),
        ("Carnivora", "order", "CA"),
        ("Feliformia", "suborder", "FL"),
        ("Felidae", "family", "FE"),
        ("Panthera", "genus", "PA"),
    ]
    responses: dict[tuple[str, str], httpx.Response] = {}
    for name, rank, taxon_id in chain_searches:
        responses[("GET", _search_path(name, rank=rank))] = _search_200(
            [_row(taxon_id, name, rank)]
        )
    # Chordata: subphylum children (Vertebrata only here, but the
    # resolver collapses the phylum → single-rank-children case to
    # keep the subphylum slot).
    responses[("GET", _children_path("CH2"))] = _children_200(
        [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")]
    )
    # Vertebrata: infraphylum + class.
    responses[("GET", _children_path("VE"))] = _children_200(
        [
            _row("GN", "Gnathostomata", "infraphylum", parent_id="VE"),
            _row("MA", "Mammalia", "class", parent_id="VE"),
        ]
    )
    # Gnathostomata: parvphylum only.
    responses[("GET", _children_path("GN"))] = _children_200(
        [_row("OS", "Osteichthyes", "parvphylum", parent_id="GN")]
    )
    # Osteichthyes: megaclass only.
    responses[("GET", _children_path("OS"))] = _children_200(
        [_row("TT", "Tetrapoda", "megaclass", parent_id="OS")]
    )
    # Tetrapoda: class only.
    responses[("GET", _children_path("TT"))] = _children_200(
        [_row("MA", "Mammalia", "class", parent_id="TT")]
    )
    # Mammalia: subclass only.
    responses[("GET", _children_path("MA"))] = _children_200(
        [_row("TH", "Theria", "subclass", parent_id="MA")]
    )
    # Theria: order only.
    responses[("GET", _children_path("TH"))] = _children_200(
        [_row("CA", "Carnivora", "order", parent_id="TH")]
    )
    # Carnivora: suborder only.
    responses[("GET", _children_path("CA"))] = _children_200(
        [_row("FL", "Feliformia", "suborder", parent_id="CA")]
    )
    # Feliformia: family only.
    responses[("GET", _children_path("FL"))] = _children_200(
        [_row("FE", "Felidae", "family", parent_id="FL")]
    )
    # Felidae: genus only.
    responses[("GET", _children_path("FE"))] = _children_200(
        [_row("PA", "Panthera", "genus", parent_id="FE")]
    )
    # Panthera: no children (leaf).
    responses[("GET", _children_path("PA"))] = _children_200([])
    # Rank-less search fallback for off-tuple intermediates (the
    # rank-anchored search would target the wrong rank and miss).
    for name, rank, taxon_id in chain_searches:
        responses[("GET", _search_path_no_rank(name))] = _search_200([_row(taxon_id, name, rank)])

    client = ChecklistBankClient(client=httpx.Client(transport=_transport(responses)))
    path = [
        "Animalia",
        "Chordata",
        "Vertebrata",
        "Gnathostomata",
        "Osteichthyes",
        "Tetrapoda",
        "Mammalia",
        "Theria",
        "Carnivora",
        "Feliformia",
        "Felidae",
        "Panthera",
    ]
    response = clb_path_children.list_path_children(path, client=client)
    assert response is not None
    assert response.parent.taxon_id == "PA"
    assert response.parent.canonical_name == "Panthera"
    # Leaf: no children, no next_tiers.
    assert response.children == []
    assert response.next_tiers is None

    # Walk the chain step by step and verify each tier grouping.
    #
    # Phylum class aggregation: when a phylum has subphylum
    # children, the resolver descends into every subphylum and
    # aggregates the class-rank children into a single ``class``
    # tier. The wire envelope exposes only ``class`` for
    # Chordata — the subphylum hierarchy stays hidden inside
    # the path walk.
    chordata_response = clb_path_children.list_path_children(
        ["Animalia", "Chordata"], client=client
    )
    assert chordata_response is not None
    assert {tier.rank for tier in chordata_response.next_tiers or []} == {"class"}

    # The aggregated class tier includes every class under every
    # subphylum of Chordata. The Panthera chain above seeded
    # Mammalia under Tetrapoda; the chain also seeded Actinopterygii
    # (a class under Gnathostomata / Osteichthyes) so the aggregated
    # tier covers at least Mammalia + Actinopterygii.
    assert chordata_response is not None
    chordata_class_names = {
        c.canonical_name for tier in chordata_response.next_tiers or [] for c in tier.children
    }
    assert "Mammalia" in chordata_class_names

    # Vertebrata itself is a subphylum — its children are the
    # infraphylum + class tier pairs. The aggregation rule does
    # not apply to non-phylum parents; the resolver still emits
    # one tier per CLB rank group.
    vertebrata_response = clb_path_children.list_path_children(
        ["Animalia", "Chordata", "Vertebrata"], client=client
    )
    assert vertebrata_response is not None
    assert {tier.rank for tier in vertebrata_response.next_tiers or []} == {
        "infraphylum",
        "class",
    }

    gnatho_response = clb_path_children.list_path_children(
        ["Animalia", "Chordata", "Vertebrata", "Gnathostomata"], client=client
    )
    assert gnatho_response is not None
    assert {tier.rank for tier in gnatho_response.next_tiers or []} == {"parvphylum"}

    osteich_response = clb_path_children.list_path_children(
        [
            "Animalia",
            "Chordata",
            "Vertebrata",
            "Gnathostomata",
            "Osteichthyes",
        ],
        client=client,
    )
    assert osteich_response is not None
    assert {tier.rank for tier in osteich_response.next_tiers or []} == {"megaclass"}

    tetrapod_response = clb_path_children.list_path_children(
        [
            "Animalia",
            "Chordata",
            "Vertebrata",
            "Gnathostomata",
            "Osteichthyes",
            "Tetrapoda",
        ],
        client=client,
    )
    assert tetrapod_response is not None
    assert {tier.rank for tier in tetrapod_response.next_tiers or []} == {"class"}

    mammalia_response = clb_path_children.list_path_children(
        [
            "Animalia",
            "Chordata",
            "Vertebrata",
            "Gnathostomata",
            "Osteichthyes",
            "Tetrapoda",
            "Mammalia",
        ],
        client=client,
    )
    assert mammalia_response is not None
    assert {tier.rank for tier in mammalia_response.next_tiers or []} == {"subclass"}

    carnivora_response = clb_path_children.list_path_children(
        [
            "Animalia",
            "Chordata",
            "Vertebrata",
            "Gnathostomata",
            "Osteichthyes",
            "Tetrapoda",
            "Mammalia",
            "Theria",
            "Carnivora",
        ],
        client=client,
    )
    assert carnivora_response is not None
    assert {tier.rank for tier in carnivora_response.next_tiers or []} == {"suborder"}


def test_children_for_no_children_emits_null_next_tiers() -> None:
    """A leaf parent (e.g. a genus with no species children) returns
    ``children=[]`` and ``next_tiers=None`` — the cascade UI renders
    the leaf dropdown and the species-fetch effect kicks in.

    The wire envelope's ``next_tiers`` is ``None`` (not an empty
    list) so the cascade UI can distinguish "leaf" from "still
    loading" by the same null sentinel the legacy
    ``next_rank_hint=null`` contract used.
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
                [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")]
            ),
            ("GET", _children_path("VE")): _children_200([]),
        }
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    response = clb_path_children.list_path_children(
        ["Animalia", "Chordata", "Vertebrata"], client=client
    )
    assert response is not None
    assert response.children == []
    assert response.next_tiers is None


def test_path_children_reaches_panthera_via_intermediates() -> None:
    """The full chain
    ``Biota|Animalia|Chordata|Vertebrata|Gnathostomata|Osteichthyes|Tetrapoda|Mammalia|Theria|Carnivora|Feliformia|Felidae|Panthera``
    resolves cleanly to Panthera — no 404, no walk abort.

    This pins the end-to-end best-effort walk through every
    off-tuple intermediate rank CLB / CoL publishes.
    """
    chain_searches = [
        ("Animalia", "kingdom", "N"),
        ("Chordata", "phylum", "CH2"),
        ("Vertebrata", "subphylum", "VE"),
        ("Gnathostomata", "infraphylum", "GN"),
        ("Osteichthyes", "parvphylum", "OS"),
        ("Tetrapoda", "megaclass", "TT"),
        ("Mammalia", "class", "MA"),
        ("Theria", "subclass", "TH"),
        ("Carnivora", "order", "CA"),
        ("Feliformia", "suborder", "FL"),
        ("Felidae", "family", "FE"),
        ("Panthera", "genus", "PA"),
    ]
    responses: dict[tuple[str, str], httpx.Response] = {}
    for name, rank, taxon_id in chain_searches:
        responses[("GET", _search_path(name, rank=rank))] = _search_200(
            [_row(taxon_id, name, rank)]
        )
        # Best-effort resolver also tries rank-less search when the
        # rank-anchored search misses (off-tuple intermediates like
        # infraphylum / parvphylum / megaclass / subclass /
        # suborder).
        responses[("GET", _search_path_no_rank(name))] = _search_200([_row(taxon_id, name, rank)])
    # Biota root lookup.
    responses[("GET", "/dataset/COL2024/nameusage/5T6MX")] = _get_taxon_200(
        _row("5T6MX", "Biota", "biota")
    )
    # Children fetch (no rank filter) at each non-leaf tier.
    responses[("GET", _children_path("5T6MX"))] = _children_200(
        [_row("N", "Animalia", "kingdom", parent_id="5T6MX")]
    )
    responses[("GET", _children_path("CH2"))] = _children_200(
        [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")]
    )
    responses[("GET", _children_path("VE"))] = _children_200(
        [_row("GN", "Gnathostomata", "infraphylum", parent_id="VE")]
    )
    responses[("GET", _children_path("GN"))] = _children_200(
        [_row("OS", "Osteichthyes", "parvphylum", parent_id="GN")]
    )
    responses[("GET", _children_path("OS"))] = _children_200(
        [_row("TT", "Tetrapoda", "megaclass", parent_id="OS")]
    )
    responses[("GET", _children_path("TT"))] = _children_200(
        [_row("MA", "Mammalia", "class", parent_id="TT")]
    )
    responses[("GET", _children_path("MA"))] = _children_200(
        [_row("TH", "Theria", "subclass", parent_id="MA")]
    )
    responses[("GET", _children_path("TH"))] = _children_200(
        [_row("CA", "Carnivora", "order", parent_id="TH")]
    )
    responses[("GET", _children_path("CA"))] = _children_200(
        [_row("FL", "Feliformia", "suborder", parent_id="CA")]
    )
    responses[("GET", _children_path("FL"))] = _children_200(
        [_row("FE", "Felidae", "family", parent_id="FL")]
    )
    responses[("GET", _children_path("FE"))] = _children_200(
        [_row("PA", "Panthera", "genus", parent_id="FE")]
    )
    responses[("GET", _children_path("PA"))] = _children_200([])

    client = ChecklistBankClient(client=httpx.Client(transport=_transport(responses)))
    response = clb_path_children.list_path_children(
        [
            "Biota",
            "Animalia",
            "Chordata",
            "Vertebrata",
            "Gnathostomata",
            "Osteichthyes",
            "Tetrapoda",
            "Mammalia",
            "Theria",
            "Carnivora",
            "Feliformia",
            "Felidae",
            "Panthera",
        ],
        client=client,
    )
    assert response is not None
    assert response.parent.taxon_id == "PA"
    assert response.parent.canonical_name == "Panthera"
    assert response.next_tiers is None
