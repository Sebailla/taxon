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
from typing import cast

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


def test_threshold_default_value_is_1_000_000() -> None:
    """The default lazy-null threshold is the contract value 1,000,000.

    The threshold was raised from 100,000 to 1,000,000 to cover
    the CoL root ``Eukaryota`` and ``incertae sedis`` cases:
    those roots have <15,000 direct children but multi-million-row
    subtrees. The threshold is now checked against the CTE count
    (the total descendant rows the recursive walk traverses), not
    just the direct children. 1M keeps the per-tier envelope
    within the 1s response target.
    """
    assert tree_mod.SPECIES_COUNT_LAZY_NULL_THRESHOLD == 1_000_000


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


def test_species_count_triggers_rebuild_when_above_threshold(
    client: TestClient,
) -> None:
    """``_count_descendant_species`` materialises on first call when threshold < fanout.

    Bigroot has 5 direct children; with ``threshold=3`` the direct-count
    guard fires and the helper now ALSO triggers
    :func:`taxon.api.projections.materialize_for_parent` so the next
    request hits the cache instead of paying the CTE cost again. The
    rebuild returns the species count (5) for this small subtree and
    writes a row to ``taxon_descendant_counts``.
    """
    from taxon.api.projections import REBUILD_BUDGET_SECONDS

    bigroot_id = _id_for_name(client, "Bigroot")
    state = client.app.state.app_state  # type: ignore[attr-defined]
    with state.SessionLocal() as session:
        count = tree_mod._count_descendant_species(session, bigroot_id, threshold=3)
    # Subtree fits under the per-request budget, so the rebuild writes
    # a real integer, not a lazy-null sentinel.
    assert isinstance(count, int)
    assert count == 5

    # The rebuild wrote a row in the projection table. The next call
    # for the same parent returns from the cache without invoking the
    # materialiser again.
    with state.SessionLocal() as session:
        cached = tree_mod._count_descendant_species(session, bigroot_id, threshold=3)
    assert cached == count
    # The cache-hit path bypasses the threshold guard entirely; even
    # threshold=0 returns the cached value.
    with state.SessionLocal() as session:
        cached_under = tree_mod._count_descendant_species(session, bigroot_id, threshold=0)
    assert cached_under == count

    # Suppress the unused-import warning while keeping the symbol
    # visible for the test docstring cross-reference.
    _ = REBUILD_BUDGET_SECONDS


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
        count = tree_mod._count_descendant_species(session, bigroot_id, threshold=10)

    assert isinstance(count, int)
    assert count == 5


def test_lazy_null_helper_returns_none_when_rebuild_exceeds_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the rebuild exceeds :data:`REBUILD_BUDGET_SECONDS`, the helper returns ``None``.

    The descendant-counts-projection change altered the semantics: the
    helper no longer lazy-nulls above the threshold, it triggers a
    synchronous rebuild instead. When the rebuild exceeds the per-
    request SLO the materialiser returns ``None`` and writes nothing —
    preserving the original "don't burn the request budget" guarantee.

    ``taxon.api.tree._count_descendant_species`` does ``from taxon.api.projections
    import materialize_for_parent`` INSIDE the function, so monkey-patching
    ``taxon.api.projections.materialize_for_parent`` (the source module)
    takes effect on the next call: Python re-imports the symbol into the
    function's local namespace every time the lazy import runs.
    """
    from time import sleep

    import taxon.api.projections as projections_mod

    real_materialize = projections_mod.materialize_for_parent

    def _slow(session: object, parent_id: int, **kw: object) -> int | None:
        sleep(0.1)
        # Run the real materialiser with a zero budget so it trips the
        # SLO guard on its own ``perf_counter`` measurement regardless
        # of how fast the real CTE actually is.
        from sqlalchemy.orm import Session

        return real_materialize(cast(Session, session), parent_id, budget_seconds=0.0)

    monkeypatch.setattr(projections_mod, "materialize_for_parent", _slow)

    bigroot_id = _id_for_name(client, "Bigroot")
    state = client.app.state.app_state  # type: ignore[attr-defined]
    with state.SessionLocal() as session:
        count = tree_mod._count_descendant_species(session, bigroot_id, threshold=3)

    assert count is None
