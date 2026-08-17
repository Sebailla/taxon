# Archive Report: arbol-col-browse

**Change**: `arbol-col-browse`
**Closed**: 2026-08-16
**Final HEAD**: `69d00e2` on `develop`
**Merged PR**: #69 (commit `3fc2eb1`) — https://github.com/Sebailla/taxon/pull/69
**Closes**: issue #67 — replace the 7-dropdown Cascade with a CoL-style hierarchical TaxonomicTree
**Artifact store mode**: hybrid (filesystem + Engram observation `sdd/arbol-col-browse/archive-report`)

## Summary

The `arbol-col-browse` change replaces `frontend/src/components/Cascade.tsx` (7-dropdown linear cascade that broke on `data/col.db` due to a missing `biota` rank) with a CoL-style hierarchical `TaxonomicTree` that lazy-loads children by `parent_id`, indents by rank, renders `rank: Name Authorship • N spp.` rows, and exposes `Source` + `Extant only` filters. The explored path flows through the `cascadePath` Zustand store and a `path:change` CustomEvent so the breadcrumb-links panel keeps working. Parent-id addressing bypasses the `Biota` synthesis bug.

## What Shipped

### Backend (PR #69 merge `3fc2eb1`)
- `taxon/api/tree.py` (new): `list_tree_children(parent_id, include, limit, cursor)`, `search_taxon(q, limit, include_extinct)`, `_split_authorship(name, display_name)`, recursive CTE for `species_count` with lazy `null` >100k direct children.
- `taxon/api/router.py` (modified): `GET /api/tree/children` and `GET /api/tree/search` registered BEFORE the `/{path:path}/taxon-links` catch-all (route-ordering RED test 1.9 covers shadowing).
- `taxon/api/schemas.py` (modified): `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`, `TreeSearchHit` exported from `__all__`. `TreeNodeResponse` extends `TaxonResponse` with `has_children`, `species_count`, `authorship` without mutating the canonical shape.

### Frontend (PR #69 merge `3fc2eb1`)
- `frontend/src/components/TaxonomicTree.tsx` (new, 618 LOC): caret rows, `Find taxon` header with `aria-activedescendant` combobox, `Source` + `Extant only` checkboxes, skeletons `role="treeitem"`, empty + error hoisted out of `role="tree"` host.
- `frontend/src/store/taxonomicTree.ts` (new): Zustand store with `childrenByParentId: Map`, `expandedIds: Set`, `rootIds`, actions `loadRoots`, `ensureChildren`, `toggleExpand`, `revealNode`, `setIncludeExtinct`, `clear`.
- `frontend/src/api.ts` (modified): `fetchTreeNode(parentId, init?)`, `fetchTreeSearch(q, init?)`, `createDebouncedSearch` with 200ms debounce.
- `frontend/src/App.tsx` (modified): mounts `<TaxonomicTree>` in the Cascade slot; breadcrumb-links `useEffect` and `path:change` listener kept verbatim.
- `frontend/src/components/Breadcrumb.tsx` (modified): aria-label kept verbatim as `Cascade path breadcrumb` (line 26).

### Deletions (PR #69 merge `3fc2eb1`)
- `frontend/src/components/Cascade.tsx`
- `frontend/src/components/Cascade.state.ts`
- 6 cascade test files (cascadeDynamicTiers, Cascade.pathAware, Cascade.ui, cascadeRoots, cascadeSubphylum, Cascade.test.tsx.legacy).

### Tests (final state, from PR #69 merge and CI on `69d00e2`)
- Backend: 192/192 pytest green.
- Frontend: 99/99 vitest green.
- TypeScript: `tsc -b` green.
- Vite: build green.
- Lint: `ruff format` + `ruff check` green.
- Lighthouse a11y green.
- 4 CI gates green (backend py3.11, backend py3.12, frontend node20, lighthouse a11y).

### Learn-es entry
- `learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` (committed in `69d00e2`) with Spanish mirror at `documents-es/learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` (per AGENTS.md §1).

## Specs Synced (delta → main)

| Domain | Action | Details |
|--------|--------|---------|
| `taxonomy-hierarchy` | MODIFIED + ADDED | MODIFIED: `Hierarchy Browse by Path`, `Stable Response Shape and Ordering`. ADDED: `Parent-id Children Endpoint`, `Tree Search Endpoint`, `species_count Lazy Semantics`, `Path-Resolver Endpoints Stay Verbatim`. Existing `## ADDED Requirements` (Permanent Breadcrumb, Clickable Breadcrumb Segment) preserved verbatim. |
| `taxonomic-tree-browse` | Created | Delta copied verbatim via shell `cp` + `diff -r` byte-identical readback. |
| `taxon-tree-search` | Created | Delta copied verbatim via shell `cp` + `diff -r` byte-identical readback. |

### Source of Truth Updated
- `openspec/specs/taxonomy-hierarchy/spec.md`
- `openspec/specs/taxonomic-tree-browse/spec.md` (new)
- `openspec/specs/taxon-tree-search/spec.md` (new)

## Stale-Checkbox Reconciliation (per skill exception)

The persisted `openspec/changes/arbol-col-browse/tasks.md` arrived at archive time with 18 tasks unchecked (`- [ ]`) because the previous `sdd-apply` sub-agent failed with `sdd_task_result_empty` (transport failure) and never persisted its progress. Per the `sdd-archive` skill's stale-checkbox exception (require user authorization + concrete evidence from `apply-progress`/`verify-report`/repository state), the user authorized reconciliation backed by:

