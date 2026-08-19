# Tasks: descendant-counts-projection

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~845 total (production ~340 + tests ~505; Spanish mirrors excluded from budget) |
| 400-line budget risk | Medium (PR #2 ~440 LOC is borderline; work-unit commits per `work-unit-commits` keeps each child commit ≤ 400 LOC) |
| Chained PRs recommended | Yes |
| Suggested split | PR #1 → PR #2 → PR #3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Schema + ORM + `PROJECTION_TABLES` widening + `apply-projection` CLI + `register_display_level` | PR #1 | `pytest taxon/tests/test_migrate.py taxon/tests/test_descendant_counts_projection.py::test_apply_creates_taxon_descendant_counts_table taxon/tests/test_descendant_counts_projection.py::test_apply_projection_runs_the_cte_on_a_bare_engine -v` | `python -m taxon.migrate apply --database-url sqlite:///$TMP/col.db` → exits 0, `taxon_descendant_counts` exists; `python -m taxon.migrate apply-projection` → exits 0 on empty DB | Remove `taxon/api/projections.py` (no consumers yet), revert `taxon/schema.py`, revert `taxon/migrate.py`, drop `taxon_descendant_counts` table. API read path untouched — pre-change behaviour preserved. |
| 2 | Materialisation engine (`projections.py`): rebuild + lookup + SLO guard | PR #2 | `pytest taxon/tests/test_descendant_counts_projection.py -v` (excluding the bare-engine test from PR #1) | N/A (pure SQLAlchemy helpers, exercised via TestClient in PR #3) | Revert `taxon/api/projections.py` + tests; PR #1's CLI surface still works against an empty projection. |
| 3 | API integration + `import_data` rebuild | PR #3 | `pytest taxon/tests/ -v` (all green); `pytest taxon/tests/test_species_count_lazy_null.py -v` (unchanged, regression guard) | `uvicorn taxon.api:create_app --reload` + `curl "/api/tree/children?parent_id={animalia_id}"` → `species_count` is non-null integer after first request; `python -m taxon.import_data` on `data/taxon.db` rebuilds the projection | Revert `taxon/api/tree.py` + `taxon/api/_tree_tiers.py` + `taxon/import_data.py`; PR #1's CLI remains the only writer to the table. |

## Phase 1 — PR #1: Foundation (schema + ORM + CLI surface) (~270 LOC)

**Worktree**: `../taxon-worktrees/descendant-counts-projection-pr1`.
**Branch**: `feat/descendant-counts-projection-pr1`.
**Base / Target**: `develop` per AGENTS.md §4.
**Depends on**: nothing.
**Strict TDD**: every work unit below starts with a RED test (commit RED → GREEN → refactor).

### 1. Add the `TaxonDescendantCount` ORM class to `taxon/schema.py`

**Files**: `taxon/schema.py`, `taxon/tests/test_schema.py`.
**Acceptance**:
- [x] `TaxonDescendantCount` class exists on `Base.metadata` with `__tablename__ = "taxon_descendant_counts"`.
- [x] Four columns: `taxon_id` (PK, FK to `taxa.id`), `species_count` (INT, NOT NULL), `total_count` (INT, NOT NULL), `computed_at` (String, NOT NULL).
- [x] `computed_at` default is `lambda: datetime.now(UTC).isoformat(timespec="seconds")` (ISO-8601 string — SQLite has no TIMESTAMP, matches `SpeciesExplored.explored_at`).
- [x] No secondary index: `taxon_id` is the PK (rowid B-tree); every access is a point lookup or `IN`-list over PKs.
**Tests**: `taxon/tests/test_schema.py` — RED-first: `test_taxon_descendant_count_table_exists_with_four_columns`, `test_taxon_descendant_count_pk_is_taxon_id`, `test_taxon_descendant_count_computed_at_default_is_iso8601_string`. `pytest taxon/tests/test_schema.py -v`.
**Notes**:
- Conventional commit: `feat(schema): add TaxonDescendantCount for cached descendant counts`.
- Place the class directly after `SpeciesPath` (line 56) so the lifecycle neighbour is right; the projection is FK'd to `taxa.id` and is invalidated by a re-import — same lifecycle as `SpeciesPath`, NOT as the workspace models.
- Import `datetime, UTC` from `datetime` (not `from datetime import datetime, UTC` if the module doesn't already do so — check existing imports first to avoid duplication).
- **Sequential**: no parallel writers; this commit must land before any consumer of the class exists.

### 2. Add `PROJECTION_TABLES` constant + bare-engine `register_display_level` helper

**Files**: `taxon/api/projections.py` (new module — empty skeleton), `taxon/api/workspace.py` (NOT modified).
**Acceptance**:
- [ ] `taxon/api/projections.py` exists with a single exported constant `PROJECTION_TABLES: tuple[str, ...] = ("taxon_descendant_counts",)`.
- [ ] `PROJECTION_TABLES` is importable as `from taxon.api.projections import PROJECTION_TABLES`.
- [ ] A stub `register_display_level(engine: Engine) -> None` is exported. It attaches the SQLite user function `taxonomy_display_level(rank)` to every new connection via `@event.listens_for(engine, "connect")`, mirroring the FastAPI factory's listener at `taxon/api/__init__.py:92-95`. Body delegates to `taxon.taxonomy.display_level`.
- [ ] Importing the module has no side effects (no engine creation, no DB I/O).
**Tests**: RED-first in a new `taxon/tests/test_descendant_counts_projection.py` (full file at PR #2 — for this commit, only the bare-engine registration test exists as `test_register_display_level_attaches_function_to_bare_engine` — see task 6).
**Notes**:
- Conventional commit: `feat(projections): add PROJECTION_TABLES tuple + register_display_level helper`.
- The module is `projections.py` (public), NOT `_projection.py` as the proposal named it — ADR-1 in `design.md:43-49`. `migrate.py` and `import_data.py` import from outside `taxon/api/`, so the underscore-private convention used by `_tree_tiers.py` does not fit.
- The helper is called from `taxon/migrate.py` and `taxon/import_data.py` in PR #1 task 3 and PR #3 respectively. Without it, both bare engines raise `sqlite3.OperationalError: no such function: taxonomy_display_level` when `materialize_all` runs — the design names this as the highest-risk integration point (`design.md:365-403`).
- Do NOT add `lookup_one`, `lookup_many`, `materialize_*` here yet — those land in PR #2.
- **Sequential**: this commit lands before PR #1 task 3 (CLI) so the helper is available.

### 3. Widen `_run_apply` to include `PROJECTION_TABLES` + register `taxonomy_display_level` on the CLI engine

**Files**: `taxon/migrate.py`, `taxon/tests/test_migrate.py`.
**Acceptance**:
- [ ] `taxon/migrate.py::main` passes `WORKSPACE_TABLES + PROJECTION_TABLES` to `_run_apply` (so plain `apply` creates `taxon_descendant_counts` alongside the three workspace tables).
- [ ] `WORKSPACE_TABLES` itself is UNCHANGED — its docstring pins its meaning to the three re-import-surviving workspace tables (`taxon/api/workspace.py:43-50`); we widen the apply call site, NOT the constant.
- [ ] The CLI engine at `taxon/migrate.py:233` calls `register_display_level(engine)` after `create_engine(...)` so the recursive CTE works out-of-band.
- [ ] The CLI does NOT yet gain an `apply-projection` subcommand — that lands in task 5.
**Tests**: `taxon/tests/test_migrate.py` — RED-first update: `test_apply_creates_three_new_tables` is renamed to `test_apply_creates_all_migrated_tables` and now also asserts `taxon_descendant_counts` in the result set; add `test_apply_creates_taxon_descendant_counts_on_fresh_db` (single-table pin, the spec's `Fresh DB gains the table on apply` scenario). `pytest taxon/tests/test_migrate.py -v`.
**Notes**:
- Conventional commit: `feat(migrate): include PROJECTION_TABLES in apply + register display_level on CLI engine`.
- The `_run_apply` interface (`taxon/migrate.py:158`) does NOT change — the only widening is at the call site in `main`. This keeps the helper reusable and testable.
- `register_display_level(engine)` is idempotent (SQLite allows re-registering the same function name), so calling it twice on the same engine (once here, once if PR #1 task 5 also wires it) is safe — but PR #1 task 5 will NOT re-register; only one of the two callers should register.
- The `register_display_level` call is the bare-engine fix that prevents `OperationalError: no such function: taxonomy_display_level` when CLI callers reach PR #2's CTE work.
- **Sequential**: must land before PR #1 task 4 (CLI subcommand) because the subcommand runs the same engine.

### 4. RED-first test for the `apply-projection` subcommand

**Files**: `taxon/tests/test_migrate.py`.
**Acceptance**:
- [ ] `test_apply_projection_exits_zero_on_empty_db` — RED: `python -m taxon.migrate apply-projection --database-url sqlite:///...` against an empty DB exits non-zero (currently the subcommand does not exist → argparse error → non-zero exit). Test pins the contract.
- [ ] `test_apply_projection_respects_threshold_flag` — RED: pass `--threshold=1` against a populated DB; argparse should accept the flag. Currently fails because the flag is unrecognised.
- [ ] `test_apply_projection_is_idempotent_via_cli` — RED: invoking twice exits zero both times. Fails because the subcommand does not exist.
**Tests**: All three are RED at this commit. `pytest taxon/tests/test_migrate.py -v` shows them failing with the expected argparse / exit-code errors.
**Notes**:
- Conventional commit: `test(migrate): pin apply-projection CLI contract (RED)`.
- These tests use the same `subprocess` + `tmp_path` harness as the existing `test_migrate.py` (see `_run` + `env_with_pythonpath` fixtures, lines 66-93).
- Strict TDD: this commit MUST be its own commit (RED only) so the GREEN commit in task 5 has a clear diff.

### 5. Add the `apply-projection` subparser to `taxon/migrate.py`

**Files**: `taxon/migrate.py`, `taxon/tests/test_migrate.py`.
**Acceptance**:
- [ ] `python -m taxon.migrate apply-projection --database-url sqlite:///...` exits 0 on a populated DB and on an empty DB.
- [ ] The subparser accepts `--threshold INT` (default `SPECIES_COUNT_LAZY_NULL_THRESHOLD`); the value narrows the population (only parents whose `direct_children_count` exceeds the value get rows).
- [ ] The subparser accepts `--budget-seconds FLOAT` (default `None` — disables the SLO guard for offline callers; see ADR-2 in `design.md:60-82`).
- [ ] The three RED tests from task 4 now pass GREEN.
- [ ] The subcommand calls `register_display_level(engine)` (idempotent re-registration is acceptable; only one of the three callers actually needs the call — keep the call site explicit for clarity).
**Tests**: `taxon/tests/test_migrate.py` — the three RED tests from task 4 now pass. Also add `test_apply_projection_creates_taxa_table_on_empty_db_for_cte` to confirm the subcommand can run an in-memory CTE against the freshly-created `taxa` table (no data — just exercises the SQL plumbing).
**Notes**:
- Conventional commit: `feat(migrate): add apply-projection subcommand + --threshold/--budget-seconds flags`.
- Implementation skeleton: `apply-projection` calls `materialize_all` from `taxon/api/projections.py`. PR #1 ships a stub `materialize_all(session, threshold, budget_seconds=None) -> int` that returns `0` (no rows written). The full implementation lands in PR #2 — PR #1 only needs the CLI wiring to be honest about the contract.
- Subparser position: between `dry-run` and `apply` is fine, or after `apply` — argparse does not care. Match the existing order (dry-run → apply → apply-projection) so the help listing is predictable.
- **Sequential**: task 5 ships after task 4 (RED-first). PR #1 closes when tasks 1+2+3+4+5 land as 5 commits.

### 6. Bare-engine registration test (catches the `taxonomy_display_level` gap)

**Files**: `taxon/tests/test_descendant_counts_projection.py` (new file).
**Acceptance**:
- [ ] `test_register_display_level_attaches_function_to_bare_engine` — create a bare `create_engine("sqlite:///:memory:")` (NO listener), then call `register_display_level(engine)`. Open a connection and run `SELECT taxonomy_display_level('species')` — must return `"species"`.
- [ ] `test_register_display_level_is_idempotent` — calling `register_display_level(engine)` twice on the same engine does not raise.
- [ ] `test_register_display_level_fails_on_unregistered_engine` — a bare engine without the registration throws `OperationalError: no such function: taxonomy_display_level` when the CTE is run. Pins the gap.
**Tests**: All three are the seed of the new test file. `pytest taxon/tests/test_descendant_counts_projection.py -v`.
**Notes**:
- Conventional commit: `test(projections): pin register_display_level on bare engine`.
- This is the test that `design.md:402-403` explicitly names as the safety net for the `taxonomy_display_level` registration gap. It is the highest-risk integration point in the change — invisible to API-engine unit tests, only surfaces when CLI runs.
- RED-first: the helper does not exist yet (task 2 ships it), so task 6 must commit AFTER task 2. Order: 1 → 2 → 6 → 3 → 4 → 5.

PR #1 closes with 6 work-unit commits (1 + 2 + 6 + 3 + 4 + 5), ~270 LOC total. The PR body should mention the `register_display_level` gap is now closed and that the CLI subcommand is wired but a no-op until PR #2.

## Phase 2 — PR #2: Materialisation engine (`projections.py`) (~440 LOC, borderline)

**Worktree**: `../taxon-worktrees/descendant-counts-projection-pr2`.
**Branch**: `feat/descendant-counts-projection-pr2`.
**Base / Target**: `develop` (after PR #1 merges).
**Depends on**: PR #1 merged (so the schema + CLI scaffolding exist).

### 7. RED-first lookup helpers (`lookup_one`, `lookup_many`, `_table_exists`)

**Files**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] `lookup_one(session, taxon_id) -> int | None` returns the cached `species_count` or `None` on a miss.
- [ ] `lookup_one` catches `OperationalError: no such table: taxon_descendant_counts` and returns `None` — the legacy-DB scenario (spec §Schema Adds Without Touching Legacy Databases).
- [ ] `lookup_many(session, taxon_ids) -> dict[int, int]` runs ONE `IN`-list `SELECT`; absent ids are simply missing from the dict; empty input returns `{}` without a round trip.
- [ ] `_table_exists(session, name) -> bool` returns `False` for a missing table (used by the read path on legacy DBs).
- [ ] No session mutation — both helpers are pure reads.
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_lookup_one_returns_none_when_table_absent` (legacy DB — use a fresh in-memory engine without `create_all`).
- `test_lookup_one_returns_cached_value_after_write` (write a row, look it up).
- `test_lookup_many_returns_empty_dict_for_empty_input` (no DB round trip — assert by patching `session.execute`).
- `test_lookup_many_excludes_missing_ids` (mix of present + absent).
- `test_table_exists_returns_false_for_missing_table` (legacy DB).
**Notes**:
- Conventional commit: `feat(projections): add lookup_one + lookup_many read helpers (RED-first)`.
- `lookup_one` is the FIRST integration point in the read path — `tree.py` will call it before the threshold guard in PR #3. The signature must be final at this commit because PR #3's tree.py diff depends on it.
- Use `text("SELECT taxon_id, species_count FROM taxon_descendant_counts WHERE taxon_id = :pid")` — never interpolate the id.
- **Sequential**: no parallel writers. PR #3 will only land after this PR merges.

### 8. RED-first `_projected_parent_ids` (population predicate)

**Files**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] `_projected_parent_ids(session, threshold) -> list[int]` returns every taxon id whose `direct_children_count` exceeds `threshold`.
- [ ] Threshold constant is imported from `taxon.api.tree.SPECIES_COUNT_LAZY_NULL_THRESHOLD` — single source of truth (spec §Population Rule).
- [ ] Empty result returns `[]` (no error).
- [ ] The query is `SELECT parent_id FROM taxa WHERE parent_id IS NOT NULL GROUP BY parent_id HAVING count(*) > :threshold` — bound parameter, never interpolated.
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_projected_parent_ids_returns_only_above_threshold` (build a fixture with 3 parents: 5 children, 100 children, 1000 children; with threshold=50 → only the last one).
- `test_projected_parent_ids_skips_root_with_null_parent_id` (a root taxon whose `parent_id IS NULL` is never a "parent" for this projection).
- `test_projected_parent_ids_uses_spec_constant` (monkeypatch `SPECIES_COUNT_LAZY_NULL_THRESHOLD = 50`, confirm the query reads it).
**Notes**:
- Conventional commit: `feat(projections): add _projected_parent_ids population predicate`.
- The query must NOT use `SELECT COUNT(*) FROM taxa WHERE parent_id = :pid` in a loop — that would be N+1. The grouped `HAVING` query is the single-round-trip form.
- This helper is shared by `materialize_all` (PR #2 task 10) and may be reused by `import_data` (PR #3 task 13).

### 9. RED-first `materialize_for_parent` + SLO budget guard

**Files**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] `materialize_for_parent(session, parent_id, *, budget_seconds=REBUILD_BUDGET_SECONDS) -> int | None` rebuilds the row for `parent_id` and returns `species_count`.
- [ ] Uses `time.perf_counter()` to measure the CTE walk elapsed time (ADR-2: measure, don't predict).
- [ ] Under budget (`elapsed <= budget_seconds`): INSERT the row, `session.commit()`, return `species_count`.
- [ ] Over budget: `session.rollback()`, NO row written, return `None` — the pre-change answer.
- [ ] Idempotent: re-running on an existing row upserts on the PK (no duplicate, no accumulation).
- [ ] `REBUILD_BUDGET_SECONDS: Final[float] = 1.0` — matches the `/api/tree/children` 1s SLO documented at `taxon/api/tree.py:67-69`.
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_rebuild_under_budget_writes_row` (small fixture, default budget → row exists after the call; `computed_at` is recent).
- `test_rebuild_over_budget_skips_write_and_returns_none` (inject `budget_seconds=0.0` to force the over-budget branch deterministically — no sleeps, no flaky timing. Assert `None` returned AND no row in the table).
- `test_rebuild_is_idempotent_on_existing_row` (call twice; row count = 1; values may differ if fixture changes but count is constant).
- `test_rebuild_sets_computed_at_iso8601_string` (assert format `datetime.now(UTC).isoformat(timespec="seconds")`).
**Notes**:
- Conventional commit: `feat(projections): add materialize_for_parent with measured SLO budget`.
- The over-budget test (`budget_seconds=0.0`) is the design's deterministic fallback — `design.md:412` pins this as the test approach (no flaky timing).
- The CTE text mirrors `tree.py:212-227` byte-for-byte so both paths walk the same shape. The recursion depth and the `taxonomy_display_level` lookup match.
- **Sequential**: PR #3 (tree.py integration) consumes `materialize_for_parent` via `_count_descendant_species` after this PR lands.

### 10. RED-first `materialize_all` (batch population)

**Files**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] `materialize_all(session, threshold=SPECIES_COUNT_LAZY_NULL_THRESHOLD, *, budget_seconds=None) -> int` rebuilds every row for every projected parent and returns the number of rows written.
- [ ] Iterates `_projected_parent_ids(session, threshold)` and calls `materialize_for_parent` per parent.
- [ ] `budget_seconds=None` (the default) DISABLES the SLO guard for offline callers — `apply-projection` and `import_data` are not serving a request and must complete the population (spec §Rebuild Bounded by the Per-Request SLO is scoped to the tree endpoint).
- [ ] The whole batch runs in one transaction (single `session.commit()` at the end) so a partial failure rolls back.
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_materialize_all_populates_only_above_threshold_parents` (3 parents — 5, 100, 1000 children; threshold=50 → 1 row written, returns 1).
- `test_materialize_all_is_idempotent` (call twice; row count unchanged, values for `species_count` + `total_count` do not change).
- `test_materialize_all_disables_slo_guard_by_default` (pass a fixture large enough that the default budget would skip it; `budget_seconds=None` → row written anyway).
- `test_materialize_all_returns_zero_on_empty_database` (no projected parents → returns 0, no error).
**Notes**:
- Conventional commit: `feat(projections): add materialize_all batch population`.
- The `budget_seconds=None` escape is the ONE asymmetry the design explicitly calls out at `design.md:282-287` — request path is bounded, offline path is unbounded.
- PR #1 task 5's `apply-projection` stub returned `0`; PR #2 task 10 replaces the stub with the real implementation. After this commit, PR #1's CLI subcommand populates real rows.
- The PR #2 PR body should mention this is the FIRST real writer — PR #1 ships a CLI that says "0 rows" until this lands.

### 11. PR #2 closure: extend `_table_exists` to cover the legacy-DB read path

**Files**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] The three CLI tests from PR #1 task 4 (`test_apply_projection_exits_zero_on_empty_db`, `test_apply_projection_respects_threshold_flag`, `test_apply_projection_is_idempotent_via_cli`) now exit zero AND populate rows (when threshold is hit) via the real `materialize_all`.
- [ ] `test_apply_projection_runs_the_cte_on_a_bare_engine` (the bare-engine test from PR #1 task 6) now exercises `materialize_all` end-to-end against a bare CLI engine — confirms the `taxonomy_display_level` registration gap is closed.
- [ ] `pytest taxon/tests/test_migrate.py taxon/tests/test_descendant_counts_projection.py -v` → all green.
- [ ] `pytest taxon/tests/test_species_count_lazy_null.py -v` → unchanged, still green (no regression in the pre-change path).
**Tests**: All RED tests from tasks 7-10 now pass GREEN. The two CLI tests that were stubbed in PR #1 (task 5) now exercise the real implementation.
**Notes**:
- Conventional commit: `feat(projections): wire materialize_all into apply-projection CLI`.
- This commit replaces the `materialize_all` stub shipped in PR #1 task 5 with the real implementation. The diff is small (~10 LOC) but the semantic change is large: rows are now persisted on every `apply-projection` run.
- After PR #2, `taxon_descendant_counts` has rows for every threshold-exceeding parent in the DB. The UI change (Animalia stops being `?`) lands in PR #3.
- PR #2 closes with ~440 LOC (180 module + 260 tests). Borderline over the 400-line budget — commit split per `work-unit-commits` keeps each child commit ≤ 400 LOC.

## Phase 3 — PR #3: API integration + `import_data` rebuild (~135 LOC)

**Worktree**: `../taxon-worktrees/descendant-counts-projection-pr3`.
**Branch**: `feat/descendant-counts-projection-pr3`.
**Base / Target**: `develop` (after PR #2 merges).
**Depends on**: PR #2 merged (so `projections.py` has the real `materialize_*` helpers).

### 12. Wire `lookup_one` pre-check + rebuild hooks into `_count_descendant_species`

**Files**: `taxon/api/tree.py`, `taxon/tests/test_api_router_tree.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] `_count_descendant_species` consults `lookup_one(session, parent_id)` immediately after the `_cache` request-scoped short-circuit (after line 190 of `tree.py`), BEFORE the `direct_count > threshold` guard (line 198).
- [ ] Cache hit: return `cached` directly, populate `_cache[parent_id]` for the request scope, skip the threshold guard AND the CTE.
- [ ] Cache miss: fall through to existing threshold + CTE path unchanged. If the threshold branch fires, call `materialize_for_parent(session, parent_id)` and return its result (`None` when over budget, `int` when under).
- [ ] The second threshold guard at `tree.py:236-239` (total_count > threshold) gets the same treatment — instead of re-walking, the helper writes the already-known `(species_count, total_count)` through a small `_persist_cached_count(session, parent_id, species_count, total_count, elapsed) -> None` that honours the same SLO budget.
- [ ] Regression: `pytest taxon/tests/test_species_count_lazy_null.py -v` → unchanged, still green.
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_cache_hit_returns_without_running_cte` (pre-insert a row in `taxon_descendant_counts`; monkeypatch `session.execute` to count CTE invocations; assert zero).
- `test_cache_hit_skips_threshold_guard` (parent whose `direct_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` but has a cached row → returns the cached value, no `None`).
- `test_first_read_materializes_row_and_sets_computed_at` (no cached row → call → assert `species_count` returned AND a row exists AND `computed_at` is recent).
- `test_cache_miss_below_threshold_uses_existing_cte_path` (no cached row, parent below threshold → existing CTE path runs unchanged, NO row written — only threshold-exceeding parents get cached).
- `test_rebuild_total_count_guard_writes_row_when_under_budget` (parent whose direct-children count is below threshold but whose recursive subtree is above threshold → second guard fires → `_persist_cached_count` writes the row).
**Notes**:
- Conventional commit: `feat(tree): consult projection cache before threshold guard`.
- `_persist_cached_count` lives in `taxon/api/projections.py` (a small writer helper, ~12 LOC). It is co-located with `materialize_for_parent` because both share the SLO measurement discipline.
- The `_cache` request-scoped dict at `tree.py:189-190` is preserved unchanged (it is cheaper than a DB query).
- **Sequential**: this commit lands before task 13 (batch integration) because the per-row helper is the simpler integration; the batch integration tests build on the same `_persist_cached_count` path.

### 13. Wire `lookup_many` pre-load into `_batch_species_counts`

**Files**: `taxon/api/_tree_tiers.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Acceptance**:
- [ ] `_batch_species_counts` calls `lookup_many(session, parent_ids)` immediately after the `direct_counts` read at `_tree_tiers.py:446`.
- [ ] Cached ids are written into `result` and EXCLUDED from `eligible` so they contribute no seed row to the recursive CTE.
- [ ] The CTE text at `_tree_tiers.py:467-485` is byte-identical to the pre-change version (no SQL rewrite, no new join).
- [ ] The aggregation loop at lines 486-487 only writes into ids that were seeded — structurally enforcing "cached stale row wins over CTE".
- [ ] Regression: the batch tier tests in `taxon/tests/test_api_router_tree.py` stay green unchanged.
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_batch_merges_cached_and_cte_counts` (mixed batch: 1 cached + 3 sub-threshold → result carries cached value for the cached id + CTE value for the others).
- `test_batch_excludes_cached_ids_from_cte_seed` (capture the generated seed SQL; assert cached id is absent from `UNION ALL`).
- `test_batch_returns_all_cached_when_threshold_exceeded_for_none` (all parents in batch have cached rows; CTE never runs; `eligible` is empty; returns early per `tree_tiers.py:457-458`).
- `test_batch_cached_stale_row_wins_over_cte` (cached row exists with value X; CTE would resolve to value Y; result carries X).
**Notes**:
- Conventional commit: `feat(tree-tiers): pre-load cached rows in batch species counts`.
- The change is ~15 LOC net (one new query, a small loop tweak). The CTE text is unchanged — `design.md:131-138` pins this constraint.
- **Sequential**: this commit can land in parallel with task 12 in the SAME PR (#3) but MUST be a separate commit so review focus is per-file.

### 14. Add `register_display_level` + post-import `materialize_all` in `taxon/import_data.py`

**Files**: `taxon/import_data.py`, `taxon/tests/test_import.py` (or `test_descendant_counts_projection.py`).
**Acceptance**:
- [ ] `_sqlite_engine` (line 75) calls `register_display_level(engine)` BEFORE the existing `enable_foreign_keys` listener so the function is registered on every new connection.
- [ ] `import_dataset` calls `materialize_all` after `_populate_species_paths(engine)` (line 71) and BEFORE the `return counts` (line 72). The call uses a fresh `Session(engine)` so the offline batch path is independent of any caller-held session.
- [ ] A small fixture (`test_rebuild_after_import_dataset_populates_threshold_parents`) builds a dataset where one parent exceeds the threshold; after `import_dataset` returns, the row is present with a fresh `computed_at`.
- [ ] Regression: `pytest taxon/tests/test_import.py -v` → unchanged green (the existing tests do not assert on `taxon_descendant_counts`).
**Tests**: RED-first in `taxon/tests/test_descendant_counts_projection.py`:
- `test_import_dataset_triggers_rebuild` (synthetic fixture, threshold-exceeding parent → row present after the call).
- `test_import_dataset_rebuild_is_idempotent` (call `import_dataset` twice on the same source; row count + values unchanged).
- `test_import_dataset_rebuild_does_not_drop_rows_after_drop_all` (`import_dataset` calls `drop_all` then `create_all` → the projection table is recreated empty; post-import population is fresh, not stale).
**Notes**:
- Conventional commit: `feat(import_data): rebuild projection after CoL re-import`.
- The `register_display_level` call here is the SECOND registration site (PR #1 task 3 registers on the CLI engine; PR #3 task 14 registers on the import engine). Re-registration is idempotent — SQLite allows `create_function` to overwrite without raising.
- `import_dataset` drops + creates ALL tables (`import_data.py:46-47`), so the projection table is fresh on every import — there is no stale-row window (design §Migration / Rollout).
- The post-import `materialize_all` call uses `budget_seconds=None` (the default) so the SLO guard is disabled — imports are offline batch callers.

### 15. Update the legacy `Out of Scope` line in `taxonomic-tree-browse/spec.md`

**Files**: `openspec/specs/taxonomic-tree-browse/spec.md`.
**Acceptance**:
- [ ] The line `species_count materialization at deep nodes` is removed from the `Out of Scope` section (the line exists at the bottom of the file; check with `rg "species_count materialization" openspec/specs/`).
- [ ] The delta spec at `openspec/changes/descendant-counts-projection/specs/taxonomic-tree-browse/spec.md` already records the superseded requirement — no edit to the delta spec needed.
- [ ] `git diff openspec/specs/taxonomic-tree-browse/spec.md` shows only the deletion.
**Tests**: None — doc-only.
**Notes**:
- Conventional commit: `docs(specs): prune superseded Out-of-Scope line for projection`.
- Tracked as its own task so it is not forgotten at archive time (design §Risks Carried From The Spec names this risk).
- This commit ships INSIDE PR #3 (or as a docs-only follow-up PR — orchestrator decides).

### 16. PR #3 closure + verify no regression

**Files**: `taxon/tests/test_species_count_lazy_null.py` (no edits — guard).
**Acceptance**:
- [ ] `pytest taxon/tests/ -v` → all green on `develop`.
- [ ] `pytest taxon/tests/test_species_count_lazy_null.py -v` → unchanged green (regression guard for the pre-change behaviour).
- [ ] `mypy taxon/` → zero errors.
- [ ] `ruff check taxon/` → zero errors.
- [ ] Runtime harness: `uvicorn taxon.api:create_app --reload` against `data/col.db`; `curl "/api/tree/children?parent_id={animalia_id}"` → `species_count` is a non-null integer (was `null` pre-change). Second call → identical value, no CTE log line.
- [ ] Runtime harness: `python -m taxon.import_data` on `data/taxon.db` rebuilds the projection; subsequent `apply-projection` is a no-op (row count unchanged).
**Tests**: The harness commands above.
**Notes**:
- Conventional commit: `test(tree): verify species_count cache integration (regression guard)`.
- This is the final PR #3 commit. After this lands, the UI change is observable and `Animalia` no longer renders `?` forever.

PR #3 closes with 5 commits (12 + 13 + 14 + 15 + 16), ~135 LOC total. Well under the 400-line cap.

## Phase 4 — Post-merge

### 17. `learn-es` entry (after PR #3 green on `develop`)

- [ ] 17.1 Write `/learn-es/2026-08-19-descendant-counts-projection.md` per AGENTS.md §2 structure (What / How / Where / Why / How it works / Workflows) in neutral/professional Spanish. Trigger: PR #3 merges green to `develop`.
- [ ] 17.2 Conventional commit: `docs(learn-es): entry for descendant-counts-projection change`.

## Critical Path

1. **PR #1** (6 commits, ~270 LOC) — schema + ORM + `register_display_level` + `apply-projection` CLI scaffold + bare-engine test. First PR in the chain.
2. **PR #2** (5 commits, ~440 LOC, borderline) — `projections.py` module: `lookup_one`, `lookup_many`, `_projected_parent_ids`, `materialize_for_parent`, `materialize_all`, SLO budget guard. Requires PR #1 on `develop`.
3. **PR #3** (5 commits, ~135 LOC) — `tree.py` cache pre-check + `_tree_tiers.py` batch pre-load + `import_data` rebuild + `Out of Scope` prune + regression harness. Requires PR #2 on `develop`.

## Conventions Reference

- Conventional commits per `AGENTS.md §3`; English message; no AI attribution.
- One worktree per PR at `../taxon-worktrees/descendant-counts-projection-pr{1..3}`; base = `develop`; never commit to `main`.
- Strict TDD per `openspec/config.yaml`: every production task has a RED-first test before GREEN.
- RED commits ship first as standalone commits so the GREEN commit shows the diff clearly.
- Sequential only: no parallel writers, no parallel PRs. One worktree at a time.
- Spanish mirror of this file: `documents-es/openspec/descendant-counts-projection/tasks-es.md` (created at write time, faithful translation, neutral/professional register).
- Spanish mirror of each artifact-bearing PR lands in the SAME PR per AGENTS.md §1.
- Pre-PR gate: no Pencil MCP / `impeccable` review needed — backend-only change.

## Open Decisions Needing User Input

The orchestrator will surface the following decision before `sdd-apply` because the delivery strategy is `ask-on-risk` and PR #2 is borderline at ~440 LOC (40 lines over the 400-line cap):

**Which chain strategy should we use for the 3-PR chain?**

| Option | Tradeoff |
|--------|----------|
| `stacked-to-main` | Each PR merges to `develop` in order. Fast iteration. PR #2 over-budget risk is mitigated by per-commit `work-unit-commits` splitting (each child commit ≤ 400 LOC). |
| `feature-branch-chain` | `feature/projection` tracker branch accumulates the integration. PR #1 targets the tracker, PR #2 targets PR #1's branch, PR #3 targets PR #2's branch. Only the tracker merges to `develop`. Best for rollback control. |
| `size:exception` | Single PR with maintainer approval. Fastest but loses per-PR focus. Only viable if the reviewer is comfortable reviewing ~845 LOC in one go. |

The user must pick one before `sdd-apply` runs.
