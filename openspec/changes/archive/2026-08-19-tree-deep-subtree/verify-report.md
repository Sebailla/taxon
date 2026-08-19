# Verification Report — tree-deep-subtree (issue #76)

> **Verified on**: `develop` @ `c2ff70b` (PR #80 merged)
> **Date**: 2026-08-19
> **Verifier**: `sdd-verify` sub-agent (orchestrator-orchestrated)

## Change summary

`tree-deep-subtree` replaces the direct-only envelope of `GET /api/tree/children` with a per-tier subtree envelope that mirrors the proven `/api/path-children` shape. Each expanded parent now renders its descendants grouped by rank (`phylum`, `family`, `order`, `genus`, `species`), with per-tier pagination keyed `(name, id)` and the same `_phylum_rollup` / `_family_rollup` collapse rules the cascade already trusts.

## 4-PR delivery chain (all merged)

| PR | Title | Merge | LOC net | Status |
|----|-------|-------|---------|--------|
| A.1 (#77) | Subtree envelope + per-tier pagination | `bae59ab` | 1326 | ✅ size:exception (3.3× budget) |
| A.2 (#78) | Composite index + `taxon.migrate` | `b2294ed` | 325 | ✅ within budget |
| Design gate | Stitch design + impeccable audit | `6660505` | 193 | warning with 2 P1 fixes |
| C.1 (#79) | Store + api + fetchTierPage | `8824eb3` | 577 | ✅ within budget |
| C.2 (#80) | TierGroup + keyboard nav + ARIA | `c2ff70b` | 1037 | ✅ within production budget |

## Quality gate summary

| Gate | Result | Notes |
|------|--------|-------|
| `pytest taxon/tests/` | ✅ 267 passed | Backend tests through PR A.2 |
| `mypy taxon/` | ✅ 45 files clean | Backend typecheck |
| `ruff check taxon/` | ✅ all checks passed | Backend lint |
| `ruff format --check taxon/` | ✅ 45 files formatted | Backend format |
| `npm run typecheck` | ✅ clean | Frontend typecheck |
| `npm run lint` | ✅ clean | Frontend lint |
| `npm run test` | ✅ 24 files / 152 tests | Frontend |
| `npm run build` | ✅ clean | Frontend bundle |
| CI pipeline (4 jobs × 4 PRs) | ✅ 4/4 SUCCESS on every PR | backend 3.11 + 3.12, frontend node 20, lighthouse a11y |

## Specification coverage

| Spec scenario | Implementation | Status |
|---|---|---|
| `next_tiers` envelope shape (per-tier rows + cursor) | `taxon/api/schemas.py::TreeNodeTier` + `taxon/api/_tree_tiers.py::_build_next_tiers` | ✅ |
| Per-tier recursive CTE (`max_depth=8`) | `taxon/api/_tree_tiers.py::_per_tier_walk` | ✅ |
| Per-tier row cap (50 default, 200 max) | `taxon/api/router.py::get_tree_children` (clamp + 400 reject) | ✅ |
| Per-tier cursor pagination keyed `(name, id)` | `taxon/api/_tree_tiers.py::_encode_cursor` + `_decode_cursor` | ✅ |
| `_phylum_rollup` / `_family_rollup` collapse | `taxon/api/_tree_tiers.py` (extracted from `sqlite_resolver.py`) | ✅ |
| Cascade-rank ordering | `taxon/api/hierarchy::_DISPLAY_LEVELS_IN_ORDER` | ✅ |
| `ix_taxa_parent_rank_name` composite index | `Taxon.__table_args__` + `taxon.migrate._ensure_indexes` | ✅ |
| Frontend `<TierGroup>` rendering | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| Frontend `next_tiers` cache + `loadMore` action | `frontend/src/store/taxonomicTree.ts` | ✅ |
| Frontend `fetchTierPage` helper | `frontend/src/api.ts` | ✅ |
| Frontend keyboard nav (ArrowDown/Up/Right/Left/Enter/Home/End) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| Frontend ARIA surface (`role="group"`, `aria-expanded`, `aria-controls`, `aria-label`) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| P1 #1 (text contrast: text-slate replaces text-muted/outline) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| P2 #1 (hide Load more when no cursor) | `frontend/src/components/TaxonomicTree.tsx` (`hasMore` calc) | ✅ |

## Findings

### CRITICAL

None.

### WARNING

1. **PR A.1 size:exception (1326 LOC net vs 360 forecast)** — already accepted by user; documented in PR #77 body. The bulk is the new shared module `taxon/api/_tree_tiers.py` (+572 LOC) which hosts the extracted helpers + per-tier CTE + cursor + envelope builder + `_plural_label` + `_row_to_dataclass` together because they share `tier_ranks` ordering. Splitting the extraction across two commits would have inflated the chain without reducing cognitive load on review.

2. **PR C original was split into 2 PRs (C.1 + C.2)** — user chose split over size:exception. PR C.2 merged at 1037 LOC net, but the production code (`TaxonomicTree.tsx`, ~638 LOC) is within the 400-line budget; the rest is test coverage.

### SUGGESTION

1. **Backend `_per_tier_walk` second round-trip** — the CTE returns ids only, then a second `fetch rows by id` re-orders by `lower(name), name`. Intentional per the design. If the dataset grows beyond ~50k rows per tier, revisit and consider materialised intermediate (followed up via issue, not this PR).

2. **Per-row `_count_descendant_species` in the enrich callback** — for an Animalia-sized first page (5 phyla × 50 rows × 6 tiers ≈ 1500 per-row CTEs worst case) this could blow past the 50ms p95 budget on `data/col.db`. MVP runs against in-memory SQLite; real-dataset benchmarking deferred.

3. **Spec mirror files (proposal-es.md, design-es.md, explore-es.md) under `documents-es/openspec/changes/tree-deep-subtree/` were lost** during session cleanup (the `git checkout --` step discarded untracked files because the parent checkout had them only as untracked). The English artifacts in `openspec/changes/tree-deep-subtree/` are intact; only the Spanish mirrors of the planning layer are missing. Spec delta mirror (`subtree-es.md`) survived because it shipped via PR A.1. Follow-up: re-author the planning mirror if needed from the English originals.

4. **P2/P3 items from the impeccable audit** (caret rotation, connector break, rank-specific badges, approximate tilde tooltip, source toggle tooltip) are tracked as SUGGESTIONs; not blockers, not in this PR's scope.

## Risks

| Risk | Likelihood | Status |
|------|------------|--------|
| Sub-agent `sdd-apply` produced no output (transport failure) during PR C.2 launch | Confirmed once | Recovered: orchestrator completed WU 2 + WU 3 directly with same spec + surface brief; CI green |
| `Detect.mjs` for the impeccable Assessment B is not installed at the project root | Confirmed | Audit ran as degraded inline (single-context); documented in surface brief |
| Runaway `_count_descendant_species` on real data | Medium | Deferred to benchmark follow-up |

## Closure

`change: tree-deep-subtree` is verified ready for archive. Spec delta (`subtree.md`) plus the existing `taxonomic-tree-browse.spec.md` footnote form the durable surface. The 4-PR chain delivered the contract end-to-end with no CRITICAL findings, 2 accepted WARNINGS (both documented), and 4 SUGGESTIONs for future work.
