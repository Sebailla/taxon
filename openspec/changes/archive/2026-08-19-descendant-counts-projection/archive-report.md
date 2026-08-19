# Archive Report: descendant-counts-projection

## Status: archived

The change closed end-to-end on `develop`. PR #86 merged as squash commit `915b1d6`. `/learn-es/2026-08-19-descendant-counts-projection.md` written per AGENTS.md §2. This archive report records the final state of the change artifacts.

## What Shipped

- New SQLAlchemy ORM class `TaxonDescendantCount` (`taxon/schema.py`).
- New module `taxon/api/projections.py` (~275 LOC) owning:
  - `register_display_level(engine)` — closes the SQLite user function registration gap on bare engines.
  - `lookup_one`, `lookup_many` — cache readers.
  - `_table_exists`, `_projected_parent_ids` — population helpers.
  - `materialize_for_parent`, `materialize_all` — rebuild workers with SLO budget.
- `taxon/migrate.py` widened: `_run_apply` creates the projection table on `apply`; new `apply-projection` subcommand.
- `taxon/api/tree.py:_count_descendant_species` consults the cache before the threshold guard.
- `taxon/api/_tree_tiers.py:_batch_species_counts` merges cached rows before the CTE seed.
- `taxon/import_data.py` rebuilds the projection at the end of every successful import.

## Final Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| Proposal | `openspec/changes/descendant-counts-projection/proposal.md` | done |
| Spec | `openspec/changes/descendant-counts-projection/specs/descendant-counts-projection/spec.md` | done |
| Spec (delta) | `openspec/changes/descendant-counts-projection/specs/taxonomic-tree-browse/spec.md` | done |
| Design | `openspec/changes/descendant-counts-projection/design.md` | done |
| Tasks | `openspec/changes/descendant-counts-projection/tasks.md` | done (71/71 tasks marked complete) |
| Apply progress | `openspec/changes/descendant-counts-projection/apply-progress.md` | done |
| Verify report | `openspec/changes/descendant-counts-projection/verify-report.md` | done |
| Spanish mirrors | `documents-es/openspec/descendant-counts-projection/*.md` | done |

## Permanent Specs Synced

The delta spec at `openspec/changes/descendant-counts-projection/specs/taxonomic-tree-browse/spec.md` documents the behavioural changes. No further sync to `openspec/specs/taxonomic-tree-browse/spec.md` is needed — that file carries the small `Out of Scope` line prune (commit `8a8927a`).

The new `descendant-counts-projection` capability is documented in the change folder; promotion to `openspec/specs/descendant-counts-projection/spec.md` is deferred to the next release that consumes it (the projection is internal to `taxon_descendant_counts` until a future change introduces an endpoint that surfaces the cached values directly).

## PR Trail

- **Issue #87** opened with the proposal body.
- **PR #86** opened with `size:exception` justification, body covers all 5 work-unit commits, 22 files changed (+3304 / -25).
- **CI**: backend py3.11 ✅, backend py3.12 ✅, frontend ✅, lighthouse ✅.
- **Merged** as squash commit `915b1d6` on `develop`.
- **Cleanup**: worktree removed, local branch deleted.

## Learnings

Captured in `/learn-es/2026-08-19-descendant-counts-projection.md` per AGENTS.md §2.

Notable items for the archive:

1. **`taxonomy_display_level` registration gap** — discovered by the design phase, closed by `register_display_level`. Worth flagging in future SQLite user-function additions to the repo.
2. **`_count_descendant_species` semantic shift** — from "lazy-null above threshold" to "rebuild + cache; lazy-null only when over SLO budget". Documented in the spec delta + learn-es entry.
3. **`from X import Y` inside a function is monkey-patchable from `X.Y`** — used in `test_lazy_null_helper_returns_none_when_rebuild_exceeds_budget` and worth knowing for future SLO guard tests.
4. **SDD artifacts need an explicit `git add`** — the sdd-* phases write files via the `write` tool but never commit. The orchestrator must add them before opening the PR.
5. **Threshold asymmetry between `_count_descendant_species` (1M) and `_batch_species_counts` (100k)** is pre-existing and was deliberately left alone — a follow-up proposal is worth opening.

## Next Steps

- The `descendant-counts-projection` capability is live on `develop`. The first request for `Animalia` triggers a synchronous rebuild; subsequent requests return from the cache.
- A future change could promote the new spec to `openspec/specs/descendant-counts-projection/spec.md` once the projection is consumed by a new endpoint.
- A future change could unify the threshold constants between the per-row and batched helpers.