- **Repository evidence**: backend files (`taxon/api/tree.py`, modified `router.py`/`schemas.py`) present; frontend files (`TaxonomicTree.tsx` 618 LOC, `taxonomicTree.ts` store, 5 test files) present; `Breadcrumb.tsx` aria-label verbatim at line 26; `Cascade.tsx` + `Cascade.state.ts` + 6 cascade test files absent; learn-es entry + Spanish mirror present.
- **PR evidence**: PR #69 merged to `develop` at `3fc2eb1` with 4 green CI gates; the merge commit body documents the sub-agent transport-failure drift that this change recovered from.
- **Final-state facts**: 192 pytest + 99 vitest + tsc-b + ruff + 4 CI gates green.

**Phase 2 deferral**: 4 tasks (2.1–2.4, Pencil design + impeccable audit) were marked `[x] [DEFERRED]` with verbatim rationale: Pencil MCP was disabled in the implementation session, so the prescriptive surface brief was captured as `docs/design/taxonomic-tree-browse.md` (784 lines, line-by-line translation spec for the implementer) instead of a `.pen` page. A follow-up issue may redo the Pencil `.pen` page in a future slice. This deferral is also recorded verbatim in the reconciliation note appended to `tasks.md`.

**Phase 3 reconciliation**: 14 tasks (3.1–3.14) were marked `[x]` based on repository evidence (file existence + merged PR) and the user authorization for stale-checkbox reconciliation. Evidence:
- 3.1 RED — `frontend/tests/api.treeChildren.test.ts` exists (15 tests)
- 3.2 GREEN — `fetchTreeNode`, `fetchTreeSearch` in `frontend/src/api.ts`
- 3.3 RED — `frontend/tests/api.treeSearch.test.ts` exists (5 tests)
- 3.4 GREEN — `createDebouncedSearch` in `frontend/src/api.ts`
- 3.5 RED — `frontend/tests/TaxonomicTree.test.tsx` exists (11 tests including drift-fix scenarios)
- 3.6 GREEN — `frontend/src/store/taxonomicTree.ts` has `loadRoots`, `ensureChildren`, `toggleExpand`, `revealNode`, `setIncludeExtinct`
- 3.7 GREEN — `frontend/src/components/TaxonomicTree.tsx` (618 LOC)
- 3.8 GREEN — `frontend/src/App.tsx` mounts `<TaxonomicTree>` in Cascade slot
- 3.9 GREEN — `Breadcrumb.tsx` aria-label verbatim as `Cascade path breadcrumb`
- 3.10 REFACTOR — `Cascade.tsx` + `Cascade.state.ts` + 6 cascade test files deleted
- 3.11 GREEN — `frontend/tests/App.taxonLinks.test.tsx` updated (2 tests)
- 3.12 RED — `frontend/tests/TaxonomicTree.a11y.test.tsx` exists (1 axe-core test)
- 3.13 GREEN — a11y fixes: `aria-activedescendant` on search comb, skeletons `role="treeitem"`, empty + error hoisted out of `role="tree"` host
- 3.14 Post-merge — learn-es entry committed in `69d00e2` with Spanish mirror

**Final task state**: 28/28 implementation tasks marked `[x]`, 0 unchecked. Reconciliation note appended at end of `tasks.md`.

## Drift Narrative

PR #69's body documents that the previous `sdd-apply` sub-agent failed with `sdd_task_result_empty` (transport failure) and never persisted its checkbox progress. The change captured all 14 Phase 3 implementation steps + tests + a11y fixes + learn-es entry in the drift-fix commits that comprise PR #69, but the persisted `tasks.md` continued to show `- [ ]` because the apply phase never settled. This archive reconciled the stale checkboxes per the user authorization, restoring the audit trail to match the actual final state.

## Archive Contents

- proposal.md ✅
- exploration.md ✅
- specs/ ✅ (3 delta specs — already merged into main specs above)
- design.md ✅
- tasks.md ✅ (28/28 tasks marked complete; reconciliation note appended)
- archive-report.md ✅ (this file; additive-only, excluded from snapshot/diff readback)

## Mechanical Copy Contract Evidence

- Spec sync (`taxonomic-tree-browse`, `taxon-tree-search`): empty `diff -r` output between source and destination for both files. Byte-identical mechanical copy.
- Archive move (`arbol-col-browse` → `archive/2026-08-16-arbol-col-browse`): empty `diff -r` output between pre-move snapshot and archived folder. Byte-identical move via `git mv`.
- `taxonomy-hierarchy/spec.md` merge: surgical in-place edits (MODIFIED requirement replacement + ADDED append) preserving the existing breadcrumb ADDED section verbatim.

## Final State Authority Hierarchy Applied

Per the `sdd-archive` Final-State Authority hierarchy:
- Native review authority: not applicable (RD kill switch off; no `reviewGate` to validate; proceed under ordinary repository policy).
- Persisted tasks artifact: reconciled per skill exception; final state 28/28 complete.
- Orchestrator's explicit final-state facts: 192/192 pytest, 99/99 vitest, tsc-b green, ruff format + check green, 4 CI gates green, PR #69 merged at `3fc2eb1`, learn-es at `69d00e2`.
- Intermediate snapshots (`verify-report`, `apply-progress`): not relied upon for final-state claims; their intermediate snapshots were outranked by the final-state facts above where they would otherwise disagree.

## Risks

- Phase 2 Pencil design + impeccable audit was deferred (no `.pen` page exists for `taxonomic-tree-browse`). The design was captured prescriptively in `docs/design/taxonomic-tree-browse.md` and shipped. A follow-up issue may redo the Pencil `.pen` page in a future slice if the team wants a visual artifact for `impeccable` to audit.

## SDD Cycle Complete

The change has been fully planned, implemented, verified (4 CI gates green), and archived. Ready for the next change.
