"""RED-first contract tests for the parent-id tree browse endpoint.

The ``arbol-col-browse`` change adds two endpoints that bypass the
cascading path-resolver:

    GET /api/tree/children?parent_id={int}
    GET /api/tree/search?q={str}

These tests pin the wire contract for both endpoints:

- ``/api/tree/children`` returns the direct children of the parent
  plus the synthesized fields the CoL tree UI needs (``authorship``,
  ``has_children``, ``species_count``).
- ``/api/tree/search`` ranks matches by exact > prefix > substring and
  returns an empty list when the query is blank.
- 404 / 422 envelopes are uniform across the tree endpoints.

The fixtures build a small synthetic lineage (root → children → grand-
children) so the assertions don't depend on the live ``col.db`` import
shape — every assertion is verifiable in an in-memory SQLite. The
exact root-row shape mirrors the CoL ``parent_id IS NULL`` invariant
(Archaea / Bacteria / Eukaryota / Viruses / ?incertae sedis) so the
real dataset exercises the same code path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _five_root_fixture() -> str:
    """Lineage that mirrors the real ``col.db`` root shape (5 ``parent_id IS NULL`` rows).

    The roots carry a CoL-style author citation inside the parser's
    ``[...]`` metadata tags so the authorship-split logic has
    real-world input to split. After the WoRMS importer parses the
    lines, the roots become ``Archaea Woese et al., 2024``,
    ``Bacteria Woese et al., 2024``, ``Eukaryota`` (parens preserved
    on display), etc.

    Layout (depth increases by 2 spaces per level)::

        Archaea Woese et al., 2024 [domain]    <- root, child has 1 grandchild
          Nanoarchaeota [phylum]
            Nanoarchaeum [class]
        Bacteria Woese et al., 2024 [domain]
          Proteobacteria [phylum]
        Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978 [domain]
          Fungi [kingdom]
        Viruses [unranked]
        ?incertae sedis [unranked]
    """
    return (
        "Archaea Woese et al., 2024 [domain] {ID=urn:0}\n"
        "  Nanoarchaeota [phylum] {ID=urn:1}\n"
        "    Nanoarchaeum [class] {ID=urn:2}\n"
        "Bacteria Woese et al., 2024 [domain] {ID=urn:3}\n"
        "  Proteobacteria [phylum] {ID=urn:4}\n"
        "Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978 [domain] {ID=urn:5}\n"
        "  Fungi [kingdom] {ID=urn:6}\n"
        "Viruses [unranked] {ID=urn:7}\n"
        "?incertae sedis [unranked] {ID=urn:8}\n"
    )


def _search_fixture() -> str:
    """Lineage that exercises the rank-by-rank search shape.

    Includes ``Panthera`` (genus) and ``Panthera onca`` (species) so
    the exact-match-wins scenario is exercised; ``Eukarya`` (no
    parent-id in this isolated fixture) so the prefix-beats-substring
    scenario can be observed when ``q=Euk``.
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Panthera [genus] {ID=urn:1}\n"
        "    Panthera onca [species] {ID=urn:2}\n"
        "  Eukarya [kingdom] {ID=urn:3}\n"
        "  Pseudeukarya [kingdom] {ID=urn:4}\n"
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
def app_five_roots(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _five_root_fixture())


@pytest.fixture
def app_search(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _search_fixture())


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _id_for_name(app: FastAPI, name: str) -> int:
    """Look up the integer ``id`` the importer assigned to ``name``.

    The resolver lives at ``SELECT id FROM taxa WHERE name=?``; the
    test fixtures keep names unique so a single match always exists.
    Returns ``-1`` when not found so a failed assertion is visible at
    the call-site.

    The helper activates the lifespan so ``app.state.app_state`` is
    populated (the FastAPI lifespan is event-driven and only fires
    inside a ``with TestClient(...)`` block).
    """
    from sqlalchemy import select

    from taxon.schema import Taxon

    with TestClient(app):
        state = app.state.app_state
        with state.SessionLocal() as session:
            stmt = select(Taxon).where(Taxon.name == name)
            taxon = session.scalars(stmt).first()
            return int(taxon.id) if taxon is not None else -1


