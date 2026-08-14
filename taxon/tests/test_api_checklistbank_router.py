"""RED-first contract tests for the ChecklistBank-backed router endpoints.

The router takes a :class:`ChecklistBankClient` per request via FastAPI's
``Depends`` so tests can inject a transport-stubbed client and exercise
the HTTP shape without hitting the public ChecklistBank API.

The tests pin four contracts:

- ``GET /api/kingdoms`` returns the two root taxa (Biota + Viruses).
- ``GET /api/path-children?path=A|B|C`` returns the children of the
  deepest resolved taxon; the resolver applies the subphylum collapse
  rule when the phylum has no subphylum children.
- ``GET /api/species-list?path=A|B|C|...|GENUS`` returns the species
  children of the deepest resolved genus.
- A bad segment yields a 404 with the failing segment in the detail
  body so the cascade UI can highlight the dropdown that produced it.

The router replacement lives in ``taxon/api/router.py`` and is
intentionally atomic: it consumes the ChecklistBank client and emits
the cascade envelope directly. These tests are the only
path-children integration coverage for the CLB backend.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taxon.api.router import _get_checklistbank_client

# ---------------------------------------------------------------------------
# Stub client and transport — a tiny in-process CLB mock.
# ---------------------------------------------------------------------------


class _StubClient:
    """Drop-in :class:`ChecklistBankClient` that serves canned responses.

    The tests construct a transport (a dict of URL → response), wrap
    it in an httpx Client, and pass the client to the stub. The stub
    forwards ``search`` and ``get_children`` to the transport and
    skips the actual HTTP call.
    """

    def __init__(self, transport: httpx.MockTransport) -> None:
        # Pin the base URL so the stub can match full URLs without
        # the path being misinterpreted as relative.
        self._client = httpx.Client(
            transport=transport,
            base_url="https://api.checklistbank.org",
        )
        self._requests: list[str] = []

    def list_roots(
        self,
        dataset_key: str | None = None,
        limit: int = 20,
    ) -> list[Any]:
        url = f"/dataset/COL2024/tree?{urlencode({'limit': limit})}"
        self._requests.append(url)
        r = self._client.get(url)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [self._parse(row) for row in r.json().get("result", [])]

    def search(
        self,
        q: str,
        rank: str | None = None,
        dataset_key: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Any]:
        params: dict[str, Any] = {"q": q, "limit": limit, "offset": offset}
        if rank is not None:
            params["rank"] = rank
        url = f"/dataset/COL2024/nameusage/search?{urlencode(params)}"
        self._requests.append(url)
        r = self._client.get(url)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [self._parse(row) for row in r.json().get("result", [])]

    def get_children(
        self,
        taxon_id: str,
        dataset_key: str | None = None,
        limit: int = 300,
        offset: int = 0,
        rank: str | None = None,
    ) -> list[Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if rank is not None:
            params["rank"] = rank
        url = f"/dataset/COL2024/tree/{taxon_id}/children?{urlencode(params)}"
        self._requests.append(url)
        r = self._client.get(url)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return [self._parse(row) for row in r.json().get("result", [])]

    @staticmethod
    def _parse(row: dict[str, Any]) -> Any:
        """Translate a CLB row into a ``ChecklistBankTaxon`` dataclass."""
        from taxon.checklistbank import ChecklistBankTaxon

        return ChecklistBankTaxon(
            taxon_id=str(row["id"]),
            dataset_key=str(row.get("datasetKey", "COL2024")),
            canonical_name=row.get("name", ""),
            scientific_name=row.get("name", ""),
            rank=row.get("rank", ""),
            parent_id=str(row["parentId"]) if row.get("parentId") is not None else None,
        )


def _app_with_client(client: _StubClient) -> FastAPI:
    """Build an app with the CLB client dependency overridden."""
    from taxon.api import create_app

    app = create_app(database_url="sqlite:///:memory:")
    app.dependency_overrides[_get_checklistbank_client] = lambda: client
    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _row(
    taxon_id: str,
    name: str,
    rank: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Build a CLB ``/tree/{id}/children``-style row."""
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


def _search_url(name: str, rank: str) -> str:
    params: dict[str, Any] = {"q": name, "limit": 20, "offset": 0, "rank": rank}
    return f"/dataset/COL2024/nameusage/search?{urlencode(params)}"


def _search_url_no_rank(name: str) -> str:
    """URL-encode a CLB search-by-name without a ``rank`` filter.

    The best-effort resolver falls back to rank-less search when
    the rank-anchored search misses (off-tuple intermediates) or
    when the path walks past the 9-tier tuple (Issue #43).
    """
    params: dict[str, Any] = {"q": name, "limit": 20, "offset": 0}
    return f"/dataset/COL2024/nameusage/search?{urlencode(params)}"


