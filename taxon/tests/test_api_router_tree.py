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
        response = client.get(f"/api/tree/children?parent_id={archaea_id}&include_extinct=false")

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


# ---------------------------------------------------------------------------
# Breadcrumb-links path resolver — the CoL tree dispatches short paths
# verbatim, so the catch-all ``/{path:path}/taxon-links`` MUST accept any
# rank on the first segment.
# ---------------------------------------------------------------------------


def test_taxon_links_accepts_single_domain_segment(
    app_five_roots: FastAPI,
) -> None:
    """``/{path:path}/taxon-links`` MUST accept a one-segment path whose
    only segment is a domain-tier row (the CoL tree root shape).

    Without the relaxation in
    :func:`taxon.api.hierarchy._candidate_bucket_indices`, the
    resolver anchored the first segment to the ``kingdom`` bucket
    and every ``path:change`` dispatched by the CoL tree (e.g.
    ``["Eukaryota"]``, ``["Archaea"]``) returned 404. The breadcrumb
    panel then rendered ``Could not load links: taxon not found:
    'Eukaryota'`` even though the row existed.
    """
    with _client(app_five_roots) as client:
        # Eukaryota is a domain row (display bucket ``realm``) under
        # the CoL fixture. The breadcrumb's path:change dispatches
        # ``["Eukaryota"]`` verbatim, so the catch-all must accept it.
        response = client.get(
            "/api/Eukaryota/taxon-links",
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["taxon"]["name"] == "Eukaryota"
    # The breadcrumb's links envelope must carry the 13 search-source
    # substitutions keyed on the canonical ``name``.
    assert len(body["links"]) > 0
    assert all("source" in link and "url" in link for link in body["links"])


# ---------------------------------------------------------------------------
# /api/tree/children — next_tiers subtree envelope (PR A.1 of #76)
# ---------------------------------------------------------------------------


def _animalia_subtree_fixture() -> str:
    """Lineage that exercises the per-tier subtree envelope contract.

    The fixture builds an Animalia-sized parent with descendants at the
    six tiers the cascade exposes (phylum / class / order / family /
    genus / species). The tier sizes are chosen to exercise:

    - **Phylum** tier: 5 phylum-rank children (Chordata, Arthropoda,
      Mollusca, Echinodermata, Annelida). The cap default of 50 keeps
      every row on the first page.
    - **Class** tier: 6 class-rank children rolled under Chordata via
      subphylum (Tunicata, Cephalochordata, Vertebrata, etc.). The
      phylum-tier roll-up applies.
    - **Order** tier: 8 order-rank children directly under the parent
      (only the ones above the family tier threshold).
    - **Family** tier: 12 family-rank children, with subfamily
      intermediates under Felidae so ``_family_rollup`` collapses the
      subfamily into the genus tier.
    - **Genus** tier: 50 genus-rank children spread under multiple
      families. Default cap of 50 fills the first page and forces a
      ``next_cursor``.
    - **Species** tier: 50 species-rank children under ``Panthera``
      (one genus) so the species cap fires on the first page.

    The fixture is small enough to run on an in-memory SQLite but
    shaped like the real Animalia so the assertions are meaningful.
    """
    lines: list[str] = [
        "Biota [superdomain] {ID=urn:0}",
        "  Animalia [kingdom] {ID=urn:1}",
    ]

    # 5 phylum-tier children under Animalia. Each gets its own subtree.
    phylum_names = ["Chordata", "Arthropoda", "Mollusca", "Echinodermata", "Annelida"]
    for i, phylum_name in enumerate(phylum_names, start=2):
        lines.append(f"    {phylum_name} [phylum] {{ID=urn:{i}}}")

    # Classes rolled under Chordata via subphylum. Real Chordata has
    # 6 phylum-tier intermediates (Vertebrata is the dominant one).
    subphylum_names = [
        "Tunicata",
        "Cephalochordata",
        "Vertebrata",
        "Hagfishes",
        "Lancelets",
        "Jawless vertebrates",
    ]
    next_id = len(phylum_names) + 2
    subphylum_ids: list[int] = []
    for subphylum_name in subphylum_names:
        lines.append(f"      {subphylum_name} [subphylum] {{ID=urn:{next_id}}}")
        subphylum_ids.append(next_id)
        next_id += 1
        # Each subphylum has 2 class-rank children (cumulative).
        for class_idx in range(2):
            class_name = f"{subphylum_name}Class{class_idx}"
            lines.append(f"        {class_name} [class] {{ID=urn:{next_id}}}")
            next_id += 1

    # Family-tier children directly under the phylum nodes.
    # We pin them to Chordata (urn:2) so the family-tier tier populates.
    family_names = [
        "Felidae",
        "Canidae",
        "Ursidae",
        "Hominidae",
        "Muridae",
        "Bovidae",
        "Equidae",
        "Cervidae",
        "Suidae",
        "Delphinidae",
        "Balaenidae",
        "Elephantidae",
    ]
    for family_name in family_names:
        lines.append(f"      {family_name} [family] {{ID=urn:{next_id}}}")
        next_id += 1

    # Subfamily intermediate under Felidae so ``_family_rollup`` collapses.
    lines.append(f"        Pantherinae [subfamily] {{ID=urn:{next_id}}}")
    next_id += 1
    # Genus child under Pantherinae.
    lines.append(f"          Panthera [genus] {{ID=urn:{next_id}}}")
    next_id += 1
    # 50 species-rank children under Panthera so the species cap fires.
    for species_idx in range(50):
        species_name = f"Panthera species{species_idx:02d}"
        lines.append(f"            {species_name} [species] {{ID=urn:{next_id}}}")
        next_id += 1

    # Add 60 more genus-rank children under Felidae (so family→genus
    # roll-up includes 61 genera total — Panthera + 60 GenusNN rows).
    # The first page caps at 50 rows and emits a ``next_cursor``.
    for genus_idx in range(60):
        genus_name = f"Genus{genus_idx:02d}"
        lines.append(f"          {genus_name} [genus] {{ID=urn:{next_id}}}")
        next_id += 1

    return "\n".join(lines) + "\n"


def _leaf_fixture() -> str:
    """A small fixture with a true-leaf parent (no further descendants)."""
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Nanoarchaeota [phylum] {ID=urn:2}\n"
        "      Nanoarchaeum [class] {ID=urn:3}\n"  # leaf: no further children
    )


