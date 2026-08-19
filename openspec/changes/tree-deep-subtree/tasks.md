# Tasks: tree-deep-subtree

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,010 total (360 + 150 + 380 + 120) |
| 400-line budget risk | Low (per PR) |
| Chained PRs recommended | Yes |
| Suggested split | A.1 → A.2 → C → D |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| A.1.1 | Failing test pins `next_tiers` on Animalia | PR A.1 | `pytest taxon/tests/test_api_router_tree.py::test_tree_children_next_tiers_animalia_first_page -x` | N/A (fixture only, no server) | Revert commit; old envelope still serialises with `next_tiers=None` |
| A.1.2 | Extract roll-up helpers to `_tree_tiers.py` | PR A.1 | `pytest taxon/tests/test_api_router_tree.py -x` | N/A (import refactor, behaviour preserved) | Revert commit; helpers re-exported from `sqlite_resolver.py` |
| A.1.3 | Add `TreeNodeTier` + `_per_tier_walk` + cursor helpers | PR A.1 | `pytest taxon/tests/test_api_router_tree.py -x` | N/A (pure-Python helpers) | Revert commit; `next_tiers` field still optional |
| A.1.4 | Wire `next_tiers` envelope into router | PR A.1 | `pytest taxon/tests/test_api_router_tree.py -x` | `uvicorn taxon.api.app:app` + `curl /api/tree/children?parent_id={animalia}` | Revert commit; old query path intact |
| A.1.5 | Spec docs commit (PR B folded in) | PR A.1 | `pytest` (no test, doc-only) | N/A | Revert commit; no code change |
| A.2.1 | Failing test for index migration | PR A.2 | `pytest taxon/tests/test_migrate.py::test_migrate_creates_parent_rank_name_index -x` | N/A (in-memory SQLite) | Revert commit; index not declared |
| A.2.2 | Add composite index to schema | PR A.2 | `pytest taxon/tests/ -x` | N/A (DDL only) | Revert commit; schema change reverts |
| A.2.3 | Wire `migrate.py` ensure_indexes | PR A.2 | `pytest taxon/tests/test_migrate.py -x` | `python -m taxon.migrate` on `data/col.db` | Revert commit; standalone migrate no-op |
| C.1 | Failing vitest for tier-group contract | PR C | `pnpm vitest run frontend/src/components/TaxonomicTree.test.tsx` | N/A (component test) | Revert commit; no UI change |
| C.2 | Store gains `nextTiers` + `tierRowsByKey` + `loadMore` | PR C | `pnpm vitest run frontend/src/store/taxonomicTree.test.ts` | N/A (zustand test) | Revert commit; old store slice intact |
| C.3 | `api.ts` widens + `fetchTierPage` | PR C | `pnpm vitest run frontend/src/api.test.ts` | N/A (fetch mock) | Revert commit; old fetch wrapper intact |
| C.4 | `<TierGroup>` component + walk() integration | PR C | `pnpm vitest run frontend/src/components/TaxonomicTree.test.tsx` | `pnpm dev` + browser smoke | Revert commit; old `walk()` intact |
| C.5 | Keyboard nav + ARIA | PR C | `pnpm vitest run frontend/src/components/TaxonomicTree.test.tsx` | axe-core + Playwright smoke | Revert commit; component intact |
| D.1 | Verification report | PR D | `pytest taxon/tests/ && pnpm vitest && pnpm build` | Same harness | Revert commit; doc-only |
| D.2 | `/learn-es/2026-08-19-tree-deep-subtree.md` | PR D | N/A (no test) | N/A | Revert commit; doc-only |
| D.3 | Archive report | PR D | N/A (no test) | N/A | Revert commit; doc-only |

## Phase 1 — PR A.1: Backend subtree envelope + router wiring (~360 LOC)

**Worktree**: `../taxon-worktrees/tree-deep-subtree-pr1`
**Branch**: `feat/tree-deep-subtree-pr1`
**Base / Target**: `develop`
**Strict TDD**: every work unit starts with a RED test (except the docs commit).

### Work unit 1 — failing test pins `next_tiers` on Animalia

