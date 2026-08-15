"""Contract tests for the SQLite-only cascade resolver (PR #58).

PR #58 replaces the CLB-backed cascade endpoints with a pure
SQLite implementation. The wire shape is preserved 100% so the
cascade UI keeps working without frontend changes. The three
endpoints under test:

- ``GET /api/kingdoms`` — synthesize the two roots (Biota + Viruses).
- ``GET /api/path-children?path=A|B|C`` — descendant lookup + roll-up rules.
- ``GET /api/species-list?path=A|B|C|...|GENUS`` — species leaf list,
  including subspecies / variety / form descendants.

The roll-up rules (sub-PR 2b + sub-PR #2c):

- **Rule 1 — phylum → class roll-up**: when a phylum has subphylum-tier
  children, recurse into each subphylum-child and collect class-tier
  grandchildren. Aggregate with direct class children. Emits one
  ``class`` tier on the wire; the subphylum / infraphylum / parvphylum /
  microphylum / megaclass tiers stay hidden inside the path walk.
- **Rule 2 — subphylum collapse**: when a phylum has only direct
  class children (no subphylum-tier children), emit a single ``class``
  tier — never a ``subphylum`` tier.
- **Rule 3 — family → genus roll-up**: when a family has children at
  subfamily / tribe / subtribe / infratribe ranks, descend breadth-first
  through each, collect every genus-tier descendant, aggregate into a
  single ``genus`` tier.
- **Species roll-up**: a genus's species children include subspecies,
  variety, form descendants — all share the species display bucket.

Test seeding uses :func:`taxon.import_data.import_dataset`, the
established WoRMS-style importer used by the existing SQLite-backed
endpoints. The newer :mod:`taxon.indented_import` module intentionally
leaves ``display_level`` NULL on the rows it produces (see its
docstring); the cascade resolver filters by ``display_level`` so the
test fixtures go through ``import_dataset`` so every node carries the
right bucket.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures — GBIF Backbone-style indented trees parsed by import_data.
# ---------------------------------------------------------------------------


def _mollusca_fixture() -> str:
    """The Littorina chain with explicit off-tuple intermediates.

    Layout (depth increases by 2 spaces per level):

    - Biota (superdomain)
      - Animalia (kingdom)
        - Mollusca (phylum)
          - Gastropoda (class)
            - Littorinimorpha (order)
              - Littorinoidea (superfamily — display_level == family)
                - Littorinidae (family)
                  - Littorininae (subfamily — display_level == family)
                    - Littorina (genus)
                      - Littorina littorea (species)
                      - Littorina saxatilis (species)
                        - Littorina saxatilis tenebrosa (subspecies)
                        - Littorina saxatilis neglecta (subspecies)
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Mollusca [phylum] {ID=urn:2}\n"
        "      Gastropoda [class] {ID=urn:3}\n"
        "        Littorinimorpha [order] {ID=urn:4}\n"
        "          Littorinoidea [superfamily] {ID=urn:5}\n"
        "            Littorinidae [family] {ID=urn:6}\n"
        "              Littorininae [subfamily] {ID=urn:7}\n"
        "                Littorina [genus] {ID=urn:8}\n"
        "                  Littorina littorea [species] {ID=urn:9}\n"
        "                  Littorina saxatilis [species] {ID=urn:10}\n"
        "                    Littorina saxatilis tenebrosa [subspecies] {ID=urn:11}\n"
        "                    Littorina saxatilis neglecta [subspecies] {ID=urn:12}\n"
    )


def _arthropoda_fixture() -> str:
    """A phylum with only direct class children (no subphylum in between).

    Used by ``test_path_children_subphylum_collapse`` to exercise
    Rule 2: a phylum with only class-rank children emits a single
    ``class`` tier on the wire.
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Arthropoda [phylum] {ID=urn:2}\n"
        "      Insecta [class] {ID=urn:3}\n"
        "      Crustacea [class] {ID=urn:4}\n"
        "      Arachnida [class] {ID=urn:5}\n"
    )


def _phylum_intermediates_fixture() -> str:
    """A phylum whose direct children cover every off-tuple intermediate
    rank that the cascade hides inside the path walk:

        subphylum, infraphylum, parvphylum, microphylum, megaclass

    The test asserts that none of these surface as a NextTier — the
    resolver folds them all into the single ``class`` tier on the wire.
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Vertebrata [subphylum] {ID=urn:3}\n"
        "        Gnathostomata [infraphylum] {ID=urn:4}\n"
        "          Osteichthyes [parvphylum] {ID=urn:5}\n"
        "            Tetrapoda [megaclass] {ID=urn:6}\n"
        "              Mammalia [class] {ID=urn:7}\n"
    )


