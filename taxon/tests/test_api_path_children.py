"""RED-first contract tests for the path-aware hierarchy endpoint.

The new endpoint ``GET /api/path-children?path=A|B|C`` replaces the
six rank-named cascade endpoints (phyla, classes, orders,
families, genera, species) with a single endpoint that walks
whatever path the caller provides and returns the direct
children of the deepest resolved taxon, regardless of which
rank they happen to occupy.

Why: CoL introduces intermediate ranks (subphylum, gigaclass,
infraclass, superorder, parvorder, ...) that the fixed six-rank
cascade skips. With 24 kingdoms and 40+ ranks in the live
archive, ``Chordata → classes`` returns 0 results because the
children are subphyla (Vertebrata, Cephalochordata, Tunicata).
The path-aware resolver returns whatever children the deepest
resolved taxon actually has, and the frontend renders an
arbitrary number of dropdowns instead of six fixed ones.

The endpoint contract:

    GET /api/path-children?path=Animalia|Chordata

    200:
      {
        "parent": { "id": ..., "name": "Chordata", "rank": "phylum", ... },
        "children": [
          { "id": ..., "name": "Vertebrata", "rank": " subphylum", ... },
          ...
        ],
        "next_rank_hint": " subphylum"
      }

    404 when the deepest segment does not resolve, with the
    failing segment in the detail (same behaviour as the
    rank-named endpoints so the frontend error UX is
    consistent).

The ``next_rank_hint`` is the rank value the frontend should use
to label the next dropdown. It is the rank that appears most
often among the children so a heterogeneous set (e.g. Chordata
has 3 subphyla + a handful of genus children for unranked
microspecies) still gets a sensible label.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

HIERARCHY_FIXTURE = (
    "Biota [superdomain] {ID=urn:0}\n"
    "  Animalia [kingdom] {ID=urn:1}\n"
    "    Chordata [phylum] {ID=urn:2}\n"
    "      Actinopterygii [class] {ID=urn:3}\n"
    "        Cyprinodontiformes [order] {ID=urn:4}\n"
    "          Goodeidae [family] {ID=urn:5}\n"
    "            Girardinichthys [genus] {ID=urn:6}\n"
    "              Girardinichthys multiradiatus [species] {ID=urn:7}\n"
    "              Girardinichthys viviparus [species] {ID=urn:8}\n"
    "            Ilyodon [genus] {ID=urn:9}\n"
    "              Ilyodon furcidens [species] {ID=urn:10}\n"
    "  Plantae [kingdom] {ID=urn:11}\n"
    "    Magnoliophyta [phylum] {ID=urn:12}\n"
)


# Fixture that simulates CoL's intermediate-rank pattern: Chordata
# has subphylum Vertebrata as its child, mirroring the live CoL
# archive. The cascade UI in 2B/2C broke on this pattern because
# it skipped directly from phylum to class; the path-aware
# resolver must surface the subphylum row instead.
INTERMEDIATE_RANK_FIXTURE = (
    "Biota [superdomain] {ID=urn:0}\n"
    "  Animalia [kingdom] {ID=urn:1}\n"
    "    Chordata [phylum] {ID=urn:2}\n"
    "      Vertebrata [subphylum] {ID=urn:3}\n"
    "        Actinopterygii [class] {ID=urn:4}\n"
    "          Cyprinodontiformes [order] {ID=urn:5}\n"
    "            Goodeidae [family] {ID=urn:6}\n"
    "              Girardinichthys [genus] {ID=urn:7}\n"
    "                Girardinichthys multiradiatus [species] {ID=urn:8}\n"
)


@pytest.fixture
def seeded_app(tmp_path: Path) -> FastAPI:
    """Build an app whose DB is preloaded with ``HIERARCHY_FIXTURE``."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db_path = tmp_path / "taxon.db"
    src_path = tmp_path / "dataset.txt"
    src_path.write_text(HIERARCHY_FIXTURE, encoding="utf-8")
    import_dataset(src_path, db_path, batch_size=64)
    app = create_app(database_url=f"sqlite:///{db_path}")
    # Expose the db_path so tests that need to seed additional rows
    # can use it directly (FastAPI's State object isn't safely
    # accessible from inside request handlers).
    app.state.db_path = db_path
    return app


