"""RED-first contract tests for the ChecklistBank client.

The cascade resolver composes three CLB calls per dropdown:

1. ``get_taxon(taxon_id)`` to resolve the deepest segment.
2. ``get_children(taxon_id)`` to fetch the children for the next
   dropdown.
3. ``search(q, rank=...)`` to bind a segment name to an id.

These tests pin the wire shape via httpx ``MockTransport`` so the
client can run without hitting the real ChecklistBank API.

The CLB API serves two distinct response shapes:

- ``/dataset/{key}/tree/{id}/children`` returns a flat envelope
  with ``result: [ {...row...}, ... ]``.
- ``/dataset/{key}/nameusage/search?q=&rank=`` returns the same
  envelope but each row carries a ``parentId``.

The parser must consume both shapes via ``.get()`` with sensible
defaults so the resolver never explodes on a missing optional
field.
"""

from __future__ import annotations

from typing import Any

import httpx

from taxon.checklistbank import (
    CLB_BASE_URL,
    DEFAULT_DATASET_KEY,
    ChecklistBankClient,
    _parse_taxon,
)

# ---------------------------------------------------------------------------
# _parse_taxon
# ---------------------------------------------------------------------------


def test_parse_taxon_keeps_only_cascade_relevant_fields() -> None:
    """The CLB row carries ~12 useful fields; everything else
    (issues, habitats, threatStatuses, synonyms, ...) is dropped.
    The cascade labels dropdowns from ``name`` only."""
    raw = {
        "datasetKey": 299029,
        "id": "N",
        "rank": "kingdom",
        "status": "accepted",
        "name": "Animalia",
        "labelHtml": "<i>Animalia</i>",
        "parentId": "5T6MX",
        "count": 2981931,
        "childCount": 7,
        "authorship": None,
        # All of these should be ignored:
        "issues": [],
        "habitats": [],
        "threatStatuses": [],
        "synonym": False,
    }
    taxon = _parse_taxon(raw)
    assert taxon.taxon_id == "N"
    assert taxon.dataset_key == "299029"
    assert taxon.canonical_name == "Animalia"
    assert taxon.rank == "kingdom"
    assert taxon.status == "accepted"
    assert taxon.parent_id == "5T6MX"
    assert taxon.child_count == 7


def test_parse_taxon_handles_missing_optional_fields() -> None:
    """Defensive: leaf rows and search hits often drop optional
    fields (``labelHtml``, ``parentId``, ``count``). The parser
    must coerce them to ``None`` so callers can branch without
    ``KeyError``."""
    raw = {
        "datasetKey": 299029,
        "id": "SP1",
        "rank": "species",
        "status": "accepted",
        "name": "Panthera leo",
    }
    taxon = _parse_taxon(raw)
    assert taxon.taxon_id == "SP1"
    assert taxon.canonical_name == "Panthera leo"
    assert taxon.scientific_name == "Panthera leo"
    assert taxon.label_html is None
    assert taxon.parent_id is None
    assert taxon.count is None
    assert taxon.child_count is None
    assert taxon.status == "accepted"


def test_parse_taxon_uses_label_html_when_present() -> None:
    """CLB renders italics in ``labelHtml``. The cascade UI uses
    this verbatim — the parser must not synthesize a fallback."""
    raw = {
        "datasetKey": 299029,
        "id": "CH2",
        "rank": "phylum",
        "status": "accepted",
        "name": "Chordata",
        "labelHtml": "<i>Chordata</i>",
    }
    taxon = _parse_taxon(raw)
    assert taxon.label_html == "<i>Chordata</i>"


def test_parse_taxon_handles_live_search_envelope() -> None:
    """The real CLB ``/nameusage/search`` envelope nests the row
    under ``result[].usage`` (with ``usage.id``,
    ``usage.name.scientificName`` + ``rank``, ``usage.status``,
    ``usage.datasetKey``) plus a ``classification[]`` breadcrumb.
    The flat shape used in stub tests is also tolerated.

    Captured from the live API on 2026-08-14.
    """
    raw = {
        "id": "N",
        "classification": [
            {
                "id": "5T6MX",
                "name": "Biota",
                "rank": "unranked",
                "status": "accepted",
                "labelHtml": "<i>Biota</i>",
            },
            {
                "id": "N",
                "name": "Animalia",
                "rank": "kingdom",
                "status": "accepted",
                "labelHtml": "Animalia",
            },
        ],
        "usage": {
            "datasetKey": 299029,
            "id": "N",
            "name": {"scientificName": "Animalia", "rank": "kingdom"},
            "rank": "kingdom",
            "status": "accepted",
            "labelHtml": "Animalia",
            "parentId": "5T6MX",
            "count": 2981931,
            "childCount": 34,
        },
    }
    taxon = _parse_taxon(raw)
    assert taxon.taxon_id == "N"
    assert taxon.dataset_key == "299029"
    assert taxon.canonical_name == "Animalia"
    assert taxon.rank == "kingdom"
    assert taxon.status == "accepted"
    assert taxon.parent_id == "5T6MX"
    assert taxon.child_count == 34
    assert taxon.count == 2981931


