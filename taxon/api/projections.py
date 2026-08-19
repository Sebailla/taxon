"""Cached ``(species_count, total_count)`` projection for threshold-exceeding parents.

The :data:`taxon.api.tree.SPECIES_COUNT_LAZY_NULL_THRESHOLD` guard is
the right tool for any single subtree whose recursive walk stays under
the per-request SLO. For the long tail of parents with millions of
descendants (Animalia with 22,711 descendants / 950k species,
Eukaryota with 5.6M descendants, Methanobacteriota with 1,064) the
recursive CTE is too expensive to run per request. The fix is to
materialise the count once, cache it in a SQLite table, and let the
read path serve the cache in O(1).

Module layout
-------------

- :func:`register_display_level` — closes the
  ``taxonomy_display_level`` SQLite user-function registration gap on
  bare engines built by ``taxon.migrate`` and ``taxon.import_data``.
  Every helper in this module assumes the function is registered on
  the engine.
- :func:`lookup_one` / :func:`lookup_many` — read helpers used by
  :mod:`taxon.api.tree` and :mod:`taxon.api._tree_tiers`. They never
  raise when the projection table is missing — the projection is
  additive and a freshly-created DB has not materialised anything yet.
- :func:`_table_exists` / :func:`_projected_parent_ids` — population
  helpers. The first returns ``False`` when the table is not yet in
  the engine; the second returns the population (every taxon whose
  direct-children count exceeds the threshold).
- :func:`materialize_for_parent` — synchronous rebuild for a single
  parent. Commits the row only when the rebuild finishes within the
  per-request SLO; otherwise returns ``None`` so the read path falls
  back to the lazy-null behaviour.
- :func:`materialize_all` — iterates the population and calls
  :func:`materialize_for_parent` per parent. Used by
  ``taxon.import_data`` at the end of a CoL re-import and by the
  ``python -m taxon.migrate apply-projection`` subcommand.

The :data:`REBUILD_BUDGET_SECONDS` cap is the only knob the read path
exposes. Offline callers (``apply-projection``, ``import_data``) pass
``budget_seconds=None`` to bypass the guard — they have no SLO.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from time import perf_counter

from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from taxon.api.tree import SPECIES_COUNT_LAZY_NULL_THRESHOLD, SPECIES_DISPLAY_LEVEL
from taxon.schema import Taxon, TaxonDescendantCount
from taxon.taxonomy import display_level

_logger = logging.getLogger(__name__)

#: Per-request rebuild budget. A materialisation that exceeds this
#: threshold returns ``None`` so the read path falls back to lazy-null
#: — the projection is an optimisation, not a guarantee. ``1s`` keeps
#: the rebuild inside the per-tier CTE walk's response target. Offline
#: callers (``apply-projection``, ``import_data``) pass
#: ``budget_seconds=None`` to disable the guard.
REBUILD_BUDGET_SECONDS: float = 1.0

#: Table names owned by this module. Mirrors :data:`taxon.api.workspace.WORKSPACE_TABLES`
#: so ``python -m taxon.migrate apply`` and the import-data hook can
#: discover every table this change introduces without the migrate CLI
#: learning about each new one individually.
PROJECTION_TABLES: tuple[str, ...] = ("taxon_descendant_counts",)


def register_display_level(engine: Engine) -> None:
    """Attach ``taxonomy_display_level`` to every new SQLite connection.

    The FastAPI factory wires the function on its engine
    (``taxon/api/__init__.py:92-95``) but ``taxon.migrate`` and
    ``taxon.import_data`` build bare engines without the listener.
    Running the recursive CTE from either path raises
    ``sqlite3.OperationalError: no such function: taxonomy_display_level``
    — invisible to any unit test that uses the API's engine.

    This helper attaches the same listener to a caller-supplied engine
    so offline callers can run the CTE. SQLite's
    :meth:`sqlite3.Connection.create_function` overwrites a
    previously-registered function of the same name and arity, so the
    helper is idempotent — ``apply`` and ``apply-projection`` can both
    call it on the same engine without coordination.

    No-op when the engine is not a SQLite engine: the listener
    registration would never fire on Postgres / MySQL because the
    ``connect`` event never lands on a ``sqlite3.Connection``.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _register(dbapi_connection: object, _: object) -> None:
        # mypy cannot narrow ``dbapi_connection`` to ``sqlite3.Connection``
        # because the ``connect`` event fires for every backend; the
        # listener is only attached to SQLite engines so the runtime
        # type is always ``sqlite3.Connection``.
        conn: sqlite3.Connection = dbapi_connection  # type: ignore[assignment]
        conn.create_function("taxonomy_display_level", 1, display_level)


__all__ = [
    "PROJECTION_TABLES",
    "REBUILD_BUDGET_SECONDS",
    "register_display_level",
]