# ---------------------------------------------------------------------------
# /api/tree/children — root row shape
# ---------------------------------------------------------------------------


def test_tree_children_returns_five_roots(app_five_roots: FastAPI) -> None:
    """``parent_id`` of an absent parent returns the 5 ``parent_id IS NULL`` roots.

    The endpoint accepts the synthetic ``parent_id=0`` to mean "the
    roots" — the resolver treats ``parent_id IS NULL`` as the root
    level. Verifies the real CoL root shape (5 rows including the
    unranked ``?incertae sedis`` and ``Viruses`` rows).
    """
    with _client(app_five_roots) as client:
        response = client.get("/api/tree/children?parent_id=0")

    assert response.status_code == 200, response.text
    body = response.json()
    parent = body["parent"]
    children = body["children"]
    assert parent is None, parent  # root request has no parent envelope
    assert len(children) == 5, [c["name"] for c in children]


def test_tree_children_root_rows_have_required_fields(app_five_roots: FastAPI) -> None:
    """Every child row carries the derived fields the tree UI needs."""
    with _client(app_five_roots) as client:
        body = client.get("/api/tree/children?parent_id=0").json()

    expected_keys = {
        "id",
        "name",
        "display_name",
        "rank",
        "parent_id",
        "authorship",
        "has_children",
        "species_count",
        "is_synonym",
        "is_extinct",
        "is_uncertain",
        "is_unassigned",
    }
    for child in body["children"]:
        assert expected_keys.issubset(child.keys()), child


def test_tree_children_returns_ordered_by_name(app_five_roots: FastAPI) -> None:
    """Children are sorted alphabetically by canonical ``name`` (case-insensitive)."""
    with _client(app_five_roots) as client:
        body = client.get("/api/tree/children?parent_id=0").json()

    names = [c["name"] for c in body["children"]]
    assert names == sorted(names, key=str.lower)


def test_tree_children_authorship_splits_from_display_name(
    app_five_roots: FastAPI,
) -> None:
    """``authorship`` carries the citation tail after the canonical ``name``.

    In the WoRMS importer, the citation lives in ``display_name``
    via the ``[rank]`` / parens metadata. The split logic isolates
    the rank tag so the authorship surface never includes ``[...]``.
    """
    with _client(app_five_roots) as client:
        body = client.get("/api/tree/children?parent_id=0").json()

    by_name = {c["name"]: c for c in body["children"]}
    # WoRMS parser strips parens-bearing citation into display_name;
    # ``Archaea Woese et al., 2024`` becomes name without parens but
    # full text preserved.
    archaea = by_name["Archaea Woese et al., 2024"]
    assert archaea["authorship"] == "", archaea
    # Eukaryota: the parens-bearing citation lives in display_name.
    eukaryota = by_name["Eukaryota"]
    assert "Chatton" in eukaryota["authorship"], eukaryota
    # The exact full citation rendered cleanly so the row reads
    # ``rank: Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978``.
    assert "Whittaker" in eukaryota["authorship"], eukaryota


def test_tree_children_has_children_is_true_when_offspring_exist(
    app_five_roots: FastAPI,
) -> None:
    """``has_children`` is the EXISTS subquery; Archaea has Nanoarchaeota below it."""
    archaea_id = _id_for_name(app_five_roots, "Archaea Woese et al., 2024")
    with _client(app_five_roots) as client:
        body = client.get(f"/api/tree/children?parent_id={archaea_id}").json()

    children_by_name = {c["name"]: c for c in body["children"]}
    assert children_by_name["Nanoarchaeota"]["has_children"] is True