def _children_url(taxon_id: str, rank: str | None = None) -> str:
    params: dict[str, Any] = {"limit": 300, "offset": 0}
    if rank is not None:
        params["rank"] = rank
    return f"/dataset/COL2024/tree/{taxon_id}/children?{urlencode(params)}"


# ---------------------------------------------------------------------------
# /api/kingdoms
# ---------------------------------------------------------------------------


def test_kingdoms_returns_biota_and_viruses() -> None:
    """``GET /api/kingdoms`` returns exactly two root taxa: Biota + Viruses.

    Biota (``5T6MX``) and Viruses (``V``) are the only root-tier rows in
    ChecklistBank ``COL2024``. The router returns them as ``TaxonResponse``
    items with opaque string ids so the cascade UI's root dropdown is
    deterministic.
    """
    transport = httpx.MockTransport(
        lambda req: (
            httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 2,
                    "result": [
                        _row("5T6MX", "Biota", "biota"),
                        _row("V", "Viruses", "viruses"),
                    ],
                },
            )
            if req.url.path == "/dataset/COL2024/tree"
            else httpx.Response(404)
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/kingdoms")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    names = {item["name"] for item in body}
    assert names == {"Biota", "Viruses"}
    by_name = {item["name"]: item for item in body}
    assert by_name["Biota"]["id"] == "5T6MX"
    assert by_name["Viruses"]["id"] == "V"


# ---------------------------------------------------------------------------
# /api/path-children
# ---------------------------------------------------------------------------


def test_path_children_returns_animalia_phyla() -> None:
    """``GET /api/path-children?path=Animalia`` returns the 7 kingdoms under Biota.

    The cascade starts at the kingdom tier (rank ``kingdom``), not the
    biota tier — Animalia is the first segment after Biota in the cascade
    UI's first dropdown. The resolver walks the segment against CLB and
    returns the phylum children grouped under a single ``phylum`` tier
    in ``next_tiers``.
    """
    animalia_row = _row("N", "Animalia", "kingdom", parent_id="5T6MX")
    phyla_rows = [
        _row("44", "Chordata", "phylum", parent_id="N"),
        _row("54", "Arthropoda", "phylum", parent_id="N"),
        _row("42", "Annelida", "phylum", parent_id="N"),
    ]
    transport = httpx.MockTransport(
        lambda req: {
            ("GET", _search_url("Animalia", rank="kingdom")): httpx.Response(
                200,
                json={"offset": 0, "limit": 20, "total": 1, "result": [animalia_row]},
            ),
            ("GET", _children_url("N")): httpx.Response(
                200,
                json={"offset": 0, "limit": 300, "total": 3, "result": phyla_rows},
            ),
        }.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/path-children?path=Animalia")
    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Animalia"
    assert body["parent"]["id"] == "N"
    names = {child["name"] for child in body["children"]}
    assert {"Chordata", "Arthropoda", "Annelida"} <= names
    # next_rank_hint is gone; next_tiers carries the structured shape.
    assert "next_rank_hint" not in body
    assert "next_tiers" in body
    assert [tier["rank"] for tier in body["next_tiers"]] == ["phylum"]


def test_path_children_subphylum_collapse_for_arthropoda() -> None:
    """``GET /api/path-children?path=Animalia|Arthropoda`` collapses subphylum.

    Arthropoda has zero subphylum children in CLB ``COL2024``. The
    unranked children fetch returns class-rank rows only, so the
    resolver emits a single ``class`` tier in ``next_tiers`` — the
    subphylum slot is collapsed. The cascade UI renders classes
    directly without a subphylum picker.
    """
    arthropoda_row = _row("54", "Arthropoda", "phylum", parent_id="N")
    transport = httpx.MockTransport(
        lambda req: {
            ("GET", _search_url("Animalia", rank="kingdom")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("N", "Animalia", "kingdom")],
                },
            ),
            ("GET", _search_url("Arthropoda", rank="phylum")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [arthropoda_row],
                },
            ),
            ("GET", _children_url("54")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 2,
                    "result": [
                        _row("I", "Insecta", "class", parent_id="54"),
                        _row("C", "Crustacea", "class", parent_id="54"),
                    ],
                },
            ),
        }.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/path-children?path=Animalia%7CArthropoda")
    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Arthropoda"
    assert "next_tiers" in body
    assert [tier["rank"] for tier in body["next_tiers"]] == ["class"]
    names = {child["name"] for child in body["children"]}
    assert {"Insecta", "Crustacea"} <= names
    # Collapse means no subphylum row is emitted.
    assert not any(child["rank"] == "subphylum" for child in body["children"])


def test_path_children_404_on_bad_segment() -> None:
    """A typo like ``Nonexistent`` returns 404 — the cascade UI surfaces
    the failing segment in the error body so the user can re-pick."""
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/path-children?path=Nonexistent")
    assert response.status_code == 404
    assert "Nonexistent" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/species-list