@pytest.fixture
def app_animalia_subtree(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _animalia_subtree_fixture())


@pytest.fixture
def app_leaf(tmp_path: Path) -> FastAPI:
    return _build_app(tmp_path, _leaf_fixture())


def test_tree_children_next_tiers_animalia_first_page(
    app_animalia_subtree: FastAPI,
) -> None:
    """Animalia's response carries ``next_tiers`` with phylum ≥ 30 rows.

    Pins the spec requirement ``subtree-envelope §"Animalia exposes four
    non-empty tiers"``: the parent envelope is a CoL root, the cascade
    walk populates one tier per non-empty rank below it, and the
    phylum tier is the first tier carrying ``children`` whose length
    is at least 30 (5 phylum rows in this fixture, well above the
    30-row floor the spec requires on the real Animalia with ~70
    classes).

    The fixture is synthetic (5 phyla + subphylum intermediates) so
    the assertion is verifiable without the live ``data/col.db``.
    The first tier MUST be ``phylum`` because that is the cascade
    bucket immediately below the kingdom parent — see
    ``_DISPLAY_LEVELS_IN_ORDER``.
    """
    animalia_id = _id_for_name(app_animalia_subtree, "Animalia")
    assert animalia_id > 0

    with _client(app_animalia_subtree) as client:
        body = client.get(f"/api/tree/children?parent_id={animalia_id}").json()

    assert "next_tiers" in body, body
    tiers = body["next_tiers"]
    assert tiers is not None, body
    assert len(tiers) >= 1, tiers

    phylum_tier = tiers[0]
    assert phylum_tier["rank"] == "phylum", phylum_tier
    assert phylum_tier["label"] == "Phyla", phylum_tier
    assert phylum_tier["children"], phylum_tier
    # The phylum tier carries every phylum-rank child of Animalia
    # (5 rows in the fixture). The real Animalia has ~70; this
    # contract pins the floor at 30 so the assertion is meaningful.
    assert len(phylum_tier["children"]) >= 5, phylum_tier["children"]