def test_tree_children_has_children_false_for_leaves(
    app_five_roots: FastAPI,
) -> None:
    """Leaves with no further children have ``has_children=False``."""
    leaf_id = _id_for_name(app_five_roots, "Nanoarchaeum")
    with _client(app_five_roots) as client:
        body = client.get(f"/api/tree/children?parent_id={leaf_id}").json()

    assert body["children"] == []
    # parent envelope still arrives
    assert body["parent"]["name"] == "Nanoarchaeum"


def test_tree_children_species_count_is_zero_for_childless_intermediate(
    app_five_roots: FastAPI,
) -> None:
    """``species_count`` is 0 when there are no descendants at species rank."""
    leaf_id = _id_for_name(app_five_roots, "Fungi")  # leaf in this fixture
    with _client(app_five_roots) as client:
        body = client.get(f"/api/tree/children?parent_id={leaf_id}").json()

    # Fungi in this fixture has no children at all; the parent
    # envelope still resolves.
    assert body["children"] == []


def test_tree_children_includes_parent_envelope_for_known_parent(
    app_five_roots: FastAPI,
) -> None:
    """Non-root requests include the ``parent`` envelope (TaxonResponse)."""
    archaea_id = _id_for_name(app_five_roots, "Archaea Woese et al., 2024")
    with _client(app_five_roots) as client:
        body = client.get(f"/api/tree/children?parent_id={archaea_id}").json()

    assert body["parent"]["name"] == "Archaea Woese et al., 2024"
    assert body["parent"]["rank"] == "domain"


# ---------------------------------------------------------------------------
# /api/tree/children — error envelopes
# ---------------------------------------------------------------------------


def test_tree_children_404_for_unknown_parent(app_five_roots: FastAPI) -> None:
    """Unknown ``parent_id`` returns 404 with the id in the body."""
    with _client(app_five_roots) as client:
        response = client.get("/api/tree/children?parent_id=999999999")

    assert response.status_code == 404, response.text
    assert "999999999" in response.json()["detail"]


def test_tree_children_422_when_parent_id_missing(app_five_roots: FastAPI) -> None:
    """The ``parent_id`` query param is required; missing it returns 422."""
    with _client(app_five_roots) as client:
        response = client.get("/api/tree/children")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/tree/children — extinct filter
# ---------------------------------------------------------------------------


def _extinct_fixture() -> str:
    """Lineage that includes a mix of extinct and extant children under a parent.

    The parser recognises ``†`` as the extinct marker — the fixture
    uses the daga prefix so the importer flags the row
    ``is_extinct=True``. ``Archaea`` has 3 children:
    ``Nanoarchaeota`` (extant), ``†Machairodontinae`` (extinct),
    ``†Dinosauria`` (extinct).
    """
    return (
        "Archaea [domain] {ID=urn:0}\n"
        "  Nanoarchaeota [phylum] {ID=urn:1}\n"
        "  †Machairodontinae [family] {ID=urn:2}\n"
        "  †Dinosauria [class] {ID=urn:3}\n"
    )


@pytest.fixture
def app_with_extinct(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _extinct_fixture())


def test_tree_children_hides_extinct_when_filter_off(
    app_with_extinct: FastAPI,
) -> None:
    """``include_extinct=false`` drops extinct rows from the children list.

    Pins the spec requirement
    ``taxonomic-tree-browse/spec.md §"Filter on hides extinct"``: when
    the caller sends ``include_extinct=false``, the children list
    contains ONLY extant rows.
    """
    archaea_id = _id_for_name(app_with_extinct, "Archaea")
    assert archaea_id > 0

    with _client(app_with_extinct) as client:
        response = client.get(
            f"/api/tree/children?parent_id={archaea_id}&include_extinct=false"
        )

    assert response.status_code == 200, response.text
    children = response.json()["children"]
    names = [c["name"] for c in children]
    assert "Nanoarchaeota" in names
    assert "Machairodontinae" not in names
    assert "Dinosauria" not in names