# ---------------------------------------------------------------------------


def test_species_list_returns_panthera_species_via_subphylum() -> None:
    """Full chain Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera
    returns the species children of the Panthera genus.

    The path includes the ``subphylum`` tier (Vertebrata between
    Chordata and Mammalia), which exercises the resolver's subphylum
    handling: Chordata emits the 3 subphyla, Vertebrata walks into
    Mammalia, and Panthera finally returns its 12 species.
    """
    transport = httpx.MockTransport(
        lambda req: {
            ("GET", _search_url("Animalia", rank="kingdom")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("N", "Animalia", "kingdom")],
                },
            ),
            ("GET", _search_url("Chordata", rank="phylum")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("CH2", "Chordata", "phylum", parent_id="N")],
                },
            ),
            ("GET", _children_url("CH2", rank="subphylum")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 3,
                    "result": [
                        _row("VRT", "Vertebrata", "subphylum", parent_id="CH2"),
                        _row("TUN", "Tunicata", "subphylum", parent_id="CH2"),
                        _row("CEP", "Cephalochordata", "subphylum", parent_id="CH2"),
                    ],
                },
            ),
            ("GET", _search_url("Vertebrata", rank="subphylum")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("VRT", "Vertebrata", "subphylum", parent_id="CH2")],
                },
            ),
            ("GET", _children_url("VRT", rank="class")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 1,
                    "result": [_row("MAM", "Mammalia", "class", parent_id="VRT")],
                },
            ),
            ("GET", _search_url("Mammalia", rank="class")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("MAM", "Mammalia", "class", parent_id="VRT")],
                },
            ),
            ("GET", _children_url("MAM", rank="order")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 1,
                    "result": [_row("CAR", "Carnivora", "order", parent_id="MAM")],
                },
            ),
            ("GET", _search_url("Carnivora", rank="order")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("CAR", "Carnivora", "order", parent_id="MAM")],
                },
            ),
            ("GET", _children_url("CAR", rank="family")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 1,
                    "result": [_row("FEL", "Felidae", "family", parent_id="CAR")],
                },
            ),
            ("GET", _search_url("Felidae", rank="family")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("FEL", "Felidae", "family", parent_id="CAR")],
                },
            ),
            ("GET", _children_url("FEL", rank="genus")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 1,
                    "result": [_row("PAN", "Panthera", "genus", parent_id="FEL")],
                },
            ),
            ("GET", _search_url("Panthera", rank="genus")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("PAN", "Panthera", "genus", parent_id="FEL")],
                },
            ),
            ("GET", _children_url("PAN", rank="species")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": 12,
                    "result": [
                        _row(f"P{i}", f"Panthera {sp}", "species", parent_id="PAN")
                        for i, sp in enumerate(
                            [
                                "leo",
                                "onca",
                                "tigris",
                                "pardus",
                                "uncia",
                                "marmorata",
                                "nigricollis",
                                "tigris sondaica",
                                "leo persica",
                                "leo bleyenberghi",
                                "onca goldmani",
                                "tigris altaica",
                            ],
                            start=1,
                        )
                    ],
                },
            ),
        }.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get(
            "/api/species-list?path=Animalia%7CChordata%7CVertebrata%7CMammalia%7CCarnivora%7CFelidae%7CPanthera"
        )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 12
    names = {item["name"] for item in body["items"]}
    assert "Panthera leo" in names


# ---------------------------------------------------------------------------
# /api/path-children — best-effort walk (Issue #43)
# ---------------------------------------------------------------------------