def test_parse_taxon_handles_live_nameusage_envelope() -> None:
    """The real CLB ``/nameusage/{id}`` response wraps the taxon
    in a top-level ``usage`` object with no flat ``id`` field at
    the root. In the live API, ``rank`` lives under
    ``usage.name.rank`` (a sibling of ``scientificName``), not
    at the payload root.
    """
    raw = {
        "created": "2019-11-20T11:08:11.507938",
        "modified": "2026-08-14T00:00:00Z",
        "usage": {
            "datasetKey": 299029,
            "id": "N",
            "name": {"scientificName": "Animalia", "rank": "kingdom"},
            "rank": "kingdom",
            "status": "accepted",
            "labelHtml": "Animalia",
        },
    }
    taxon = _parse_taxon(raw)
    assert taxon.taxon_id == "N"
    assert taxon.dataset_key == "299029"
    assert taxon.canonical_name == "Animalia"
    assert taxon.rank == "kingdom"
    assert taxon.status == "accepted"


def test_parse_taxon_resolves_rank_from_name_payload() -> None:
    """Live API sometimes puts ``rank`` only inside
    ``payload.name.rank`` (not at the payload root). The parser
    must resolve ``rank`` from either location."""
    raw = {
        "usage": {
            "datasetKey": 299029,
            "id": "CH2",
            "name": {"scientificName": "Chordata", "rank": "phylum"},
            "status": "accepted",
        }
    }
    taxon = _parse_taxon(raw)
    assert taxon.rank == "phylum"


# ---------------------------------------------------------------------------
# Test transport — a stub CLB that returns canned responses.
# ---------------------------------------------------------------------------