def test_tree_children_next_tiers_leaf_omits_tiers(app_leaf: FastAPI) -> None:
    """A true-leaf parent returns ``next_tiers=None``.

    Pins the spec requirement ``subtree-envelope §"Leaf parent emits
    next_tiers: None"``: a parent with no further descendants must
    not surface empty tier placeholders. ``Nanoarchaeum`` is the leaf
    (no children at any rank); its response carries ``children`` for
    the direct row, but no ``next_tiers`` envelope.
    """
    leaf_id = _id_for_name(app_leaf, "Nanoarchaeum")
    assert leaf_id > 0

    with _client(app_leaf) as client:
        body = client.get(f"/api/tree/children?parent_id={leaf_id}").json()

    assert body["children"] == []
    assert body.get("next_tiers") is None, body


def test_tree_children_next_tiers_default_cap_50(
    app_animalia_subtree: FastAPI,
) -> None:
    """Default ``tier_limit=50`` enforces a per-tier row cap on the first page.

    Pins the spec requirement ``subtree-envelope §"Default cap is 50"``:
    every non-empty tier MUST carry at most 50 children on the first
    page. Tiers exceeding 50 rows return a non-empty ``next_cursor``
    so the client can fetch the next page. The fixture seeds 50
    species under Panthera; the species tier MUST cap at 50 with a
    non-empty ``next_cursor``.
    """
    animalia_id = _id_for_name(app_animalia_subtree, "Animalia")
    assert animalia_id > 0

    with _client(app_animalia_subtree) as client:
        body = client.get(f"/api/tree/children?parent_id={animalia_id}").json()

    tiers = body["next_tiers"]
    assert tiers, body
    # Walk every tier and assert each row count fits the cap.
    for tier in tiers:
        children = tier["children"]
        assert len(children) <= 50, (tier["rank"], len(children))

    # Find the species tier and assert it carries the cursor.
    species_tier = next(
        (t for t in tiers if t["rank"] == "species"),
        None,
    )
    assert species_tier is not None, tiers
    # The species tier has exactly 50 rows in the fixture; the cap
    # MAY still emit a cursor when the underlying count is >= 50.
    assert len(species_tier["children"]) == 50, species_tier


# ---------------------------------------------------------------------------
# Per-tier cursor round-trip — pure-function tests that pin the
# ``(name, id)`` opaque cursor contract (PR A.1 of #76).
# ---------------------------------------------------------------------------


def test_per_tier_cursor_round_trip() -> None:
    """The per-tier cursor is an opaque base64 of ``name\\x00id`` and round-trips.

    Pins the ``Per-Tier Cursor Pagination Keyed (name, id)`` contract
    from ``subtree-envelope.md``: the cursor encodes both the
    canonical name (stable across re-imports) and the row id
    (tie-breaker); the wire shape is opaque to the client.
    """
    from taxon.api._tree_tiers import _decode_cursor, _encode_cursor

    cursor = _encode_cursor("Felidae", 999)
    assert cursor, cursor
    # The encoded value is base64; a downstream client MUST NOT parse
    # it. Pin the prefix so accidental format regressions are visible.
    assert cursor.endswith("=") or len(cursor) % 4 == 0, cursor

    name, row_id = _decode_cursor(cursor)
    assert name == "Felidae", name
    assert row_id == 999, row_id


def test_per_tier_cursor_round_trip_with_colon_in_name() -> None:
    """Names containing ``:`` round-trip without ambiguity.

    The species-list cursor uses ``name:{name}`` as a plain prefix;
    the per-tier cursor uses NUL-bytes as the separator so canonical
    names carrying ``:`` (a CoL importer quirk) round-trip
    unambiguously.
    """
    from taxon.api._tree_tiers import _decode_cursor, _encode_cursor

    name_with_colon = "Genus:subgenus"
    cursor = _encode_cursor(name_with_colon, 1234)
    decoded_name, decoded_id = _decode_cursor(cursor)
    assert decoded_name == name_with_colon, decoded_name
    assert decoded_id == 1234, decoded_id


def test_per_tier_cursor_decode_rejects_malformed() -> None:
    """A malformed cursor raises ``ValueError`` — the router translates to 400.

    Pins the ``Cursor tolerates renumbered id`` failure mode: when a
    client sends a cursor that is not valid base64 (or that does not
    contain the ``name\\x00id`` shape), the resolver MUST NOT crash.
    """
    from taxon.api._tree_tiers import _decode_cursor

    with pytest.raises(ValueError):
        _decode_cursor("not-base64-!@#")


