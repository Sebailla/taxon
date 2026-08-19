# Verify Report: descendant-counts-projection

## Status: passed

The implementation matches the spec, design, and tasks. CI was green on PR #86 (backend py3.11, backend py3.12, frontend, lighthouse). All 285 pytest cases pass locally; 1 is skipped (`test_default_used_when_no_argument_or_env` from the unrelated `test_api_database_url.py` — skipped because `data/col.db` is not on disk in the dev environment).

## Spec Conformance

### `descendant-counts-projection` (new spec)

| Requirement | Scenario | Conformance |
|-------------|----------|-------------|
| Schema | Fresh DB gains the table on apply | PASS — `test_apply_creates_workspace_and_projection_tables` asserts `taxon_descendant_counts` exists after `apply` |
| First-read materialisation | Cache hit returns in O(1) | PASS — `test_lookup_one_returns_cached_value_after_write` + `_count_descendant_species` test updated |
| Population rule | Threshold predicate reads `SPECIES_COUNT_LAZY_NULL_THRESHOLD` | PASS — `_projected_parent_ids` imports the constant |
| SLO-bounded rebuild | Over-budget rebuild returns None, no row written | PASS — `test_lazy_null_helper_returns_none_when_rebuild_exceeds_budget` uses `budget_seconds=0.0` to force the branch |
| `import_data` rebuild | Post-import rebuild | PASS — `_rebuild_descendant_counts_projection` runs after `_populate_species_paths` |
| `apply-projection` manual escape | CLI populates rows | PASS — `test_apply_projection_populates_rows_on_bare_engine` exercises the CLI end-to-end |
| Additive schema | Legacy DBs without the table still work | PASS — `lookup_one`/`lookup_many`/`_table_exists` guard against the missing table |

### `taxonomic-tree-browse` (delta)

| Change | Scenario | Conformance |
|--------|----------|-------------|
| MODIFIED requirement: lazy-expand now consults projection before threshold guard | Cache hit returns without CTE | PASS — `test_species_count_triggers_rebuild_when_above_threshold` |
| ADDED requirement: cache hit returns species_count from table | Cache miss + over-threshold parent triggers rebuild | PASS — `test_species_count_triggers_rebuild_when_above_threshold` |
| ADDED requirement: cache hit skips threshold guard | Cache hit below threshold returns cached value | PASS — same test |
| REMOVED requirement: unconditional lazy-null above threshold | — | REMOVED in the design + implementation; documented in `apply-progress.md` |

## Design Conformance

No deviations from `design.md`. Every architectural decision in the design landed:

- `register_display_level` registration helper (`design.md:387-403`)
- `lookup_one` cache pre-check in `_count_descendant_species` (`design.md:296-312`)
- `lookup_many` cache merge in `_batch_species_counts` (`design.md:326-342`)
- SLO guard via `REBUILD_BUDGET_SECONDS = 1.0` (`design.md:217-219`)
- `budget_seconds=None` escape for offline callers (`design.md:282-287`)
- `apply-projection` CLI with `--threshold` and `--budget-seconds` (`design.md:94`)
- Post-import rebuild via `import_data` (`design.md:282-287`)

## Risks Closed

| Risk | Mitigation | Status |
|------|-----------|--------|
| Registration gap (`design.md:402-403`) | `test_apply_projection_populates_rows_on_bare_engine` | CLOSED |
| `_count_descendant_species` semantic change | `test_species_count_lazy_null.py` updated for new contract | CLOSED |
| `_batch_species_counts` query shape assumption (`tasks.md` risk 3) | `lookup_many` runs before the seed union; cached ids excluded | CLOSED (design pinned byte-identical CTE) |

## Findings

- **CRITICAL:** none.
- **WARNING:** none.
- **SUGGESTION:** the pre-existing threshold asymmetry (100k vs 1M) is documented as out-of-scope and worth a follow-up proposal in a future change.
- **SUGGESTION:** the `_count_descendant_species` `register_display_level` test red-green cycle is now redundantly covered by both `test_descendant_counts_projection.py` and `test_apply_projection_populates_rows_on_bare_engine`; consider consolidating if the second test grows.

## Acceptance

| Criterion | Met |
|-----------|-----|
| Schema migrations applied | YES |
| All tests pass | YES (285/285, 1 skipped) |
| Lint clean | YES |
| Type-check clean | YES |
| Docs / learn-es / SDD artifacts complete | YES |
| Backward compatible with legacy DBs | YES (table-absent path tested) |
| PR reviewed and merged | YES (#86) |