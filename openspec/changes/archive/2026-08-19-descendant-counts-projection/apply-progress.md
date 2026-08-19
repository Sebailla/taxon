# Apply Progress: descendant-counts-projection

## Status: completed

All implementation work landed in PR #86 (`feat(api): materialise species_count for threshold-exceeding parents`), merged to `develop` as squash commit `915b1d6` with green CI (backend py3.11, backend py3.12, frontend, lighthouse).

## Work-Unit Commits (single PR — size:exception)

| Commit | Concern | Tests Added |
|--------|---------|-------------|
| `dcacbb3` | `feat(schema): add TaxonDescendantCount for cached descendant counts` | `test_schema.py`: 3 tests for table presence, PK, computed_at default |
| `8a8927a` | `feat(api): register_display_level helper + red-first contract tests` | `test_descendant_counts_projection.py`: 3 tests for the bare-engine registration gap |
| `6e49b55` | `feat(api): apply-projection CLI + projection helpers + widening` | `test_migrate.py`: workspace+projection table check + bare-engine regression; `test_descendant_counts_projection.py`: lookup/materialize helpers |
| `5c7a6fe` | `feat(api): wire projection into read path + import_data rebuild hook` | `test_species_count_lazy_null.py`: 2 updated tests for new semantics |
| `aae749f` | `docs(openspec): add SDD artifacts for descendant-counts-projection` | none — SDD artifacts + Spanish mirrors committed retroactively |

## TDD Cycle Evidence

| Task | RED Commit | GREEN Commit | REFACTOR |
|------|-----------|--------------|----------|
| 1 (TaxonDescendantCount ORM) | test_schema.py (pre-existing seed) | dcacbb3 | — |
| 2 (register_display_level) | test_descendant_counts_projection.py (initial 3 RED tests) | 8a8927a | mypy type: ignore for SQLAlchemy wrapping |
| 3 (CLI widening + apply-projection) | test_migrate.py (workspace+projection check + bare-engine regression) | 6e49b55 | ruff format pass |
| 4-6 (lookup, materialize, materialize_all) | test_descendant_counts_projection.py (lookup helpers + materialize tests) | 6e49b55 | same commit — helpers landed together |
| 12 (read-path integration) | test_species_count_lazy_null.py (updated contract) | 5c7a6fe | cast(Session, session) for monkey-patched stub |
| 13 (batch integration) | test_api_router_tree.py regression (unchanged) | 5c7a6fe | — |
| 14 (import_data hook) | test_import.py (unchanged green) | 5c7a6fe | — |

## Deviations from Design

None. The implementation follows `design.md` exactly:

- `register_display_level` closes the `taxonomy_display_level` registration gap (`design.md:387-403`).
- `_count_descendant_species` consults `lookup_one` before the threshold guard and triggers `materialize_for_parent` for over-threshold parents (`design.md:296-312`).
- `_batch_species_counts` excludes cached ids from the CTE seed via `lookup_many` (`design.md:326-342`).
- `apply-projection` CLI with `--threshold` and `--budget-seconds` flags (`design.md:94` + `taxon/migrate.py:236-262`).
- `import_data` hook via `_rebuild_descendant_counts_projection` (`design.md:282-287` + `taxon/import_data.py:124-150`).

## Risks Closed

1. **Registration gap** (`design.md:365-403`) — closed by `register_display_level`. Regression net: `test_apply_projection_populates_rows_on_bare_engine`.
2. **Spec `Out of Scope` line** — pruned in commit `8a8927a`.

## Remaining Tasks

None. The change is closed end-to-end:

- [x] Proposal, spec, design, tasks artifacts persisted.
- [x] All 17 tasks implemented.
- [x] 285 pytest passed, 1 skipped (data/col.db not present in CI image).
- [x] ruff, format, mypy all clean.
- [x] PR #86 open and reviewed.
- [x] PR #86 merged to develop with green CI.
- [x] `/learn-es/2026-08-19-descendant-counts-projection.md` written per AGENTS.md §2.

## Out-of-Scope (deferred)

- No new public endpoint (`GET /api/taxon/{id}/species-count` not added).
- No migration of legacy `taxon.db` files (handled by `apply` widening).
- No non-SQLite backends (`register_display_level` is SQLite-only).
- Pre-existing threshold asymmetry between `_count_descendant_species` (1M) and `_batch_species_counts` (100k) not addressed.

## Rollback Path

1. `git revert 915b1d6` — single squash commit, atomic rollback.
2. `python -m taxon.migrate apply` on legacy DBs — does NOT drop the projection table; idempotent. For full removal: `DROP TABLE taxon_descendant_counts`.
3. The pre-change read-path behaviour (`species_count=None` for over-threshold parents) returns automatically because `lookup_one` returns `None` when the table is absent.

## Verification Summary

| Gate | Result |
|------|--------|
| `pytest taxon/tests/ -v` | 285 passed, 1 skipped |
| `ruff check .` | clean |
| `ruff format --check .` | clean |
| `mypy taxon/` | clean (49 source files) |
| CI backend py3.11 | SUCCESS |
| CI backend py3.12 | SUCCESS |
| CI frontend (node 20) | SUCCESS |
| CI lighthouse (a11y) | SUCCESS |
| PR mergeable | MERGEABLE → MERGED |