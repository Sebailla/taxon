"""Contract tests for the cascade resolver against GBIF-indented fixtures.

PR #58's SQLite-only cascade resolver filters by ``display_level``, but the
GBIF indented-tree importer (:mod:`taxon.indented_import`) intentionally
leaves the column NULL — :func:`taxon.taxonomy.display_level` is applied
at query time. This module pins the equivalence between the WoRMS-shaped
importer (used by the existing fixture tests) and the indented-tree
importer (the new path) against the cascade endpoints.

The tests in this file seed the database with
:func:`taxon.indented_import.import_indented_dataset` so every row carries
``display_level IS NULL`` and then call the public cascade endpoints. With
the resolver computing the display level at query time (via
:func:`taxon.taxonomy.display_level`) the resolver returns the same wire
shape as the WoRMS-seeded fixture suite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _mollusca_fixture() -> str:
    """A small GBIF Backbone-style indented tree.

    Mirrors the chain used by ``test_api_sqlite_only_router`` so the wire
    shape is comparable across the two importer paths:

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
    )


def _seeded_indented_app(tmp_path: Path) -> FastAPI:
    """Build a FastAPI app backed by an indented-import-seeded SQLite.

    Uses :func:`taxon.indented_import.import_indented_dataset` so every
    row carries ``display_level IS NULL``. The cascade resolver must
    compute the bucket on the fly via
    :func:`taxon.taxonomy.display_level`.
    """
    from taxon.api import create_app
    from taxon.indented_import import import_indented_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_mollusca_fixture(), encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)
    return create_app(database_url=f"sqlite:///{db}")


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def app_indented_mollusca(tmp_path: Path) -> FastAPI:
    return _seeded_indented_app(tmp_path)


def test_indented_seeded_rows_have_null_display_level(tmp_path: Path) -> None:
    """The indented importer intentionally leaves ``display_level`` NULL.

    This is the design decision documented at the top of
    :mod:`taxon.indented_import`: the bucket is computed at query time
    via :func:`taxon.taxonomy.display_level`, not denormalised at import
    time. The test pins that contract so a future "optimisation" that
    populates ``display_level`` in the importer triggers an explicit
    conversation with the resolver.
    """
    from taxon.indented_import import import_indented_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(_mollusca_fixture(), encoding="utf-8")
    import_indented_dataset(src, db, batch_size=64)

    conn = sqlite3.connect(db)
    try:
        null_count = conn.execute(
            "SELECT COUNT(*) FROM taxa WHERE display_level IS NOT NULL"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM taxa").fetchone()[0]
    finally:
        conn.close()

    assert total > 0
    assert null_count == 0, (
        "indented importer must leave display_level NULL on every row; "
        "the cascade resolver computes the bucket at query time"
    )


def test_path_children_resolves_phylum_through_indented_seed(
    app_indented_mollusca: FastAPI,
) -> None:
    """``GET /api/path-children`` resolves the phylum tier against GBIF rows.

    With the indented importer, every row has ``display_level IS NULL``.
    The cascade resolver computes the bucket at query time so this
    request resolves Mollusca (phylum) and returns its children plus the
    next-tier dropdown. Before the fix this returned 404 because the
    resolver filtered on ``Taxon.display_level``.
    """
    with _client(app_indented_mollusca) as client:
        response = client.get("/api/path-children?path=Biota|Animalia|Mollusca")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parent"]["name"] == "Mollusca"
    assert body["parent"]["rank"] == "phylum"
    assert body["children"], "phylum tier must surface at least one child"
    names = {child["name"] for child in body["children"]}
    assert "Gastropoda" in names
    assert body["next_tiers"] is not None
    assert any(tier["rank"] == "class" for tier in body["next_tiers"])


def test_species_list_resolves_genus_through_indented_seed(
    app_indented_mollusca: FastAPI,
) -> None:
    """``GET /api/species-list`` resolves the genus through the GBIF path.

    The endpoint walks every segment against ``display_level == bucket``
    in the source-of-truth mode. The indented importer leaves
    ``display_level`` NULL, so without the query-time fallback this
    returns 404 on the family / subfamily hops. With the fix the walk
    reaches Littorina and the species list surfaces Littorina littorea.
    """
    with _client(app_indented_mollusca) as client:
        response = client.get(
            "/api/species-list?path="
            "Animalia%7CMollusca%7CGastropoda%7CLittorinimorpha"
            "%7CLittorinoidea%7CLittorinidae%7CLittorininae%7CLittorina"
        )

    assert response.status_code == 200, response.text
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert "Littorina littorea" in names
