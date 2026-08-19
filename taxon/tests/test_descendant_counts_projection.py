"""RED-first contract tests for the ``descendant-counts-projection`` change.

The :mod:`taxon.api.projections` module owns the rebuild helpers
(:func:`materialize_for_parent`, :func:`materialize_all`), the read
helpers (:func:`lookup_one`, :func:`lookup_many`), and the
``register_display_level`` bridge that closes the
``taxonomy_display_level`` registration gap on bare engines
(``taxon/migrate.py`` and ``taxon/import_data.py`` build engines
without the listener that the FastAPI factory wires).

The tests are RED-first: every helper is asserted BEFORE the
production code lands.

Test inventory (from design.md §RED-first test inventory):

  1.  ``test_register_display_level_attaches_function_to_bare_engine``
  2.  ``test_register_display_level_is_idempotent``
  3.  ``test_register_display_level_fails_on_unregistered_engine``
  4.  ``test_lookup_one_returns_none_when_table_absent``
  5.  ``test_lookup_one_returns_cached_value_after_write``
  6.  ``test_lookup_many_returns_empty_dict_for_empty_input``
  7.  ``test_lookup_many_excludes_missing_ids``
  8.  ``test_table_exists_returns_false_for_missing_table``
  9.  ``test_projected_parent_ids_returns_only_above_threshold``
  10. ``test_projected_parent_ids_skips_root_with_null_parent_id``
  11. ``test_projected_parent_ids_uses_spec_constant``
  12. ``test_rebuild_under_budget_writes_row``
  13. ``test_rebuild_over_budget_skips_write_and_returns_none``
  14. ``test_rebuild_is_idempotent_on_existing_row``
  15. ``test_rebuild_sets_computed_at_iso8601_string``
  16. ``test_materialize_all_populates_only_above_threshold_parents``
  17. ``test_materialize_all_is_idempotent``
  18. ``test_materialize_all_disables_slo_guard_by_default``
  19. ``test_materialize_all_returns_zero_on_empty_database``
  20. ``test_apply_creates_taxon_descendant_counts_table``
  21. ``test_apply_preserves_pre_existing_taxa_rows``
  22. ``test_cache_hit_returns_without_running_cte``
  23. ``test_cache_hit_skips_threshold_guard``
  24. ``test_first_read_materializes_row_and_sets_computed_at``
  25. ``test_cache_miss_below_threshold_uses_existing_cte_path``
  26. ``test_rebuild_total_count_guard_writes_row_when_under_budget``
  27. ``test_batch_merges_cached_and_cte_counts``
  28. ``test_batch_excludes_cached_ids_from_cte_seed``
  29. ``test_batch_returns_all_cached_when_threshold_exceeded_for_none``
  30. ``test_batch_cached_stale_row_wins_over_cte``
  31. ``test_import_dataset_triggers_rebuild``
  32. ``test_import_dataset_rebuild_is_idempotent``
  33. ``test_import_dataset_rebuild_does_not_drop_rows_after_drop_all``
  34. ``test_apply_projection_runs_the_cte_on_a_bare_engine``
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from taxon.schema import Taxon

# ---------------------------------------------------------------------------
# `taxonomy_display_level` registration gap
# ---------------------------------------------------------------------------
#
# The recursive CTE used by every read path calls a SQLite user function
# ``taxonomy_display_level(rank)`` (see ``taxon/api/tree.py:221`` and
# ``taxon/api/_tree_tiers.py:479``). The FastAPI factory attaches the
# function via a ``connect`` listener (``taxon/api/__init__.py:92-95``),
# but the bare engines built by ``taxon.migrate`` and ``taxon.import_data``
# do NOT. Running the CTE from either path raises
# ``sqlite3.OperationalError: no such function: taxonomy_display_level``.
#
# The fix is a single ``register_display_level(engine)`` helper exported
# from :mod:`taxon.api.projections` that wires the listener on the
# caller-supplied engine. The three tests below pin the contract that
# every offline caller can rely on.


def test_register_display_level_attaches_function_to_bare_engine() -> None:
    """``register_display_level`` makes the recursive CTE work on a bare engine.

    Build a fresh SQLite engine with NO ``connect`` listener (mirrors
    ``taxon/migrate.py:233`` which calls ``create_engine(database_url)``
    with no listener). After ``register_display_level(engine)`` the
    function ``taxonomy_display_level(rank)`` resolves on every new
    connection and returns the canonical display-level bucket.
    """
    from taxon.api.projections import register_display_level

    engine = create_engine("sqlite:///:memory:")
    register_display_level(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT taxonomy_display_level('species')")).one()
    assert row[0] == "species", row[0]


def test_register_display_level_is_idempotent() -> None:
    """Calling ``register_display_level`` twice on the same engine does not raise.

    The CLI's ``apply`` and ``apply-projection`` subcommands both touch
    the same engine; re-registering the same function is allowed by
    SQLite (``create_function`` overwrites). The helper must be
    idempotent so the CLI can call it without coordination.
    """
    from taxon.api.projections import register_display_level

    engine = create_engine("sqlite:///:memory:")
    register_display_level(engine)
    # Calling a second time must not raise.
    register_display_level(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT taxonomy_display_level('family')")).one()
    assert row[0] == "family"


def test_register_display_level_fails_on_unregistered_engine() -> None:
    """A bare engine without the registration raises ``OperationalError`` on the CTE.

    This is the regression net for the design's discovery: the
    recursive CTE silently fails on bare engines until the helper
    exists. The test MUST fail on the un-registered engine so the
    fix is observed to land.
    """
    engine = create_engine("sqlite:///:memory:")
    # NO register_display_level call here.

    # SQLAlchemy wraps the underlying ``sqlite3.OperationalError`` in its
    # own ``OperationalError``; the test must accept either so the
    # failure mode is observed at the wire boundary.
    from sqlalchemy.exc import OperationalError as SAOperationalError

    with (
        pytest.raises((sqlite3.OperationalError, SAOperationalError)) as exc_info,
        engine.connect() as conn,
    ):
        conn.execute(text("SELECT taxonomy_display_level('species')")).one()
    assert "taxonomy_display_level" in str(exc_info.value)


# ---------------------------------------------------------------------------
# `_projected_parent_ids` — population predicate
# ---------------------------------------------------------------------------


def _make_taxon(
    session: Session,
    *,
    parent_id: int | None,
    rank: str,
    name: str,
    source_id: str,
) -> Taxon:
    """Persist a single ``Taxon`` row and flush so the id is available."""
    taxon = Taxon(
        source_id=source_id,
        parent_id=parent_id,
        rank=rank,
        name=name,
        display_name=name,
        display_level="species" if rank == "species" else None,
    )
    session.add(taxon)
    session.flush()
    return taxon