def _stub_transport(responses: dict[tuple[str, str], httpx.Response]) -> httpx.MockTransport:
    """Build a :class:`MockTransport` that dispatches on (method, path).

    The cascade resolver issues GET requests to
    ``/dataset/COL2024/tree/{id}/children`` and
    ``/dataset/COL2024/nameusage/search``. The transport returns
    the pre-registered response for the matching (method, path)
    tuple, or 404 for everything else.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key in responses:
            return responses[key]
        return httpx.Response(404, json={"error": "not stubbed"})

    return httpx.MockTransport(handler)


def _animalia_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "datasetKey": 299029,
            "id": "N",
            "rank": "kingdom",
            "status": "accepted",
            "name": "Animalia",
            "labelHtml": "<i>Animalia</i>",
            "parentId": "5T6MX",
            "count": 2981931,
            "childCount": 34,
        },
    )


def _children_response(rows: list[dict[str, Any]], total: int | None = None) -> httpx.Response:
    if total is None:
        total = len(rows)
    return httpx.Response(200, json={"offset": 0, "limit": 300, "total": total, "result": rows})


def _search_response(rows: list[dict[str, Any]], total: int | None = None) -> httpx.Response:
    if total is None:
        total = len(rows)
    return httpx.Response(200, json={"offset": 0, "limit": 20, "total": total, "result": rows})


# ---------------------------------------------------------------------------
# ChecklistBankClient.get_taxon
# ---------------------------------------------------------------------------


def test_get_taxon_returns_parsed_row() -> None:
    """The client surfaces a CLB row as a :class:`ChecklistBankTaxon`."""
    transport = _stub_transport({("GET", "/dataset/COL2024/nameusage/N"): _animalia_response()})
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    taxon = client.get_taxon("N")
    assert taxon is not None
    assert taxon.taxon_id == "N"
    assert taxon.canonical_name == "Animalia"
    assert taxon.rank == "kingdom"
    assert taxon.child_count == 34


def test_get_taxon_returns_none_on_404() -> None:
    """A 404 from CLB means the id does not exist. The resolver
    branches without exception handling, so 404 → None."""
    transport = _stub_transport({})  # every path returns 404
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    taxon = client.get_taxon("DOES_NOT_EXIST")
    assert taxon is None


# ---------------------------------------------------------------------------
# ChecklistBankClient.get_children
# ---------------------------------------------------------------------------


def test_get_children_returns_list() -> None:
    """Children endpoint returns an envelope with ``result[]``.
    The client surfaces only the rows."""
    rows = [
        {
            "datasetKey": 299029,
            "id": "AC",
            "rank": "phylum",
            "status": "accepted",
            "name": "Acanthocephala",
            "labelHtml": "<i>Acanthocephala</i>",
            "count": 1917,
            "childCount": 0,
        },
        {
            "datasetKey": 299029,
            "id": "AN",
            "rank": "phylum",
            "status": "accepted",
            "name": "Annelida",
            "labelHtml": "<i>Annelida</i>",
            "count": 41152,
            "childCount": 0,
        },
    ]
    transport = _stub_transport(
        {("GET", "/dataset/COL2024/tree/N/children"): _children_response(rows)}
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    children = client.get_children("N")
    assert len(children) == 2
    assert children[0].canonical_name == "Acanthocephala"
    assert children[1].canonical_name == "Annelida"


def test_get_children_returns_empty_on_404() -> None:
    """A missing parent returns 404. The client coerces it to an
    empty list so the resolver can render "no children" without
    error handling."""
    transport = _stub_transport({})  # every path returns 404
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    children = client.get_children("DOES_NOT_EXIST")
    assert children == []


def test_get_children_passes_rank_query() -> None:
    """The subphylum probe in PR #2b relies on the client passing
    ``rank=subphylum`` as a query parameter."""
    captured: dict[str, str] = {}

    def rec_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _children_response([])

    recording = httpx.MockTransport(rec_handler)
    client = ChecklistBankClient(client=httpx.Client(transport=recording))
    client.get_children("CH2", rank="subphylum")
    assert "rank=subphylum" in captured["url"]


# ---------------------------------------------------------------------------
# ChecklistBankClient.search
# ---------------------------------------------------------------------------


def test_search_returns_matches() -> None:
    """The search endpoint returns matches with the same row shape
    as the children endpoint, plus a ``parentId`` column."""
    rows = [
        {
            "datasetKey": 299029,
            "id": "N",
            "rank": "kingdom",
            "status": "accepted",
            "name": "Animalia",
            "labelHtml": "<i>Animalia</i>",
            "parentId": "5T6MX",
        }
    ]
    transport = _stub_transport(
        {("GET", "/dataset/COL2024/nameusage/search"): _search_response(rows)}
    )
    client = ChecklistBankClient(client=httpx.Client(transport=transport))
    hits = client.search("Animalia")
    assert len(hits) == 1
    assert hits[0].taxon_id == "N"
    assert hits[0].parent_id == "5T6MX"


def test_search_with_rank_filter() -> None:
    """The cascade resolver binds a path segment to the right rank
    by passing ``rank=phylum`` etc. The client must forward the
    rank as a query parameter."""
    captured: dict[str, str] = {}

    def rec_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _search_response([])

    recording = httpx.MockTransport(rec_handler)
    client = ChecklistBankClient(client=httpx.Client(transport=recording))
    client.search("Chordata", rank="phylum")
    assert "rank=phylum" in captured["url"]
    assert "q=Chordata" in captured["url"]


def test_search_with_offset_and_limit() -> None:
    """Pagination is supported via ``offset`` + ``limit``."""
    captured: dict[str, str] = {}

    def rec_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _search_response([])

    recording = httpx.MockTransport(rec_handler)
    client = ChecklistBankClient(client=httpx.Client(transport=recording))
    client.search("Panthera", limit=50, offset=200)
    assert "limit=50" in captured["url"]
    assert "offset=200" in captured["url"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_dataset_key_is_col2024() -> None:
    """The cascade pins ``COL2024`` so the IDs are reproducible
    across runs. ``3LR`` is documented as the future upgrade
    path but is NOT used in v1."""
    assert DEFAULT_DATASET_KEY == "COL2024"


def test_clb_base_url_is_public() -> None:
    """The base URL points at the public CLB API. No auth required
    for read-only access to the COL2024 dataset."""
    assert CLB_BASE_URL == "https://api.checklistbank.org"


def test_custom_dataset_key_overrides_default() -> None:
    """The client accepts a ``dataset_key`` parameter that
    overrides the default. The cascade resolver never sets it in
    v1 but tests + future releases rely on the override."""
    captured: dict[str, str] = {}

    def rec_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _animalia_response()

    recording = httpx.MockTransport(rec_handler)
    client = ChecklistBankClient(
        dataset_key="CUSTOM2025",
        client=httpx.Client(transport=recording),
    )
    client.get_taxon("N")
    assert "/dataset/CUSTOM2025/" in captured["url"]