- [x] 1.1 Add `test_tree_children_next_tiers_animalia_first_page` to `taxon/tests/test_api_router_tree.py`; build a synthetic WoRMS-shaped fixture (50 genus direct + 5 phylum direct + tier mocks) when the live `data/col.db` is unavailable; assert `body["next_tiers"]` is non-empty and the first tier is `phylum` with `len(children) >= 30`.
- [x] 1.2 Add `test_tree_children_next_tiers_leaf_omits_tiers` pinning `next_tiers is None` for a true-leaf parent; add `test_tree_children_next_tiers_default_cap_50` asserting no tier exceeds 50 rows on the first page.
- [x] 1.3 Commit: `test(tree): pin next_tiers contract for Animalia first page`.

### Work unit 2 — extract roll-up helpers to `_tree_tiers.py`

- [x] 2.1 Move `_phylum_rollup`, `_family_rollup`, `_collect_descendants_by_rank`, `_build_tiers_from_grouping`, `_build_tier` from `taxon/api/sqlite_resolver.py` to `taxon/api/_tree_tiers.py`.
- [x] 2.2 Re-export them from `sqlite_resolver.py` so `list_path_children` keeps the public surface; both modules now share the single source of truth.
- [x] 2.3 Run `pytest taxon/tests/test_api_router_tree.py taxon/tests/test_api_router_path.py -x`; must stay green (no behaviour change).
- [x] 2.4 Commit: `refactor(api): extract roll-up helpers to _tree_tiers shared module`.

### Work unit 3 — `TreeNodeTier` schema + `_per_tier_walk` + cursor helpers

- [x] 3.1 `taxon/api/schemas.py`: add `TreeNodeTier(BaseModel)` with `rank`, `label`, `examples`, `children: list[TreeNodeResponse]`, `next_cursor: str | None = None`; extend `TreeChildrenResponse` with `next_tiers: list[TreeNodeTier] | None = None`.
- [x] 3.2 `taxon/api/_tree_tiers.py`: add `_per_tier_walk(session, parent_id, tier_ranks, *, max_depth=8, tier_limit=50, cursor=None, include_extinct=True) -> list[Taxon]` with the recursive CTE from the design (parametrised `:tier_ranks` + `max_depth=8`).
- [x] 3.3 Add `_build_next_tiers(session, parent_id, direct_children, *, tier_limit=50, cursor=None, include_extinct=True) -> list[TreeNodeTier] | None` that calls `_per_tier_walk` + `_children_grouped_by_rank` + the roll-up rules + cursor handling.
- [x] 3.4 Add `_encode_cursor(name, id) -> str` and `_decode_cursor(cursor) -> tuple[str, int]` (opaque base64 of `f"{name}\x00{id}"`); unit-test the round-trip.
- [x] 3.5 Commit: `feat(api): add TreeNodeTier envelope + per-tier recursive CTE`.

### Work unit 4 — wire envelope into `list_tree_children` + `get_tree_children`

- [x] 4.1 `taxon/api/tree.py::list_tree_children` accepts `tier: str | None = None` and `tier_limit: int = 50`; computes `_build_next_tiers` once for the parent envelope; honours `tier` query param when present (returns the paginated page for that tier only, no envelope).
- [x] 4.2 `taxon/api/router.py::get_tree_children` accepts `tier` + `tier_limit` query params; clamps `tier_limit > 200` silently; rejects `< 1` with HTTP 400.
- [x] 4.3 The failing tests from work unit 1 now pass; add `test_tree_children_next_tiers_pagination_round_trip` and `test_tree_children_next_tiers_off_tuple_collapse`.
- [x] 4.4 Commit: `feat(api): wire next_tiers envelope into /api/tree/children`.

### Work unit 5 — spec docs commit (PR B folded in)

- [x] 5.1 Copy `openspec/changes/tree-deep-subtree/specs/subtree-envelope.md` → `openspec/specs/taxonomic-tree-browse/subtree.md` (adjacent to the current `spec.md`); copy the Spanish mirror to `documents-es/openspec/specs/taxonomic-tree-browse/subtree-es.md`.
- [x] 5.2 Append a "Delta applied" footnote to `openspec/specs/taxonomic-tree-browse/spec.md` pointing at the new sibling file (verbatim per the change archive convention).
- [x] 5.3 Commit: `docs(specs): add subtree envelope delta to taxonomic-tree-browse capability`.

PR A.1 lands as 5 commits, ~360 LOC (280 code + 80 docs).

## Phase 2 — PR A.2: Index migration + `taxon.migrate` (~150 LOC)

**Worktree**: `../taxon-worktrees/tree-deep-subtree-pr2`
**Branch**: `feat/tree-deep-subtree-pr2`
**Base / Target**: `develop`
**Depends on**: PR A.1 merged.