def test_path_children_returns_next_tiers_array() -> None:
    """The wire envelope exposes ``next_tiers`` as a list of
    ``{rank, label, examples, children}`` records and the legacy
    ``next_rank_hint`` field is gone.

    The endpoint must serialise every tier group the resolver emits
    so the cascade UI can render one dropdown per group. The
    ``next_rank_hint`` key is dropped from the JSON response
    entirely — the legacy field is replaced by the structured
    ``next_tiers`` array.
    """
    animalia_row = _row("N", "Animalia", "kingdom", parent_id="5T6MX")
    chordata_children = [
        _row("VE", "Vertebrata", "subphylum", parent_id="CH2"),
        _row("CE", "Cephalochordata", "subphylum", parent_id="CH2"),
        _row("TU", "Tunicata", "subphylum", parent_id="CH2"),
    ]
    transport = httpx.MockTransport(
        lambda req: {
            ("GET", _search_url("Animalia", rank="kingdom")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [animalia_row],
                },
            ),
            ("GET", _search_url("Chordata", rank="phylum")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 20,
                    "total": 1,
                    "result": [_row("CH2", "Chordata", "phylum", parent_id="N")],
                },
            ),
            # No rank= filter on the children fetch.
            ("GET", _children_url("CH2")): httpx.Response(
                200,
                json={
                    "offset": 0,
                    "limit": 300,
                    "total": len(chordata_children),
                    "result": chordata_children,
                },
            ),
        }.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        response = test_client.get("/api/path-children?path=Animalia%7CChordata")
    assert response.status_code == 200
    body = response.json()
    # next_rank_hint is gone — the API no longer emits the field.
    assert "next_rank_hint" not in body
    # next_tiers is the new structured shape.
    assert "next_tiers" in body
    assert isinstance(body["next_tiers"], list)
    assert len(body["next_tiers"]) == 1
    tier = body["next_tiers"][0]
    assert tier["rank"] == "subphylum"
    assert tier["label"] == "Subphylum"
    assert set(tier["examples"]) == {"Vertebrata", "Cephalochordata", "Tunicata"}
    assert len(tier["children"]) == 3
    # The flattened children list stays so callers that ignore the
    # grouping keep working.
    assert {child["name"] for child in body["children"]} == {
        "Vertebrata",
        "Cephalochordata",
        "Tunicata",
    }


def test_path_children_with_off_tuple_chain_returns_multiple_tiers() -> None:
    """Full chordate walk through off-tuple intermediate ranks
    emits the right number of ``next_tiers`` at every step.

    Vertebrata's children include an infraphylum row
    (Gnathostomata) AND a class row (Mammalia). The endpoint
    serialises both as ``next_tiers`` so the cascade UI renders
    an "Infraphylum" dropdown followed by a "Class" dropdown.
    """
    responses: dict[tuple[str, str], httpx.Response] = {
        ("GET", _search_url("Animalia", rank="kingdom")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 20,
                "total": 1,
                "result": [_row("N", "Animalia", "kingdom")],
            },
        ),
        ("GET", _search_url("Chordata", rank="phylum")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 20,
                "total": 1,
                "result": [_row("CH2", "Chordata", "phylum", parent_id="N")],
            },
        ),
        # Chordata: subphylum only (so step 1 emits the subphylum tier).
        ("GET", _children_url("CH2")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 300,
                "total": 1,
                "result": [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")],
            },
        ),
        ("GET", _search_url("Vertebrata", rank="subphylum")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 20,
                "total": 1,
                "result": [_row("VE", "Vertebrata", "subphylum", parent_id="CH2")],
            },
        ),
        # Best-effort: rank-less search fallback for Gnathostomata
        # (the rank-anchored search targets "class" and misses the
        # infraphylum row).
        ("GET", _search_url_no_rank("Gnathostomata")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 20,
                "total": 1,
                "result": [
                    _row("GN", "Gnathostomata", "infraphylum", parent_id="VE"),
                ],
            },
        ),
        # Vertebrata: infraphylum + class rows.
        ("GET", _children_url("VE")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 300,
                "total": 2,
                "result": [
                    _row("GN", "Gnathostomata", "infraphylum", parent_id="VE"),
                    _row("MA", "Mammalia", "class", parent_id="VE"),
                ],
            },
        ),
        # Gnathostomata: parvphylum only.
        ("GET", _children_url("GN")): httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 300,
                "total": 1,
                "result": [_row("OS", "Osteichthyes", "parvphylum", parent_id="GN")],
            },
        ),
    }
    transport = httpx.MockTransport(
        lambda req: responses.get(
            (req.method, req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")),
            httpx.Response(404),
        )
    )
    client = _StubClient(transport)
    app = _app_with_client(client)
    with _client(app) as test_client:
        # Step 1: Chordata emits subphylum children.
        response = test_client.get("/api/path-children?path=Animalia%7CChordata")
    assert response.status_code == 200
    body = response.json()
    assert "next_tiers" in body
    assert [tier["rank"] for tier in body["next_tiers"]] == ["subphylum"]

    with _client(app) as test_client:
        # Step 2: Vertebrata emits infraphylum + class.
        response = test_client.get("/api/path-children?path=Animalia%7CChordata%7CVertebrata")
    assert response.status_code == 200
    body = response.json()
    ranks = [tier["rank"] for tier in body["next_tiers"]]
    assert ranks == ["infraphylum", "class"]
    labels = [tier["label"] for tier in body["next_tiers"]]
    assert labels == ["Infraphylum", "Class"]

    with _client(app) as test_client:
        # Step 3: Gnathostomata emits parvphylum.
        response = test_client.get(
            "/api/path-children?path=Animalia%7CChordata%7CVertebrata%7CGnathostomata"
        )
    assert response.status_code == 200
    body = response.json()
    ranks = [tier["rank"] for tier in body["next_tiers"]]
    assert ranks == ["parvphylum"]
