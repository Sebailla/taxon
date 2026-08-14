# Proposal: cascade-checklistbank

## Intent

The cascade backend currently serves Kingdom→Phylum→Class→Order→Family→Genus from the GBIF Species API. The live smoke test returned only 4 phyla under `Animalia` (Arthropoda, Chordata, Cnidaria, Mollusca) — GBIF's backbone is incomplete for the user's domain. ChecklistBank's `COL2024` release exposes 34 real phyla under `Animalia`, plus the missing root tier (`Biota`) and the subphylum tier that GBIF collapses. We migrate the cascade backend end-to-end to `https://api.checklistbank.org` against the `COL2024` dataset, add Biota as the visible root and subphylum as a real intermediate tier, and update the cascade UI to render both. The previous attempt tracked under issue #32 used GBIF and failed at the smoke-test phase; this change is the pivot, not a re-issue of #32.

## Scope

### In Scope
- Replace `taxon/gbif.py` with `taxon/checklistbank.py` (new module, new field names, opaque `str` IDs).
- Rewrite `taxon/api/gbif_path_children.py` → `taxon/api/clb_path_children.py` with the 9-tier tuple `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)`.
- Update `taxon/api/router.py`: cascade endpoints bind to `Depends(_get_checklistbank_client)`.
- `/api/kingdoms` returns Biota + Viruses (root tier, 2 options). Picking Biota reveals 7 kingdoms in the next dropdown.
- Subphylum rendered when present (Chordata → Vertebrata subphylum → Mammalia class); skipped with `next_rank_hint = "class"` when the parent phylum has no subphylum children (e.g. Arthropoda).
- Pin dataset key to `COL2024`; document `3LR` magic-key upgrade path in code comments only.
- Delete `taxon/gbif.py`, `taxon/tests/test_gbif.py`, `taxon/tests/test_gbif_path_children.py`, `taxon/tests/test_api_gbif_router.py` after the router swap is green.
- Frontend slice (`Cascade.tsx`, `api.ts`, fixtures) to render Biota + subphylum, gated on Pencil MCP + `impeccable` audit per AGENTS.md §5.
- Spanish mirror at `documents-es/openspec/changes/cascade-checklistbank/proposal-es.md` per AGENTS.md §1.

### Out of Scope
- TTL/response cache on the resolver (follow-up PR if load testing shows need).
- Tighter kingdom dedup beyond the per-id dedup already in `_resolve_deepest`.
- Bump to `COL2025` or any future CoL release.
- Virus realm cascade beyond the root dropdown.
- Any change to the public response schema (`PathChildrenEnvelope`, `TaxonResponse`, `SpeciesListItem`).
- Closing or commenting on issue #32.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `taxonomy-hierarchy`: backend switches GBIF → ChecklistBank; effective tier set becomes 9 (Biota root + subphylum); root endpoint returns 2 options (Biota, Viruses) instead of 8 kingdoms; subphylum appears only when present. Public response schema (`id`/`name`/`display_name`, alphabetical ordering, 404/409 semantics) unchanged. Delta spec required.

## Approach

End-to-end GBIF → CLB replacement in three chained backend PRs (under 400-line budget each), plus one frontend PR after Pencil + `impeccable` clears.