### Work unit 1 — failing test for migration

- [ ] 1.1 Add `test_migrate_creates_parent_rank_name_index` to `taxon/tests/test_migrate.py`: drop-if-exists, run migrate, assert index present, run again, assert still present.
- [ ] 1.2 Add `test_migrate_skips_index_if_present` (no-op when index exists) and `test_migrate_preserves_existing_indexes` (row count + 3 prior indexes unchanged).
- [ ] 1.3 Commit: `test(migrate): pin parent_rank_name index migration contract`.

### Work unit 2 — declare composite index in `Taxon`

- [ ] 2.1 `taxon/schema.py::Taxon.__table_args__` gains `Index("ix_taxa_parent_rank_name", "parent_id", "rank", "name")`.
- [ ] 2.2 Run `pytest taxon/tests/ -x`; in-memory SQLite creates the index automatically and tests stay green.
- [ ] 2.3 Commit: `feat(schema): add ix_taxa_parent_rank_name composite index`.

### Work unit 3 — wire `_ensure_indexes` + standalone CLI flags

- [ ] 3.1 `taxon/migrate.py::_ensure_indexes()` adds `CREATE INDEX IF NOT EXISTS ix_taxa_parent_rank_name ON taxa (parent_id, rank, name)` step; second call is a no-op.
- [ ] 3.2 Standalone `taxon.migrate` script accepts `--only-index` (skip non-index migrations) and `--skip-indexes` (skip index step) CLI flags; help text documents both.
- [ ] 3.3 Failing tests from work unit 1 now pass; commit: `feat(migrate): wire ix_taxa_parent_rank_name into ensure_indexes`.

PR A.2 lands as 3 commits, ~150 LOC.

## Phase 3 — PR C: Frontend rewrite (~380 LOC)

**Worktree**: `../taxon-worktrees/tree-deep-subtree-pr3`
**Branch**: `feat/tree-deep-subtree-pr3`
**Base / Target**: `develop` (after PR A.2 merges)
**Depends on**: PR A.2 merged + Pencil MCP design pass + `impeccable` audit per `AGENTS.md §5`.
**Gate**: do not start until the Pencil `.pen` file is reviewed and `impeccable` signs off; record the design link in the PR body.

### Work unit 1 — failing vitest for tier-group contract

- [ ] 1.1 `frontend/src/components/TaxonomicTree.test.tsx` adds: `renders_tier_groups_collapsed_by_default`, `expanding_tier_group_fetches_first_page`, `load_more_appends_rows`, `keyboard_navigation_across_tier_groups`, `aria_labels_on_tier_group_and_button`.
- [ ] 1.2 Commit: `test(tree): pin tier-group rendering contract`.

### Work unit 2 — store gains `nextTiers` + `tierRowsByKey` + `loadMore`

- [ ] 2.1 `frontend/src/store/taxonomicTree.ts` adds `nextTiersByParentId: Map<number, TreeNodeTier[]>` and `tierRowsByKey: Map<string, { rows: TreeNodeResponse[]; nextCursor: string | null }>` (key `${parentId}:${rank}`).
- [ ] 2.2 New `loadMore(parentId, rank)` action: calls `fetchTierPage`, appends rows to `tierRowsByKey`, updates the `nextCursor`.
- [ ] 2.3 `setIncludeExtinct` invalidation also nukes `nextTiersByParentId` + `tierRowsByKey` (same discipline as `childrenByParentId`).
- [ ] 2.4 Commit: `feat(tree-store): add next_tiers cache + loadMore action`.

### Work unit 3 — `api.ts` widens + `fetchTierPage`

- [ ] 3.1 `frontend/src/api.ts::TreeChildrenResponse` widens to include `next_tiers: TreeNodeTier[] | null`; new `TreeNodeTier` interface mirrors the backend.
- [ ] 3.2 `fetchTierPage(parentId, tier, cursor, { tierLimit = 50, signal? })` calls `/api/tree/children?parent_id=...&tier=...&cursor=...&tier_limit=...&limit=...`; returns the tier page payload.
- [ ] 3.3 `buildTreeChildrenUrl` accepts `tier` + `cursor` query params.
- [ ] 3.4 Commit: `feat(api): add fetchTierPage helper + widen TreeChildrenResponse type`.

### Work unit 4 — `<TierGroup>` component + `walk()` integration