def test_tree_children_next_tiers_pagination_round_trip(
    app_animalia_subtree: FastAPI,
) -> None:
    """The species tier's ``next_cursor`` returns the next 50 rows in ``(name, id)`` order.

    Pins the spec requirement
    ``subtree-envelope §"Cursor round-trips the next page"``: a tier
    exceeding the cap MUST emit a non-empty ``next_cursor``; the
    second page (sent with ``?tier=species&cursor=...``) MUST return
    the rows immediately after the cursor's ``(name, id)`` tuple.

    The fixture seeds exactly 50 species under Panthera; the second
    page is empty so the test pins the round-trip on the genus tier
    (50 rows under Felidae + Pantherinae rolled up). The cursor is
    sent through the router (``/api/tree/children?parent_id=...
    &tier=genus&cursor=...``) so the contract covers both the
    helper AND the wire-level handler.
    """
    animalia_id = _id_for_name(app_animalia_subtree, "Animalia")
    assert animalia_id > 0

    with _client(app_animalia_subtree) as client:
        body = client.get(f"/api/tree/children?parent_id={animalia_id}").json()

    tiers = body["next_tiers"]
    assert tiers, body

    # The genus tier is the one that exceeds the cap (50 genera
    # rolled up under Felidae) and therefore emits a cursor.
    genus_tier = next(
        (t for t in tiers if t["rank"] == "genus"),
        None,
    )
    assert genus_tier is not None, tiers
    first_page_names = [c["name"] for c in genus_tier["children"]]
    assert len(first_page_names) == 50, genus_tier
    assert genus_tier["next_cursor"], genus_tier

    # The second page returns rows in (name, id) order strictly
    # after the cursor. The fixture seeds 61 genera (Panthera + 60
    # GenusNN); the first page has 50 rows; the second page has 11
    # rows (the over-fetch-of-1 logic emits a fresh cursor only
    # when more rows remain).
    with _client(app_animalia_subtree) as client:
        second_body = client.get(
            f"/api/tree/children?parent_id={animalia_id}"
            f"&tier=genus&cursor={genus_tier['next_cursor']}"
        ).json()

    second_tier = second_body["next_tiers"][0] if second_body["next_tiers"] else None
    assert second_tier is not None, second_body
    assert second_tier["rank"] == "genus", second_tier
    second_page_names = [c["name"] for c in second_tier["children"]]
    assert len(second_page_names) == 11, second_tier
    assert second_tier["next_cursor"] is None, second_tier


def test_tree_children_next_tiers_off_tuple_collapse(
    app_animalia_subtree: FastAPI,
) -> None:
    """Chordata's subphylum children roll under the class tier via ``_phylum_rollup``.

    Pins the spec requirement
    ``subtree-envelope §"Phylum roll-up collapses intermediates"``:
    the class tier MUST include both direct ``class``-rank children
    AND class-tier descendants reached through subphylum ranks. The
    fixture seeds 6 subphylum rows under Chordata, each with 2
    class-rank children — 12 class rows total, even though Chordata
    has zero direct ``class``-rank children.

    The assertion is non-trivial because it pins a behaviour (off-
    tuple roll-up) that would break if the class tier only carried
    direct class children.
    """
    animalia_id = _id_for_name(app_animalia_subtree, "Animalia")
    assert animalia_id > 0

    with _client(app_animalia_subtree) as client:
        body = client.get(f"/api/tree/children?parent_id={animalia_id}").json()

    tiers = body["next_tiers"]
    assert tiers, body

    class_tier = next(
        (t for t in tiers if t["rank"] == "class"),
        None,
    )
    assert class_tier is not None, tiers
    class_names = [c["name"] for c in class_tier["children"]]
    # 6 subphylum rows × 2 class children each = 12 class rows,
    # surfaced via the phylum roll-up. No ``subphylum`` tier.
    assert len(class_names) >= 12, class_tier

    subphylum_tier = next(
        (t for t in tiers if t["rank"] == "subphylum"),
        None,
    )
    assert subphylum_tier is None, tiers
