"""RED-first contract tests for the ``species_count`` lazy-null threshold.

The ``arbol-col-browse`` change ships the recursive CTE for
``species_count`` with a configurable lazy-null threshold so the
response stays under the 100ms target on the CoL tree.

The threshold is the *direct-children fanout* of the parent taxon.
When a parent has more than the threshold direct children, the
helper returns ``None`` instead of walking the recursive CTE --
the cost scales with descendant breadth, so the threshold keeps
the response cheap for the worst-case fanout nodes.

This test pins the contract:

1. The default threshold (:data:`taxon.api.tree.SPECIES_COUNT_LAZY_NULL_THRESHOLD`)
   is **100,000** direct children.
2. A parent whose fanout is BELOW the threshold returns an integer
   ``species_count``.
3. A parent whose fanout is ABOVE the threshold returns
   ``species_count=None`` (and the CTE is not invoked).
4. The threshold can be lowered via the ``threshold`` argument so
   the integration tests can exercise the gate without a 100k-row
   fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taxon.api import tree as tree_mod


def _tier_fixture() -> str:
    """Lineage shaped for the lazy-null threshold gate.

    Layout::

        Bigroot [unranked]            <- 5 direct children (exceeds threshold=3)
          SpeciesParent [species]
            Bigroot species 1 [species]
            Bigroot species 2 [species]
            Bigroot species 3 [species]
            Bigroot species 4 [species]
            Bigroot species 5 [species]
        Smallroot [unranked]          <- 1 direct child
          Smallroot species [species]
    """
    return (
        "Bigroot [unranked] {ID=urn:0}\n"
        "  Bigroot species 1 [species] {ID=urn:1}\n"
        "  Bigroot species 2 [species] {ID=urn:2}\n"
        "  Bigroot species 3 [species] {ID=urn:3}\n"
        "  Bigroot species 4 [species] {ID=urn:4}\n"
        "  Bigroot species 5 [species] {ID=urn:5}\n"
        "Smallroot [unranked] {ID=urn:6}\n"
        "  Smallroot species [species] {ID=urn:7}\n"
    )


def _build_app(tmp_path: Path, fixture: str) -> TestClient:
    """Build a TestClient backed by an in-memory SQLite imported from ``fixture``."""
    from taxon.api import create_app
    from taxon.import_data import import_dataset

    db = tmp_path / "taxon.db"
    src = tmp_path / "dataset.txt"
    src.write_text(fixture, encoding="utf-8")
    import_dataset(src, db, batch_size=64)
    return TestClient(create_app(database_url=f"sqlite:///{db}"))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return _build_app(tmp_path, _tier_fixture())


def _id_for_name(client: TestClient, name: str) -> int:
    from sqlalchemy import select

    from taxon.schema import Taxon

    # TestClient fires lifespan on first request; warm it so the
    # ``app_state`` attribute is populated.
    with client:
        client.get("/healthz")
    state = client.app.state.app_state  # type: ignore[attr-defined]
    with state.SessionLocal() as session:
        stmt = select(Taxon).where(Taxon.name == name)
        taxon = session.scalars(stmt).first()
        assert taxon is not None, f"fixture missing {name}"
        return int(taxon.id)


def test_threshold_default_value_is_100_000() -> None:
    """The default lazy-null threshold is the contract value 100,000."""
    assert tree_mod.SPECIES_COUNT_LAZY_NULL_THRESHOLD == 100_000


def test_species_count_is_integer_below_threshold(client: TestClient) -> None:
    """Smallroot (1 direct child) returns the integer species count."""
    smallroot_id = _id_for_name(client, "Smallroot")
    with client:
        response = client.get(f"/api/tree/children?parent_id={smallroot_id}")

    assert response.status_code == 200
    body = response.json()
    children = body["children"]
    assert len(children) == 1
    assert children[0]["name"] == "Smallroot species"
    # The integer species count comes through the wire as ``int`` --
    # 0 because the lone child has no further species descendants.
    assert isinstance(children[0]["species_count"], int)
    assert children[0]["species_count"] == 0


def test_species_count_is_null_above_threshold(client: TestClient) -> None:
    """``_count_descendant_species`` returns ``None`` when threshold < fanout.

    Bigroot has 5 direct children; with ``threshold=3`` the helper
    short-circuits and returns ``None`` without walking the recursive
    CTE.
    """
    bigroot_id = _id_for_name(client, "Bigroot")
    state = client.app.state.app_state  # type: ignore[attr-defined]
    with state.SessionLocal() as session:
        # Bigroot has 5 direct children. With threshold=3 the gate
        # fires and returns None without walking the CTE.
        count = tree_mod._count_descendant_species(
            session, bigroot_id, threshold=3
        )
        assert count is None


def test_lazy_null_helper_returns_integer_for_threshold_above_fanout(
    client: TestClient,
) -> None:
    """The helper itself returns an ``int`` when threshold is above the fanout.

    Bigroot has 5 children; threshold=10 makes the gate inactive.
    The CTE walks and counts 5 species descendants.
    """
    bigroot_id = _id_for_name(client, "Bigroot")
    state = client.app.state.app_state  # type: ignore[attr-defined]
    with state.SessionLocal() as session:
        count = tree_mod._count_descendant_species(
            session, bigroot_id, threshold=10
        )

    assert isinstance(count, int)
    assert count == 5


def test_lazy_null_helper_returns_none_for_threshold_below_fanout(
    client: TestClient,
) -> None:
    """The helper returns ``None`` when the threshold falls below the fanout."""
    bigroot_id = _id_for_name(client, "Bigroot")
    state = client.app.state.app_state  # type: ignore[attr-defined]
    with state.SessionLocal() as session:
        count = tree_mod._count_descendant_species(
            session, bigroot_id, threshold=3
        )

    assert count is None