- [ ] 4.1 `frontend/src/components/TaxonomicTree.tsx`: new `<TierGroup tier={TreeNodeTier} parentId={number} depth={number} />` component — renders header (caret + label + row count), child rows, "Load more" button when `next_cursor` is non-empty; tier rows sit one indent level deeper than the header.
- [ ] 4.2 `walk()` gains `visitTierGroup(parentId, depth, tier)` callback that calls `<TierGroup>` between direct children and the existing grandchild flow.
- [ ] 4.3 Default state: first tier (`phylum`) expanded, subsequent tiers collapsed; matching caret toggle.
- [ ] 4.4 Failing tests from work unit 1 (`renders_tier_groups_collapsed_by_default`, `expanding_tier_group_fetches_first_page`, `load_more_appends_rows`) now pass.
- [ ] 4.5 Commit: `feat(tree): render tier groups + load-more pagination`.

### Work unit 5 — keyboard nav + ARIA

- [ ] 5.1 Tab order across tier groups in cascade-rank order; ArrowDown/Up inside a group; ArrowRight/Left expand/collapse the header; Enter toggles row caret when `has_children=true`; Home/End jumps to first/last row of the active group.
- [ ] 5.2 ARIA: tier group container `role="group"` + `aria-label="<label> group"`; header `role="button"` + `aria-expanded` + `aria-controls`; "Load more" button `aria-label="Load more <label>"`.
- [ ] 5.3 Commit: `feat(tree): tier-group keyboard navigation + ARIA labels`.

PR C lands as 5 commits, ~380 LOC.

## Phase 4 — PR D: Verification + learn-es + archive (~120 LOC)

**Worktree**: `../taxon-worktrees/tree-deep-subtree-pr4`
**Branch**: `chore/tree-deep-subtree-verify`
**Base / Target**: `develop` (after PR C merges)

### Work unit 1 — verification report

- [ ] 1.1 Run `pytest taxon/tests/` + `mypy taxon/` + `ruff check taxon/` + `pnpm vitest` + `pnpm build`; all must be green on `develop`.
- [ ] 1.2 Write `openspec/changes/tree-deep-subtree/verify-report.md` + Spanish mirror `documents-es/openspec/changes/tree-deep-subtree/verify-report-es.md` with CRITICAL/WARNING/SUGGESTION findings and the screenshot set from the browser smoke session.
- [ ] 1.3 Commit: `docs(verify): add tree-deep-subtree verification report`.

### Work unit 2 — learn-es entry

- [ ] 2.1 Write `/learn-es/2026-08-19-tree-deep-subtree.md` per `AGENTS.md §2` structure (What / How / Where / Why / How it works / Workflows) in neutral/professional Spanish.
- [ ] 2.2 Commit: `docs(learn-es): entry for tree-deep-subtree change (PRs #A.1, #A.2, #C)`.

### Work unit 3 — archive report

- [ ] 3.1 Write `openspec/changes/tree-deep-subtree/archive-report.md` per the standard closing artifact: the 4 PRs, the synced specs (`taxonomic-tree-browse/spec.md` + new `subtree.md` sibling), the lessons learned.
- [ ] 3.2 Commit: `chore(openspec): archive tree-deep-subtree change`.

PR D lands as 3 commits, ~120 LOC.

## Critical Path

1. **PR A.1** (5 commits, ~360 LOC) — backend envelope + router + extracted helpers; PR B docs fold in.
2. **PR A.2** (3 commits, ~150 LOC) — composite index + `taxon.migrate`; requires A.1 on `develop`.
3. **PR C** (5 commits, ~380 LOC) — frontend rewrite; requires A.2 on `develop` + Pencil + `impeccable` sign-off.
4. **PR D** (3 commits, ~120 LOC) — verification + learn-es + archive; requires C on `develop`.

## Conventions Reference

- Conventional commits per `AGENTS.md §3`; English message; no AI attribution.
- One worktree per PR at `../taxon-worktrees/tree-deep-subtree-pr{1..4}`; base = `develop`; never commit to `main`.
- Each commit must leave the test suite green (RED → GREEN → REFACTOR when TDD applies).
- Spanish mirror ships with each artifact-bearing commit per `AGENTS.md §1`.
- Pencil MCP + `impeccable` audit gates PR C per `AGENTS.md §5`.
- `work-unit-commits` + `chained-pr` skills per `AGENTS.md §3` for each PR.