**Backend chain (PR #1 → PR #2 → PR #3, all branch from `develop`, all target `develop`):**

- **PR #1 — `feat(checklistbank): add CLB client and taxon parser`** (~250 lines). New `taxon/checklistbank.py` mirrors `taxon/gbif.py` shape: `ChecklistBankClient` (4 methods: `get_taxon`, `get_children`, `search`, `_request`) + `ChecklistBankTaxon` dataclass (`id`, `name`, `labelHtml`, `parentId`, `count`, `childCount`, `authorship`, `rank`, `status`). Tests in `taxon/tests/test_checklistbank.py` use `httpx.MockTransport` with `_StubClient` mimicking `/dataset/COL2024/tree/{id}/children` and `/dataset/COL2024/nameusage/search`. RED-first: 9–10 tests.
- **PR #2 — `feat(checklistbank): path resolver with Biota root + subphylum tier`** (~400 lines). New `taxon/api/clb_path_children.py` (~280 lines) with 9-tier tuple. `_resolve_deepest` walks via `/tree/{id}/children` + name match (CLB search has no `higherTaxonKey`). `next_rank_hint` map: biota→kingdom, kingdom→phylum, phylum→subphylum/class (when subphylum empty), subphylum→class, class→order, order→family, family→genus, genus→species. Subphylum tolerance: phylum with 0 subphylum children → `next_rank_hint = "class"`. Tests in `taxon/tests/test_clb_path_children.py` (~350 lines, 11–12 tests): Biota root, subphylum bucket (Chordata → 3 subphyla, Arthropoda → 0 → skip), full Mammalia chain, dedup by opaque id.
- **PR #3 — `feat(api): route cascade endpoints through ChecklistBank client`** (~350 lines net, ~1,200 lines of deletions). Router swaps `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)`; tests renamed; new `taxon/tests/test_api_checklistbank_router.py` (4 tests). Delete `taxon/gbif.py` + 3 test files. Reviewers must confirm dead code is removed, not shadowed.

**Frontend slice (PR #4, separate chain because it depends on Pencil + `impeccable`):**

- **PR #4 — `feat(frontend): render Biota + subphylum in the cascade UI**. Pencil design pass on `taxon.pen` (one extra dropdown + subphylum label) under `impeccable` audit. Update `Cascade.tsx` label inference for "subphylum"/"biota"; `fetchKingdoms()` → `fetchRoots()` returning Biota + Viruses; fixtures add Biota. Branch from `develop`, target `develop`. ~150–200 lines.

**Worktrees.** `../taxon-worktrees/cascade-checklistbank-pr{1..4}`. Pencil design for PR #4 in a sibling worktree from `develop` so it does not block the backend chain. Commits split per `work-unit-commits` (parser+client / resolver+tests / router swap+test deletions) to stay under 400 changed lines per PR.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `taxon/gbif.py` | Removed | Replaced by `taxon/checklistbank.py`; deleted in PR #3. |
| `taxon/api/gbif_path_children.py` | Removed | Replaced by `taxon/api/clb_path_children.py`; deleted in PR #3. |
| `taxon/api/router.py` | Modified | Cascade endpoints swap `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)` in PR #3. |
| `taxon/api/schemas.py` | None | Public schema unchanged. |
| `taxon/checklistbank.py` | New | CLB client + dataclass; PR #1. |
| `taxon/api/clb_path_children.py` | New | 9-tier resolver with Biota root + subphylum bucket; PR #2. |
| `taxon/tests/test_checklistbank.py` | New | `_StubClient` mocks; PR #1. |
| `taxon/tests/test_clb_path_children.py` | New | Resolver tests incl. Biota + subphylum; PR #2. |
| `taxon/tests/test_api_checklistbank_router.py` | New | Router integration; PR #3. |
| `taxon/tests/test_gbif.py`, `test_gbif_path_children.py`, `test_api_gbif_router.py` | Removed | Deleted in PR #3. |
| `frontend/src/api.ts` | Modified | `fetchKingdoms()` → `fetchRoots()`; PR #4. |
| `frontend/src/components/Cascade.tsx` | Modified | Label inference for "subphylum"/"biota"; PR #4. |
| `frontend/src/components/Cascade.state.ts` | None | Reducer path-agnostic; absorbs new rank names. |
| `frontend/tests/*.test.tsx` | Modified | Mock paths add Biota; PR #4. |
| `taxon.pen` | Modified | Extra dropdown slot + subphylum label; PR #4 gated on `impeccable`. |
| `openspec/changes/cascade-checklistbank/` | New | proposal.md, design.md, tasks.md, spec deltas. |
| `documents-es/openspec/changes/cascade-checklistbank/` | New | Spanish mirrors (`-es` suffix). |
| `learn-es/2026-08-14-cascade-checklistbank.md` | New | Post-merge learning entry. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| CLB rate limiting (5–10 req/s per IP). Worst case: 8–9 chained `/tree/{id}/children` per dropdown click. | Medium | Out of scope for v1; track as follow-up. If observed during smoke test, add 60–120s TTL cache on resolver. |
| Subphylum insertion breaks previously saved GBIF-shaped URLs. | Medium | Resolver treats subphylum as optional: phylum with 0 subphylum children → `next_rank_hint = "class"`; UI collapses tier. Old saved URLs hit 404 with clear message. |
| Pencil + `impeccable` adds 1–2 days to PR #4. | High (certain) | Serial dependency per AGENTS.md §5; non-negotiable. Backend chain proceeds in parallel from sibling worktree. |
| Subphyla absent for most phyla (Chordata has 3, Arthropoda has 0). | Medium | Resolver skips tier by emitting `next_rank_hint = "class"`; reducer renders chain without subphylum slot. |
| Live API drift when CoL releases `COL2025`. | Low (~12 months) | `COL2024` pinned in client; `3LR` magic-key upgrade documented in code comment; bump is one-line constant change. |
| Dead GBIF code remains (shadowed, not deleted) in PR #3. | Low | Reviewers confirm `taxon/gbif.py`, 3 test files, `_get_gbif_client` override are physically removed. `grep -r "gbif\|Gbif"` must return zero hits post-merge. |
| Cascade reducer assumes stable path length; Biota adds one segment. | Low | Reducer already path-agnostic (renders N dropdowns from N non-leaf snapshots); `nextRankHint: string \| null` propagates any string. No structural change. |

## Rollback Plan

- **PR #1 rollback**: revert merge; `taxon/checklistbank.py` and tests are additive — no behavior change. Safe.
- **PR #2 rollback**: revert merge. Old resolver stays until PR #3 lands; router still depends on old client until PR #3.
- **PR #3 rollback**: destructive PR. Reverting requires follow-up PR reintroducing `taxon/gbif.py`, 3 test files, rewiring `taxon/api/router.py` to `Depends(_get_gbif_client)`. Base from commit just before PR #3 merged and re-apply any subsequent router changes.
- **PR #4 rollback**: revert merge. Frontend fetches fall back to old `/api/kingdoms` until PR #4 reapplied; backend stays green.
- **Hot rollback** (single PR not yet merged): `git revert <merge-commit>` in `develop`; fast-forward worktree branch; force-push if protected. For PR #3, hot rollback is unsafe due to deletions — use full rollback branch.
- **Dataset key rollback** (if `COL2024` decommissioned mid-year): bump `COL2024` → `3LR` in `taxon/checklistbank.py:DATASET_KEY`. One-line change; safe to ship without PR ceremony.

## Dependencies

- `https://api.checklistbank.org` reachable from dev (verified: `GET /dataset/COL2024/tree` returned 200 with 2 roots).
- `httpx` (already a dep) for the new client; no new runtime deps.
- `pytest` + `httpx.MockTransport` for tests.
- Pencil MCP + `impeccable` skill for PR #4 design pass.
- Worktrees at `../taxon-worktrees/cascade-checklistbank-pr{1..4}` from `develop`.
- `branch-pr` skill for PR open flow (taxon does not use `status:approved`/`type:*` labels — PR #29/#30/#31 as reference).

## Success Criteria

- [ ] `curl "https://api.checklistbank.org/dataset/COL2024/tree"` returns 200 with `{total: 2, result: [{id:"5T6MX", name:"Biota", childCount:7}, {id:"V", name:"Viruses", childCount:31}]}`.
- [ ] `curl "http://localhost:8000/api/kingdoms"` returns 2 items: `{id:"5T6MX", name:"Biota", display_name:"Biota"}` and `{id:"V", name:"Viruses", display_name:"Viruses"}`.
- [ ] `curl "http://localhost:8000/api/path-children?path=Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera"` resolves through CLB and returns 12 Panthera species (`P. leo`, `P. onca`, `P. pardus`, `P. tigris`, `P. uncia`, plus 7 historical synonyms).
- [ ] Live browser smoke test: Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → 12 species render. Animalia → Arthropoda shows classes directly (subphylum slot collapsed).
- [ ] `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"` returns zero hits in `develop` after PR #3 merges.
- [ ] Pencil design pass on `taxon.pen` reviewed by `impeccable` and approved before PR #4 lands.
- [ ] All 3 backend PRs land green on `develop` with CI passing; no reviewer flags the GBIF dead-code removal.
- [ ] `/learn-es/2026-08-14-cascade-checklistbank.md` entry created after green CI.