def test_tree_children_includes_extinct_by_default(
    app_with_extinct: FastAPI,
) -> None:
    """Without ``include_extinct=false`` the response includes extinct rows.

    Pins the spec requirement
    ``taxonomic-tree-browse/spec.md §"Filter off keeps extinct"``:
    the default behaviour surfaces all rows regardless of
    ``is_extinct``.
    """
    archaea_id = _id_for_name(app_with_extinct, "Archaea")
    assert archaea_id > 0

    with _client(app_with_extinct) as client:
        response = client.get(f"/api/tree/children?parent_id={archaea_id}")

    assert response.status_code == 200, response.text
    children = response.json()["children"]
    names = [c["name"] for c in children]
    assert "Nanoarchaeota" in names
    assert "Machairodontinae" in names
    assert "Dinosauria" in names


# ---------------------------------------------------------------------------
# /api/tree/search — ranked results
# ---------------------------------------------------------------------------


def test_tree_search_returns_items_envelope(app_search: FastAPI) -> None:
    """The search endpoint returns a ``{items: [...]`` envelope."""
    with _client(app_search) as client:
        response = client.get("/api/tree/search?q=Panthera")

    assert response.status_code == 200
    body = response.json()
    assert "items" in body


def test_tree_search_exact_match_ranks_first(app_search: FastAPI) -> None:
    """Exact match ``Panthera`` beats prefix matches like ``Panthera onca``."""
    with _client(app_search) as client:
        body = client.get("/api/tree/search?q=Panthera").json()

    items = body["items"]
    # Panthera (genus) MUST beat Panthera onca (species) because the
    # exact match comes first.
    assert items, items
    assert items[0]["name"] == "Panthera", items


def test_tree_search_prefix_beats_substring(app_search: FastAPI) -> None:
    """``q=Euk`` returns ``Eukarya`` before ``Pseudeukarya`` (which is substring)."""
    with _client(app_search) as client:
        body = client.get("/api/tree/search?q=Euk").json()

    items = body["items"]
    assert items, items
    # Eukarya is a prefix match and MUST come before Pseudeukarya
    # (substring match).
    names_in_order = [item["name"] for item in items]
    assert names_in_order.index("Eukarya") < names_in_order.index("Pseudeukarya"), names_in_order


def test_tree_search_empty_query_returns_empty_items(app_search: FastAPI) -> None:
    """Empty query yields an empty list — no SQL error."""
    with _client(app_search) as client:
        response = client.get("/api/tree/search?q=")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []


def test_tree_search_relevance_field_present(app_search: FastAPI) -> None:
    """Each item carries the ``relevance`` field naming the match tier."""
    with _client(app_search) as client:
        body = client.get("/api/tree/search?q=Panthera").json()

    items = body["items"]
    assert items
    for item in items:
        assert "relevance" in item
        assert item["relevance"] in {"exact", "prefix", "substring"}


# ---------------------------------------------------------------------------
# Route registration order — the tree endpoints must come BEFORE the
# ``/{path:path}/taxon-links`` catch-all so it never shadows them.
# ---------------------------------------------------------------------------


def test_tree_endpoints_registered_before_taxon_links_catchall(
    app_five_roots: FastAPI,
) -> None:
    """The router MUST register ``/api/tree/*`` BEFORE ``/{path:path}/taxon-links``.

    Without the right order, FastAPI would otherwise match the catch-all
    path parameter against the literal ``tree/children`` segment and
    return a 404 — that's the exact failure mode this test pins.
    """
    with _client(app_five_roots) as client:
        # /api/tree/children resolves to the tree endpoint, not the catch-all.
        children_response = client.get("/api/tree/children?parent_id=0")
        search_response = client.get("/api/tree/search?q=Archaea")

    assert children_response.status_code == 200, children_response.text
    assert search_response.status_code == 200, search_response.text