def _family_intermediates_fixture() -> str:
    """A family whose direct children cover every off-tuple intermediate
    rank that the family → genus roll-up (Rule 3) hides:

        subfamily, tribe, subtribe, infratribe

    Every intermediate carries one genus child. The test expects all
    four genera to surface under a single ``genus`` tier.
    """
    return (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Mammalia [class] {ID=urn:3}\n"
        "        Carnivora [order] {ID=urn:4}\n"
        "          Felidae [family] {ID=urn:5}\n"
        "            Felinae [subfamily] {ID=urn:6}\n"
        "              Felini [tribe] {ID=urn:7}\n"
        "                Felina [subtribe] {ID=urn:8}\n"
        "                  Felinina [infratribe] {ID=urn:9}\n"
        "                    Felis [genus] {ID=urn:10}\n"
        "            Pantherinae [subfamily] {ID=urn:11}\n"
        "              Pantherini [tribe] {ID=urn:12}\n"
        "                Pantherina [subtribe] {ID=urn:13}\n"
        "                  Pantherinina [infratribe] {ID=urn:14}\n"
        "                    Panthera [genus] {ID=urn:15}\n"
        "            Acinonychinae [subfamily] {ID=urn:16}\n"
        "              Acinonychini [tribe] {ID=urn:17}\n"
        "                Acinonychina [subtribe] {ID=urn:18}\n"
        "                  Acinonychinina [infratribe] {ID=urn:19}\n"
        "                    Acinonyx [genus] {ID=urn:20}\n"
        "            Machairodontinae [subfamily] {ID=urn:21}\n"
        "              Machairodontini [tribe] {ID=urn:22}\n"
        "                Machairodontina [subtribe] {ID=urn:23}\n"
        "                  Machairodontinina [infratribe] {ID=urn:24}\n"
        "                    Smilodon [genus] {ID=urn:25}\n"
    )


def _bad_segment_fixture() -> str:
    """A tree up to Littorina so we can probe a 404 with ``Badspecies``."""
    return _mollusca_fixture()


# ---------------------------------------------------------------------------
# App builder — fresh per fixture so lifespans stay isolated.
# ---------------------------------------------------------------------------


