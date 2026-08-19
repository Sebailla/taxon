# Proposal: descendant-counts-projection

## Intent

`/api/tree/children` returns `species_count=None` for any parent whose `direct_children_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` (1M). On the CoL tree, `Animalia`, `Eukaryota`, and `Methanobacteriota` are the only such parents today; the UI shows `?` forever because the recursive CTE is too expensive to run on demand. We materialise a new `taxon_descendant_counts` table that caches `(species_count, total_count)` for exactly those parents and serve `species_count` from the cache. First request triggers a synchronous rebuild; later requests (and reboots) read the cached row. `import_data` rebuilds after a CoL re-import; `python -m taxon.migrate apply-projection` is the manual escape hatch.

## Scope

### In Scope
- New SQLAlchemy table `taxon_descendant_counts(taxon_id PK, species_count INT, total_count INT, computed_at TIMESTAMP)` created by `taxon.migrate`.
- `_rebuild_descendant_counts(taxon_id)` helper: walks the subtree once, upserts the row, bounded by the descendant population.
- On-demand materialisation: first `_count_descendant_species` call for a parent over the threshold runs the rebuild synchronously and writes the row.
- Read path: `_count_descendant_species` checks the table first; on hit returns `species_count` directly — no threshold guard, no CTE. Misses preserve current threshold + CTE. `_batch_species_counts` reads cached rows for the batch in one query.
- `import_data` rebuilds every threshold-exceeding parent after a CoL re-import.
- `python -m taxon.migrate apply-projection` subcommand for manual re-runs.
- Red-first tests in `taxon/tests/test_descendant_counts_projection.py`; precedent `taxon/tests/test_species_count_lazy_null.py`.
- Spanish mirror at `documents-es/openspec/descendant-counts-projection/proposal-es.md` per AGENTS.md §1.

### Out of Scope
- No new public endpoint; `/api/tree/children` surface unchanged.
- No schema migration of legacy `taxon.db`; the projection is purely additive.
- No non-SQLite backends, no threshold change, no TTL on cached rows, no frontend work.

## Capabilities

### New Capabilities
- `descendant-counts-projection`: persistent, lazily-materialised `(species_count, total_count)` projection keyed by `taxon_id`, covering exactly the parents whose direct-children count exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. New full spec required.

### Modified Capabilities
- `taxonomic-tree-browse`: `_count_descendant_species` and `_batch_species_counts` read `taxon_descendant_counts` before the threshold guard and the recursive CTE. Delta spec required.

## Approach

Single backend PR, branch from `develop`, target `develop`. Add `TaxonDescendantCount` to `taxon/schema.py` so `taxon.migrate apply` picks it up via `create_all`. `_rebuild_descendant_counts` reuses the existing recursive CTE inside a single transaction. `_count_descendant_species` gains a pre-check `SELECT species_count FROM taxon_descendant_counts WHERE taxon_id = :pid`; hit → return. Miss → fall through to the existing threshold + CTE path; on the threshold branch, rebuild synchronously and write the row before returning. The `_cache` request-scoped dict is preserved. `_batch_species_counts` issues one `IN`-list read before the CTE; remaining parents resolve as today. The synchronous rebuild must finish within the 1s `/api/tree/children` SLO; if it would exceed the budget, fall back to the existing CTE path and skip the write (surfaces as `species_count=None` on the first request). `taxon/import_data.py` rebuilds every threshold-exceeding parent after a CoL re-import; `taxon/migrate.py` gains `apply-projection`. Tests (RED-first): cache hit returns from the table without a CTE; cache miss rebuilds and writes; rebuild failure leaves the table untouched; `_batch_species_counts` merges cached rows with CTE results; `import_data` triggers rebuild; `apply-projection` is idempotent. Index decisions deferred to sdd-spec.

## Affected Areas

- `taxon/schema.py` — new `TaxonDescendantCount` ORM class on `Base.metadata`.
- `taxon/api/tree.py` — `_count_descendant_species` reads the table first; threshold branch triggers rebuild.
- `taxon/api/_tree_tiers.py` — `_batch_species_counts` pre-loads cached rows.
- `taxon/import_data.py` — rebuilds the projection after a CoL re-import.
- `taxon/migrate.py` — new `apply-projection` subcommand.
- `taxon/api/_projection.py` (new) — `_rebuild_descendant_counts`, `_diff_threshold_parents`, cache helpers.
- `taxon/tests/test_descendant_counts_projection.py` (new) — red-first tests for cache, rebuild, SLO fallback.
- `openspec/specs/descendant-counts-projection/spec.md` (new) — full spec for the projection capability.
- `openspec/specs/taxonomic-tree-browse/spec.md` — delta adds the cache-read path.
- `documents-es/openspec/descendant-counts-projection/proposal-es.md` (new) — Spanish mirror per AGENTS.md §1.
- `learn-es/2026-08-19-descendant-counts-projection.md` (new) — post-merge learning entry.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| First-request latency for a projected parent exceeds the 1s `/api/tree/children` SLO. | Medium | Rebuild bounded by descendant population of one parent; if predicted cost exceeds budget, helper falls back to the existing CTE path and skips the write. |
| Cache becomes stale after a re-import that does not go through `import_data` (manual SQL, restore from backup). | Low | `apply-projection` subcommand is the documented escape hatch; `computed_at` makes staleness observable. |
| Drift between the projection and `SPECIES_COUNT_LAZY_NULL_THRESHOLD` produces inconsistent counts. | Low | Both paths read the same threshold constant from `taxon/api/tree.py`; a single source of truth keeps them in sync. |

## Rollback Plan

Change is purely additive: the table sits alongside `taxa` and the read path falls through to the existing CTE when the row is missing. **Hot rollback**: `git revert <merge-commit>` in `develop`; `DROP TABLE taxon_descendant_counts;` and the read path returns to pre-change behaviour. **Full rollback** when the revert is not feasible: drop the table, revert the four touched files plus `taxon/api/_projection.py` and the new test file in a single follow-up PR branched from a known-good commit on `develop`. Threshold semantics are unchanged, so the UI reverts to lazy-null for the projected parents without further code.

## Dependencies

- `taxon.schema.Base` and `taxon.migrate.create_all` for the new table (no Alembic).
- The existing recursive CTE in `taxon/api/tree.py` is reused.
- `taxon/import_data.py` post-import hook.
- `pytest` + `httpx` (already in deps).
- Worktree at `../taxon-worktrees/descendant-counts-projection` from `develop`.

## Success Criteria

- [ ] `_count_descendant_species` returns `species_count` from `taxon_descendant_counts` for `Animalia`, `Eukaryota`, and `Methanobacteriota` after the first request; no CTE on subsequent reads.
- [ ] First-request latency for a projected parent stays under the 1s SLO; fallback exercised when it does not.
- [ ] `apply` creates `taxon_descendant_counts` on a fresh DB; `apply-projection` rebuilds every threshold-exceeding parent and is idempotent.
- [ ] `import_data` triggers the rebuild for every threshold-exceeding parent after a CoL re-import.
- [ ] All tests in `taxon/tests/test_descendant_counts_projection.py` and `taxon/tests/test_species_count_lazy_null.py` pass green on `develop`.
- [ ] `/learn-es/2026-08-19-descendant-counts-projection.md` entry created after green CI.
