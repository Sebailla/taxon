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
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import Engine, event, func, select, text
from sqlalchemy.orm import Session

from taxon.api.tree import SPECIES_COUNT_LAZY_NULL_THRESHOLD, SPECIES_DISPLAY_LEVEL
from taxon.schema import Taxon, TaxonDescendantCount
from taxon.taxonomy import display_level

_logger = logging.getLogger(__name__)

#: Per-request rebuild budget. A materialisation that exceeds this
#: threshold returns ``None`` so the read path falls back to lazy-null
#: — the projection is an optimisation, not a guarantee. ``15s`` is
#: the empirical wall-clock cost of a full recursive CTE walk on a
#: CoL subtree (Eukaryota with 5.6M descendants finishes inside the
#: budget; larger subtrees that cannot finish in 15s still return
#: ``None`` and the projection stays empty for that parent). The
#: first request for a previously-unmaterialised parent pays the
#: rebuild latency inline; subsequent requests return from the cache
#: in O(1). Offline callers (``apply-projection``, ``import_data``)
#: pass ``budget_seconds=None`` to disable the guard.
REBUILD_BUDGET_SECONDS: float = 15.0

#: Table names owned by this module. Mirrors
#: :data:`taxon.api.workspace.WORKSPACE_TABLES` so ``python -m taxon.migrate apply``
#: and the import-data hook can discover every table this change
#: introduces without the migrate CLI learning about each new one
#: individually.
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


def _table_exists(session: Session) -> bool:
    """Return ``True`` iff the projection table is present in the engine.

    The projection is additive: a legacy DB never gets the table
    unless ``python -m taxon.migrate apply`` (or the FastAPI lifespan)
    creates it. Lookup helpers treat "table absent" and "table present,
    row absent" the same — both fall through to the pre-change path —
    so callers do not need to branch on the table's presence.
    """
    rows = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='taxon_descendant_counts'")
    ).all()
    return bool(rows)


def _projected_parent_ids(session: Session, threshold: int) -> list[int]:
    """Return ids whose direct-children count exceeds ``threshold``.

    ``SELECT parent_id FROM taxa WHERE parent_id IS NOT NULL
       GROUP BY parent_id HAVING count(*) > :threshold``
    """
    stmt = (
        select(Taxon.parent_id)
        .where(Taxon.parent_id.is_not(None))
        .group_by(Taxon.parent_id)
        .having(func.count() > threshold)
    )
    return [int(row[0]) for row in session.execute(stmt).all()]


def lookup_one(session: Session, taxon_id: int) -> int | None:
    """Return the cached ``species_count`` for ``taxon_id`` or ``None`` on a miss.

    Returns ``None`` both when the row is absent AND when the table
    itself is absent (legacy DB). The caller cannot distinguish, and
    does not need to: both fall through to the pre-change path.
    """
    if not _table_exists(session):
        return None
    stmt = select(TaxonDescendantCount.species_count).where(
        TaxonDescendantCount.taxon_id == taxon_id
    )
    return session.execute(stmt).scalar_one_or_none()


def lookup_many(session: Session, taxon_ids: Iterable[int]) -> dict[int, int]:
    """Return ``{taxon_id: species_count}`` for the cached subset.

    Absent ids are simply missing from the dict. One ``IN``-list
    SELECT; empty input returns ``{}`` without a round trip.
    """
    ids = list(taxon_ids)
    if not ids:
        return {}
    if not _table_exists(session):
        return {}
    stmt = select(TaxonDescendantCount.taxon_id, TaxonDescendantCount.species_count).where(
        TaxonDescendantCount.taxon_id.in_(ids)
    )
    return {int(tid): int(count) for tid, count in session.execute(stmt).all()}


def materialize_for_parent(
    session: Session,
    parent_id: int,
    *,
    budget_seconds: float | None = REBUILD_BUDGET_SECONDS,
) -> int | None:
    """Rebuild and persist the row for ``parent_id``; return ``species_count``.

    Runs the same recursive CTE as
    :func:`taxon.api.tree._count_descendant_species`, measures the
    elapsed wall-clock, and commits the row only when the walk finished
    within ``budget_seconds``. Over budget → no row written, returns
    ``None`` (the pre-change answer).

    ``budget_seconds=None`` disables the SLO guard — used by offline
    callers (``apply-projection``, ``import_data``) that MUST complete
    the population regardless of cost.

    Idempotent: an existing row is overwritten in place (upsert on the
    primary key), so re-running never duplicates or accumulates rows.
    """
    started = perf_counter()
    sql = text(
        """
        WITH RECURSIVE descendants(id) AS (
            SELECT id FROM taxa WHERE parent_id = :parent_id
            UNION ALL
            SELECT t.id FROM taxa t
            JOIN descendants d ON t.parent_id = d.id
        )
        SELECT
            SUM(CASE WHEN LOWER(taxonomy_display_level(
                (SELECT rank FROM taxa WHERE id = descendants.id)
            )) = :species_level THEN 1 ELSE 0 END) AS species_count,
            COUNT(*) AS total_count
          FROM descendants
        """
    )
    result = session.execute(
        sql, {"parent_id": parent_id, "species_level": SPECIES_DISPLAY_LEVEL}
    ).one()
    elapsed = perf_counter() - started
    species_count = int(result.species_count or 0)
    total_count = int(result.total_count or 0)

    if budget_seconds is not None and elapsed > budget_seconds:
        _logger.info(
            "materialize_for_parent(%s) over budget: %.3fs > %.3fs; skipping write",
            parent_id,
            elapsed,
            budget_seconds,
        )
        return None

    # Upsert by PK: keep the existing row if any, otherwise insert.
    existing = session.get(TaxonDescendantCount, parent_id)
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    if existing is None:
        session.add(
            TaxonDescendantCount(
                taxon_id=parent_id,
                species_count=species_count,
                total_count=total_count,
                computed_at=now_iso,
            )
        )
    else:
        existing.species_count = species_count
        existing.total_count = total_count
        existing.computed_at = now_iso
    session.flush()
    return species_count


def materialize_all(
    session: Session,
    threshold: int = SPECIES_COUNT_LAZY_NULL_THRESHOLD,
    *,
    budget_seconds: float | None = None,
) -> int:
    """Rebuild every threshold-exceeding parent; return rows written.

    Iterates :func:`_projected_parent_ids` and calls
    :func:`materialize_for_parent` per parent. ``budget_seconds=None``
    (the default for offline callers — ``migrate apply-projection`` and
    ``import_data``) disables the SLO guard: those callers are not
    serving a request and MUST complete the population.
    """
    parents = _projected_parent_ids(session, threshold)
    written = 0
    for parent_id in parents:
        if materialize_for_parent(session, parent_id, budget_seconds=budget_seconds) is not None:
            written += 1
    return written


__all__ = [
    "PROJECTION_TABLES",
    "REBUILD_BUDGET_SECONDS",
    "lookup_many",
    "lookup_one",
    "materialize_all",
    "materialize_for_parent",
    "register_display_level",
]