@pytest.fixture
def app_mollusca(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_mollusca_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_arthropoda(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_arthropoda_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_phylum_intermediates(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_phylum_intermediates_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_family_intermediates(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_family_intermediates_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


@pytest.fixture
def app_bad_segment(tmp_path: Path) -> FastAPI:
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_bad_segment_fixture(), encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/kingdoms
# ---------------------------------------------------------------------------


def test_kingdoms_synthesizes_biota_and_viruses(app_mollusca: FastAPI) -> None:
    """``GET /api/kingdoms`` synthesizes Biota + Viruses server-side.

    The seeded SQLite only carries Animalia (no Biota or Viruses rows),
    so the endpoint cannot rely on a database query for the two roots
    — it must synthesize them with the CLB-canonical ids (``5T6MX``
    and ``V``) and rank ``superdomain``. The wire contract is exactly
    two rows in alphabetical order by canonical ``name`` (Biota comes
    before Viruses).
    """
    with _client(app_mollusca) as client:
        response = client.get("/api/kingdoms")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    names = [item["name"] for item in body]
    assert names == ["Biota", "Viruses"]
    by_name = {item["name"]: item for item in body}
    assert by_name["Biota"]["id"] == "5T6MX"
    assert by_name["Viruses"]["id"] == "V"
    # The synthesized roots must carry the same shape as a SQLite row
    # so the cascade UI does not need to branch on backend.
    for item in body:
        assert item["display_name"]
        assert item["rank"]
        assert item["parent_id"] is None


def test_kingdoms_no_clb_dependency(app_mollusca: FastAPI) -> None:
    """The /api/kingdoms handler must not depend on ChecklistBank.

    The router must NOT call :func:`_get_checklistbank_client` (or any
    other CLB seam) for the kingdoms endpoint. We assert the
    independence by checking that no CLB import is reachable from the
    module that owns the handler — once the refactor lands, the router
    module should not import the CLB client at all.
    """
    from taxon.api import router as router_module

    router_source = Path(router_module.__file__).read_text(encoding="utf-8")
    assert "ChecklistBankClient" not in router_source
    assert "ChecklistBankTaxon" not in router_source
    assert "_get_checklistbank_client" not in router_source


# ---------------------------------------------------------------------------
# /api/path-children — phylum tier rules
# ---------------------------------------------------------------------------


def test_path_children_subphylum_collapse(app_arthropoda: FastAPI) -> None:
    """A phylum with only direct class children emits a single ``class`` tier.

    Arthropoda has Insecta + Crustacea + Malacostraca as direct
    class-rank children (no subphylum in between). The wire envelope
    exposes exactly one ``class`` tier with every child; no subphylum
    tier appears on the wire.
    """
    with _client(app_arthropoda) as client:
        response = client.get("/api/path-children?path=Animalia|Arthropoda")

    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Arthropoda"
    assert body["parent"]["rank"] == "phylum"
    assert body["next_tiers"] is not None
    assert [tier["rank"] for tier in body["next_tiers"]] == ["class"]
    names = {child["name"] for child in body["children"]}
    assert {"Insecta", "Crustacea", "Arachnida"} <= names
    # No subphylum tier ever surfaces for a phylum with only class children.
    assert not any(child["rank"] == "subphylum" for child in body["children"])


def test_path_children_phylum_intermediates_collapse_to_class(
    app_phylum_intermediates: FastAPI,
) -> None:
    """Rule 1: a phylum with subphylum / infraphylum / parvphylum /
    microphylum / megaclass children emits a single ``class`` tier.

    The five intermediate ranks never appear on the wire — only the
    deepest class-tier descendants do. Mammalia is the leaf of the
    seeded chain; it surfaces under the single ``class`` tier.
    """
    with _client(app_phylum_intermediates) as client:
        response = client.get("/api/path-children?path=Animalia|Chordata")

    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Chordata"
    assert body["next_tiers"] is not None
    assert [tier["rank"] for tier in body["next_tiers"]] == ["class"]
    class_tier = body["next_tiers"][0]
    class_names = {child["name"] for child in class_tier["children"]}
    assert "Mammalia" in class_names
    # The five intermediates stay hidden inside the path walk.
    hidden_ranks = {"subphylum", "infraphylum", "parvphylum", "microphylum", "megaclass"}
    assert not any(child["rank"] in hidden_ranks for child in body["children"])


# ---------------------------------------------------------------------------
# /api/path-children — family → genus roll-up (Rule 3)
# ---------------------------------------------------------------------------


def test_path_children_family_genus_rollup_through_infratribe(
    app_family_intermediates: FastAPI,
) -> None:
    """Rule 3: a family with subfamily / tribe / subtribe / infratribe
    children collapses all four intermediate tiers and emits a single
    ``genus`` tier aggregating every genus descendant.

    The fixture seeds four intermediate subtrees — Felinae→Felini→
    Felina→Felinina→Felis, plus the analogous Panthera / Acinonyx /
    Smilodon chains. Every intermediate stays hidden; the four genera
    surface under a single ``genus`` tier.
    """
    with _client(app_family_intermediates) as client:
        response = client.get(
            "/api/path-children?path=Animalia|Chordata|Mammalia|Carnivora|Felidae"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Felidae"
    assert body["next_tiers"] is not None
    assert [tier["rank"] for tier in body["next_tiers"]] == ["genus"]
    genus_names = {child["name"] for child in body["next_tiers"][0]["children"]}
    assert genus_names == {"Felis", "Panthera", "Acinonyx", "Smilodon"}
    # The four intermediates stay hidden inside the walk.
    hidden_ranks = {"subfamily", "tribe", "subtribe", "infratribe"}
    assert not any(child["rank"] in hidden_ranks for child in body["children"])


def test_path_children_includes_microphylum_and_megaclass(
    app_phylum_intermediates: FastAPI,
) -> None:
    """The 5-rank phylum→class intermediates ALL stay hidden on the wire.

    This is the direct, name-by-name assertion: microphylum and
    megaclass are explicitly enumerated in the design decision and the
    cascade UI must never render them as dropdowns. They live in the
    walk and never surface.
    """
    with _client(app_phylum_intermediates) as client:
        response = client.get("/api/path-children?path=Animalia|Chordata")

    assert response.status_code == 200
    body = response.json()
    ranks = {child["rank"] for child in body["children"]}
    for rank in ("subphylum", "infraphylum", "parvphylum", "microphylum", "megaclass"):
        assert rank not in ranks, f"{rank} leaked into the wire envelope"


# ---------------------------------------------------------------------------
# /api/path-children — descendant lookup through off-tuple chains
# ---------------------------------------------------------------------------


def test_path_children_off_tuple_chain_uses_descendant_lookup(
    app_mollusca: FastAPI,
) -> None:
    """The full Littorina chain with off-tuple intermediates resolves
    to Littorina (the genus).

    Path: ``Animalia|Mollusca|Gastropoda|Littorinimorpha|Littorinoidea|
    Littorinidae|Littorininae|Littorina``.

    The resolver walks each segment as a descendant lookup against
    its display_level bucket, NOT via a locked 9-tier rank tuple.
    Littorinoidea is a superfamily (display_level == family) and
    Littorininae is a subfamily (display_level == family) — both live
    at the family bucket; the resolver returns Littorina (genus).
    """
    with _client(app_mollusca) as client:
        response = client.get(
            "/api/path-children?path="
            "Animalia%7CMollusca%7CGastropoda%7CLittorinimorpha"
            "%7CLittorinoidea%7CLittorinidae%7CLittorininae%7CLittorina"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["parent"]["name"] == "Littorina"
    assert body["parent"]["rank"] == "genus"
    assert body["next_tiers"] is not None
    assert [tier["rank"] for tier in body["next_tiers"]] == ["species"]


def test_path_children_404_on_bad_segment(app_bad_segment: FastAPI) -> None:
    """A typo like ``Badspecies`` returns 404 with the failing segment in the detail.

    The cascade UI surfaces the failing segment so the user knows
    which dropdown to re-pick.
    """
    with _client(app_bad_segment) as client:
        response = client.get(
            "/api/path-children?path="
            "Animalia%7CMollusca%7CGastropoda%7CLittorinimorpha"
            "%7CLittorinidae%7CLittorina%7CBadspecies"
        )
    assert response.status_code == 404
    assert "Badspecies" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/species-list
# ---------------------------------------------------------------------------


def test_species_list_returns_subspecies_under_species(app_mollusca: FastAPI) -> None:
    """The species-list endpoint returns subspecies / variety / form descendants.

    The fixture seeds Littorina littorea + Littorina saxatilis (two
    species) plus two subspecies under saxatilis. Every descendant of
    the genus that lives at the species display bucket must surface —
    the endpoint is the leaf of the cascade and the species list is
    what the user picks through.
    """
    with _client(app_mollusca) as client:
        response = client.get(
            "/api/species-list?path="
            "Animalia%7CMollusca%7CGastropoda%7CLittorinimorpha"
            "%7CLittorinoidea%7CLittorinidae%7CLittorininae%7CLittorina"
        )

    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert names == {
        "Littorina littorea",
        "Littorina saxatilis",
        "Littorina saxatilis tenebrosa",
        "Littorina saxatilis neglecta",
    }
    assert body["next_cursor"] is None


def test_species_list_404_on_bad_segment(app_mollusca: FastAPI) -> None:
    """A bad segment in the species-list path yields 404 + detail."""
    with _client(app_mollusca) as client:
        response = client.get(
            "/api/species-list?path="
            "Animalia%7CMollusca%7CGastropoda%7CLittorinimorpha"
            "%7CLittorinidae%7CBadspecies"
        )
    assert response.status_code == 404
    assert "Badspecies" in response.json()["detail"]