@pytest.fixture
def seeded_intermediate_app(tmp_path: Path) -> FastAPI:
    """Build an app whose DB has the intermediate-rank pattern
    (Chordata -> Vertebrata subphylum, not a direct class)."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db_path = tmp_path / "taxon.db"
    src_path = tmp_path / "dataset.txt"
    src_path.write_text(INTERMEDIATE_RANK_FIXTURE, encoding="utf-8")
    import_dataset(src_path, db_path, batch_size=64)
    return create_app(database_url=f"sqlite:///{db_path}")


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_path_children_returns_direct_children_of_deepest_resolved_taxon(
    seeded_app: FastAPI,
) -> None:
    """Animalia has one direct child (Chordata). The resolver must
    surface it regardless of rank name."""
    with _client(seeded_app) as client:
        body = client.get("/api/path-children?path=Animalia").json()

    assert body["parent"]["name"] == "Animalia"
    assert body["parent"]["rank"] == "kingdom"
    assert [child["name"] for child in body["children"]] == ["Chordata"]
    assert body["next_rank_hint"] == "phylum"


def test_path_children_walks_path_to_find_terminal_parent(seeded_app: FastAPI) -> None:
    """Animalia → Chordata → Actinopterygii has one child (Cyprinodontiformes)."""
    with _client(seeded_app) as client:
        body = client.get("/api/path-children?path=Animalia%7CChordata%7CActinopterygii").json()

    assert body["parent"]["name"] == "Actinopterygii"
    assert [child["name"] for child in body["children"]] == ["Cyprinodontiformes"]
    assert body["next_rank_hint"] == "order"


def test_path_children_handles_leaf_node_with_no_children(
    seeded_app: FastAPI,
) -> None:
    """A species row has no children; the endpoint returns an empty
    list so the frontend can render an empty-state panel.

    The species ``Girardinichthys multiradiatus`` is stored as a
    single Taxon row with ``name = "Girardinichthys multiradiatus"``,
    parented under the genus ``Girardinichthys``. The path therefore
    traverses seven segments (the binomen is one segment — the
    legacy endpoint's per-segment split does not apply here)."""
    with _client(seeded_app) as client:
        body = client.get(
            "/api/path-children?path="
            "Animalia%7CChordata%7CActinopterygii%7C"
            "Cyprinodontiformes%7CGoodeidae%7C"
            "Girardinichthys%7CGirardinichthys%20multiradiatus"
        ).json()

    assert body["parent"]["name"] == "Girardinichthys multiradiatus"
    assert body["children"] == []
    assert body["next_rank_hint"] is None


# ---------------------------------------------------------------------------
# Intermediate-rank handling — the CoL-shape behaviour that motivated the
# refactor.
# ---------------------------------------------------------------------------


def test_path_children_returns_subphylum_when_class_was_assumed(
    seeded_intermediate_app: FastAPI,
) -> None:
    """Animalia → Chordata has one direct child: Vertebrata (subphylum).

    The old endpoint ``/api/Animalia/Chordata/classes`` returned
    ``[]`` because no Chordata child has rank == 'class'. The
    new endpoint surfaces the subphylum instead. The
    ``next_rank_hint`` is now the bucket name so the dropdown
    label stays stable across the 40+ intermediate ranks CoL
    publishes — subphylum collapses into the ``phylum`` bucket."""
    with _client(seeded_intermediate_app) as client:
        body = client.get("/api/path-children?path=Animalia%7CChordata").json()

    assert body["parent"]["name"] == "Chordata"
    assert [child["name"] for child in body["children"]] == ["Vertebrata"]
    assert body["next_rank_hint"] == "phylum"


def test_path_children_chains_through_subphylum_to_class(
    seeded_intermediate_app: FastAPI,
) -> None:
    """End-to-end: Animalia → Chordata → Vertebrata → Actinopterygii
    returns Cyprinodontiformes as a child. The resolver must chain
    through the subphylum without dropping into the old six-rank
    assumption."""
    with _client(seeded_intermediate_app) as client:
        body = client.get(
            "/api/path-children?path=Animalia%7CChordata%7CVertebrata%7CActinopterygii"
        ).json()

    assert body["parent"]["name"] == "Actinopterygii"
    assert [child["name"] for child in body["children"]] == ["Cyprinodontiformes"]
    assert body["next_rank_hint"] == "order"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_path_children_404_when_deepest_segment_does_not_resolve(
    seeded_app: FastAPI,
) -> None:
    """The same error semantics as the rank-named endpoints: 404
    when the deepest segment does not resolve, with the failing
    segment in the detail."""
    with _client(seeded_app) as client:
        response = client.get("/api/path-children?path=Animalia%7CChordata%7CNonexistent")

    assert response.status_code == 404
    assert "Nonexistent" in response.json()["detail"]


def test_path_children_404_when_first_segment_unknown(
    seeded_app: FastAPI,
) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/path-children?path=Marsupialia")

    assert response.status_code == 404
    assert "Marsupialia" in response.json()["detail"]


def test_path_children_400_when_path_missing(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/path-children")

    assert response.status_code == 422  # FastAPI's default for missing query params


def test_path_children_400_when_path_empty(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        response = client.get("/api/path-children?path=")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Case insensitivity (the rank-named endpoints are case-insensitive; the
# path-aware one must be too).
# ---------------------------------------------------------------------------


def test_path_children_is_case_insensitive(seeded_app: FastAPI) -> None:
    with _client(seeded_app) as client:
        body = client.get("/api/path-children?path=animalia%7Cchordata%7Cactinopterygii").json()

    assert body["parent"]["name"] == "Actinopterygii"
    assert [child["name"] for child in body["children"]] == ["Cyprinodontiformes"]


# ---------------------------------------------------------------------------
# next_rank_hint rules
# ---------------------------------------------------------------------------


def test_next_rank_hint_is_most_common_rank_among_children(
    tmp_path: Path,
) -> None:
    """When the children of the deepest taxon are heterogeneous (e.g.
    a genus has 2 species + 1 subspecies, or an unranked taxon
    has genus + species + unranked children), the hint picks
    the rank that occurs most often so the frontend can pick a
    sensible label for the next dropdown."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    fixture = (
        "Biota [superdomain] {ID=urn:0}\n"
        "  Animalia [kingdom] {ID=urn:1}\n"
        "    Chordata [phylum] {ID=urn:2}\n"
        "      Goodeidae [family] {ID=urn:3}\n"
        "        Girardinichthys [genus] {ID=urn:4}\n"
        "          Girardinichthys multiradiatus [species] {ID=urn:5}\n"
        "          Girardinichthys viviparus [species] {ID=urn:6}\n"
        "          Girardinichthys sp1 [subspecies] {ID=urn:7}\n"
    )
    db_path = tmp_path / "taxon.db"
    src_path = tmp_path / "dataset.txt"
    src_path.write_text(fixture, encoding="utf-8")
    import_dataset(src_path, db_path, batch_size=64)
    app = create_app(database_url=f"sqlite:///{db_path}")

    with _client(app) as client:
        body = client.get(
            "/api/path-children?path=Animalia%7CChordata%7CGoodeidae%7CGirardinichthys"
        ).json()

    # Three children: 2 species + 1 subspecies → hint is 'species'.
    assert body["next_rank_hint"] == "species"


def test_next_rank_hint_is_none_for_leaf_node(seeded_app: FastAPI) -> None:
    """A species has no children; the hint must be null so the
    frontend can stop emitting dropdowns."""
    with _client(seeded_app) as client:
        body = client.get(
            "/api/path-children?path=Animalia%7CChordata%7CActinopterygii%7C"
            "Cyprinodontiformes%7CGoodeidae%7CGirardinichthys"
        ).json()

    assert body["parent"]["name"] == "Girardinichthys"
    assert [child["name"] for child in body["children"]] == [
        "Girardinichthys multiradiatus",
        "Girardinichthys viviparus",
    ]
    assert body["next_rank_hint"] == "species"


# ---------------------------------------------------------------------------
# The old rank-named endpoints keep working (the path-aware one is additive;
# the cleanup lands in a follow-up PR).
# ---------------------------------------------------------------------------


def test_old_phyla_endpoint_still_works(seeded_app: FastAPI) -> None:
    """Regression guard: the new endpoint must not break the existing
    rank-named endpoints. Their cleanup is a separate PR."""
    with _client(seeded_app) as client:
        body = client.get("/api/Animalia/phyla").json()

    assert [item["name"] for item in body] == ["Chordata"]


# ---------------------------------------------------------------------------
# Cascade display_level filter — unranked rows and historical ranks are
# hidden from the cascade UI to keep the dropdowns manageable.
# ---------------------------------------------------------------------------


def test_path_children_excludes_unranked_rows(seeded_app: FastAPI) -> None:
    """``unranked`` is the canonical "exclude from cascade" signal. The
    resolver must filter it out so the cascade UI does not show millions
    of placeholder rows that CoL ships awaiting taxonomic review."""
    import sqlite3

    db_path = seeded_app.state.db_path
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO taxa (
            source_id, parent_id, rank, name, display_name, display_level,
            is_synonym, is_extinct, is_uncertain, is_unassigned
        )
        VALUES (?, ?, ?, ?, ?, NULL, 0, 0, 0, 0)
        """,
        ("urn:unranked-1", 1, "unranked", "Incertae_sedis_A", "Incertae sedis A"),
    )
    conn.commit()
    conn.close()

    with _client(seeded_app) as client:
        body = client.get("/api/path-children?path=Animalia").json()

    names = [child["name"] for child in body["children"]]
    assert "Chordata" in names
    assert "Incertae_sedis_A" not in names


def test_path_children_excludes_historical_ranks(seeded_app: FastAPI) -> None:
    """Historical ranks (``proles``, ``natio``, ``lusus``, ...) used by
    19th-century taxonomy must not leak into the cascade. The CoL
    archive carries a few thousand of them; the resolver filters them
    via the whitelist in :mod:`taxon.taxonomy`."""
    import sqlite3

    db_path = seeded_app.state.db_path
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO taxa (
            source_id, parent_id, rank, name, display_name, display_level,
            is_synonym, is_extinct, is_uncertain, is_unassigned
        )
        VALUES (?, ?, ?, ?, ?, NULL, 0, 0, 0, 0)
        """,
        [
            ("urn:proles-1", 1, "proles", "Proles procumbens", "Proles procumbens"),
            ("urn:natio-1", 1, "natio", "Natio alpina", "Natio alpina"),
        ],
    )
    conn.commit()
    conn.close()

    with _client(seeded_app) as client:
        body = client.get("/api/path-children?path=Animalia").json()

    names = [child["name"] for child in body["children"]]
    assert "Proles procumbens" not in names
    assert "Natio alpina" not in names


def test_next_rank_hint_is_a_cascade_bucket_not_a_raw_rank(
    seeded_app: FastAPI
) -> None:
    """The frontend renders the next dropdown label from the
    display_level bucket, not the child's raw rank. This is what
    lets the cascade UI keep ``class Rank Name`` as the dropdown
    label even when CoL publishes the intermediate rank
    ``superclass`` or ``infraclass``."""
    with _client(seeded_app) as client:
        body = client.get("/api/path-children?path=Animalia").json()

    # Chordata is the (only) phylum-level child of Animalia in the
    # fixture. The hint for the next dropdown is the modal bucket
    # among the children of Animalia = "phylum" (Chordata is the
    # only child the cascade sees). The frontend uses this to label
    # the next dropdown instead of having to map rank -> drop label.
    assert body["next_rank_hint"] == "phylum"
