# Tasks: cascade-checklistbank

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

Five chained PRs (PR #1 → PR #2a → PR #2b → PR #3 → PR #4); each targets
`develop` per AGENTS.md §4. The user has approved `size:exception` for
PR #1; PR #2a was estimated at ~420 LOC in the design forecast and is
split via work-unit commits so neither child commit exceeds the 400-line
cap. PR #4 is on a separate chain because it is gated on Pencil MCP +
`impeccable` review per AGENTS.md §5. Delivery strategy resolved by
orchestrator: `auto-chain`; no further decision required.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | CLB client + dataclass + parser (no router changes) | PR #1 | `pytest taxon/tests/test_checklistbank.py -v` → all pass | N/A (no router yet) | Remove `taxon/checklistbank.py` + `taxon/tests/test_checklistbank.py`; no other file touched |
| 2a | 9-tier resolver core walk (Biota root + 7 kingdoms + phyla + classes + orders + families + genera + species) | PR #2a | `pytest taxon/tests/test_clb_path_children.py::test_resolve_deepest_mammalia_chain -v` → 1 pass; `pytest taxon/tests/test_clb_path_children.py -k "not subphylum_collapse"` → all pass | N/A (no router yet) | Remove `taxon/api/clb_path_children.py` + the test file; no router wiring exists |
| 2b | Subphylum collapse rule (Chordata → 3 subphyla, Arthropoda → skip) | PR #2b | `pytest taxon/tests/test_clb_path_children.py -k subphylum_collapse -v` → all pass | N/A (no router yet) | Revert only the `_children_for` collapse probe + its 2–3 collapse tests; resolver core stays |
| 3 | Router swap + GBIF deletion | PR #3 | `pytest taxon/tests/ -v` → all pass; `pytest taxon/tests/test_api_clb_router.py -v` → 4 tests pass | `curl "http://localhost:8000/api/kingdoms"` → 2 items `{id:"5T6MX", name:"Biota"}` + `{id:"V", name:"Viruses"}`; `curl "http://localhost:8000/api/path-children?path=Animalia\|Chordata\|Vertebrata\|Mammalia\|Carnivora\|Felidae\|Panthera"` → 12 Panthera species | Restore `taxon/gbif.py` + 3 test files + rewire `taxon/api/router.py`; destructive PR — see proposal §Rollback Plan |
| 4 | Frontend: render Biota + subphylum | PR #4 | `vitest run frontend/tests/api.test.ts frontend/tests/Cascade.pathAware.test.tsx frontend/tests/Cascade.ui.test.tsx` → all pass | `curl "http://localhost:8000/api/kingdoms"` + browser smoke: Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → 12 species render; Arthropoda path skips subphylum slot | Revert frontend files only; backend unaffected |

## Phase 1: PR #1 — `feat(checklistbank): add CLB client and taxon parser`

Depends on: nothing (first PR in chain). Targets `develop`.
Branch: `../taxon-worktrees/cascade-checklistbank-pr1`.
LOC: ~450 (size:exception approved by user — see proposal §Risks).

Work-unit commits inside PR #1 (per `work-unit-commits` skill):

- [ ] 1.1 Create `taxon/checklistbank.py` with `DATASET_KEY = "COL2024"` (3LR comment), `CLB_BASE_URL`, `ChecklistBankTaxon` dataclass (`id`, `name`, `label_html`, `parent_id`, `count`, `child_count`, `authorship`, `rank`, `status`), and `ChecklistBankClient` with `__init__`, `get_taxon`, `get_children`, `search`, `_request`. `get_children` accepts `rank: str | None` for the subphylum probe in PR #2b.
  - Test: RED-first `taxon/tests/test_checklistbank.py` with `_StubClient` using `httpx.MockTransport`. Cover (a) `get_taxon` happy + 404 → `None`; (b) `get_children` parses `result[]`, applies `rank` query param, returns empty list when CLB returns `total:0`; (c) `search` returns ranked matches with classification breadcrumbs; (d) `_request` surfaces 4xx/5xx as `None` for 404, raise for 5xx; (e) `DATASET_KEY` constant tests; (f) parser handles missing optional fields (`label_html=None`, `count=None`).
  - Verify: `pytest taxon/tests/test_checklistbank.py -v` → all pass.
  - Rollback: delete `taxon/checklistbank.py` + `taxon/tests/test_checklistbank.py`. Router still depends on `_get_gbif_client`. Safe.
- [ ] 1.2 Verify: `ruff check taxon/checklistbank.py taxon/tests/test_checklistbank.py && ruff format --check taxon/checklistbank.py taxon/tests/test_checklistbank.py && mypy taxon/checklistbank.py` → zero errors.
- [ ] 1.3 Verify: live smoke `curl -sf "https://api.checklistbank.org/dataset/COL2024/tree" | jq '.total'` → `2`.

## Phase 2: PR #2a — `feat(checklistbank): path resolver core walk`

Depends on: PR #1 merged into `develop`. Targets `develop`.
Branch: `../taxon-worktrees/cascade-checklistbank-pr2a`.
LOC: ~280 module + ~140 tests = ~420 (slightly over budget; commit split per `work-unit-commits` keeps each child commit under 400 LOC).

Work-unit commits inside PR #2a:

- [ ] 2a.1 Create `taxon/api/clb_path_children.py` with `CASCADE_TIERS = ("biota", "kingdom", "phylum", "subphylum", "class", "order", "family", "genus", "species")`, `TIER_DEPTH` map, `PathChildrenResponse` dataclass, `TaxonRow` dataclass, `_to_taxon_row` parser. Stub `_resolve_deepest` and `_children_for` (no collapse rule yet — PR #2b fills it in; for now phylum returns next-rank hint = `"subphylum"` unconditionally).
  - Test: `taxon/tests/test_clb_path_children.py` with RED-first `test_cascade_tiers_constant` (9 elements incl. "biota" + "subphylum"), `test_tier_depth_index`, `test_to_taxon_row_parses_clb_fields`, `test_path_children_response_shape`. ~80 LOC tests.
  - Verify: `pytest taxon/tests/test_clb_path_children.py -v` → 4 pass.
  - Rollback: delete `taxon/api/clb_path_children.py` + `taxon/tests/test_clb_path_children.py`. Router not wired yet. Safe.
- [ ] 2a.2 Implement `_resolve_deepest(segments, client)` per design §Resolver Walk Algorithm: alternate `client.search(segment, rank=R)` (binds name → id) and `client.get_children(parent_id)` (finds next segment's id by name match, case-insensitive). Return deepest hit or `None` if any segment fails to bind.
  - Test: RED-first `test_resolve_deepest_biota_root_returns_biota_node`, `test_resolve_deepest_animalia_walks_one_step`, `test_resolve_deepest_mammalia_chain` (Animalia|Chordata|Mammalia → 4 segments → returns Mammalia), `test_resolve_deepest_unknown_segment_returns_none`. ~60 LOC tests.
  - Verify: `pytest taxon/tests/test_clb_path_children.py -v` → 8 pass.
  - Rollback: revert this commit alone; `_resolve_deepest` returns `None` for any non-trivial walk — module + dataclass from 2a.1 still pass tests.
- [ ] 2a.3 Implement `_children_for(current, client)` without collapse (always returns `rank=next_tier`, even when next tier is `subphylum`). Wire `list_path_children(segments, client=None)` to call `_resolve_deepest` then `_children_for`; emit `PathChildrenResponse`.
  - Test: RED-first `test_list_path_children_animalia_returns_phyla`, `test_list_path_children_felidae_returns_panthera_with_next_hint_species`, `test_list_path_children_root_biota_returns_seven_kingdoms_with_next_hint_kingdom`. ~60 LOC tests.
  - Verify: `pytest taxon/tests/test_clb_path_children.py -v` → 11 pass.
  - Rollback: revert this commit alone; 2a.1+2a.2 keep dataclass + walk.
- [ ] 2a.4 Verify: `ruff check taxon/api/clb_path_children.py taxon/tests/test_clb_path_children.py && ruff format --check . && mypy taxon/api/clb_path_children.py` → zero errors.

## Phase 3: PR #2b — `feat(checklistbank): subphylum collapse rule`

Depends on: PR #2a merged into `develop`. Targets `develop`.
Branch: `../taxon-worktrees/cascade-checklistbank-pr2b`.
LOC: ~50 collapse probe + ~200 collapse tests = ~250.

Work-unit commits inside PR #2b:

- [ ] 2b.1 Replace `_children_for`'s phylum branch with a collapse probe: when `next_rank == "subphylum"`, call `client.get_children(current.id, rank="subphylum")`; if empty, call `client.get_children(current.id, rank="class")` and emit `next_rank_hint = "order"`; if non-empty, return subphyla with `next_rank_hint = "class"`. No recursive descent (design §Subphylum Collapse Rule).
  - Test: RED-first `test_subphylum_collapse_chordata_returns_three_subphyla_with_next_hint_class`, `test_subphylum_collapse_arthropoda_returns_classes_with_next_hint_order`, `test_subphylum_collapse_empty_subphylum_and_empty_class_returns_empty_with_next_hint_order`. ~80 LOC tests.
  - Verify: `pytest taxon/tests/test_clb_path_children.py -k subphylum_collapse -v` → 3 pass.
  - Rollback: revert this commit alone; collapse probe gone, fallback to "always return subphylum" semantics.
- [ ] 2b.2 Add coverage for `_to_taxon_row` and `PathChildrenResponse` carrying `rank="subphylum"` for subphylum rows; add `test_phylum_with_subphyla_propagates_next_hint_class` and `test_phylum_without_subphyla_propagates_next_hint_order`. ~120 LOC tests.
  - Verify: `pytest taxon/tests/test_clb_path_children.py -v` → 17+ pass.
- [ ] 2b.3 Verify: `ruff check . && ruff format --check . && mypy taxon/api/clb_path_children.py` → zero errors.

## Phase 4: PR #3 — `feat(api): route cascade endpoints through ChecklistBank client`

Depends on: PR #1, PR #2a, PR #2b merged into `develop`. Targets `develop`.
Branch: `../taxon-worktrees/cascade-checklistbank-pr3`.
LOC: ~200 new tests + router swap → ~−700 net (1,200 deletions − 500 insertions).

Work-unit commits inside PR #3:

- [ ] 3.1 Wire `taxon/api/router.py`: add `_get_checklistbank_client()` dependency that returns a `ChecklistBankClient`; add a `get_roots` endpoint (`/api/kingdoms`) that calls `client.search(q="", rank="biota")` and returns Biota + Viruses (id + name + display_name + rank + next_rank_hint="kingdom"/"viruses"). Keep the existing `/api/kingdoms` URL surface — semantics change, contract widens.
  - Test: RED-first `taxon/tests/test_api_clb_router.py::test_kingdoms_returns_biota_and_viruses` (override `_get_checklistbank_client` with a stub returning 2 results). ~50 LOC tests.
  - Verify: `pytest taxon/tests/test_api_clb_router.py -v` → 1 pass.
  - Rollback: revert this commit; old `_get_gbif_client` path unchanged. Safe.
- [ ] 3.2 Rewire `/api/path-children` and `/api/species-list` from `Depends(_get_gbif_client)` + `GbifClient` to `Depends(_get_checklistbank_client)` + `ChecklistBankClient`. Bodies call `clb_path_children.list_path_children(...)`. Add RED tests: `test_path_children_resolves_mammalia_chain_via_clb`, `test_path_children_subphylum_collapse_arthropoda_via_clb`, `test_species_list_returns_panthera_species_via_clb`.
  - Verify: `pytest taxon/tests/test_api_clb_router.py -v` → 4 pass.
  - Rollback: revert this commit; router depends on GBIF again. Safe as long as 3.1 also reverts.
- [ ] 3.3 Delete `taxon/gbif.py`, `taxon/api/gbif_path_children.py`, `taxon/tests/test_gbif.py`, `taxon/tests/test_gbif_path_children.py`, `taxon/tests/test_api_gbif_router.py`. Remove `_get_gbif_client` from `taxon/api/router.py`. Verify `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"` returns zero hits.
  - Verify: `pytest taxon/tests/ -v` → all pass (no orphan imports, no shadowed symbols).
  - Rollback: NOT safe to revert alone. Must be paired with a follow-up PR that reintroduces the GBIF client + tests + rewires the router (proposal §Rollback Plan).
- [ ] 3.4 Verify: `ruff check . && ruff format --check . && mypy taxon/` → zero errors.
- [ ] 3.5 Runtime harness:
  - Start `uvicorn taxon.main:app --reload` from worktree root.
  - `curl -sf "http://localhost:8000/api/kingdoms" | jq 'length'` → `2`; first item `.name` → `"Biota"`.
  - `curl -sf "http://localhost:8000/api/path-children?path=Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera" | jq '.children | length'` → `>=12`.
  - `curl -sf "http://localhost:8000/api/path-children?path=Animalia|Arthropoda" | jq '.next_rank_hint'` → `"order"` (subphylum collapsed).

## Phase 5: PR #4 — `feat(frontend): render Biota + subphylum in the cascade UI`

Depends on: PR #3 merged into `develop`, Pencil design on `taxon.pen` audited under `impeccable` (AGENTS.md §5). Targets `develop`.
Branch: `../taxon-worktrees/cascade-checklistbank-pr4`.
LOC: ~350 (code + tests; Pencil design is a sibling-worktree artifact, not part of this PR's diff).

Work-unit commits inside PR #4:

- [ ] 4.0 (Pre-PR, in sibling worktree) Open `taxon.pen` via Pencil MCP, add one extra dropdown slot for the Biota root tier, add the "subphylum" rank label to the rank-label layer. Run an `impeccable` audit pass on the updated `taxon.pen` (hierarchy, accessibility, typography, color, motion, anti-patterns). Iterate until clean. Document the approval in `taxon/docs/design/approval-cascade-checklistbank.md` (date + sign-off). This task does NOT belong to PR #4; it must complete BEFORE PR #4 starts.
- [ ] 4.1 Update `frontend/src/api.ts`: rename `fetchKingdoms()` → `fetchRoots()`; return `{ roots: TaxonResponse[] }` shape (Biota + Viruses, each with `rank` + `next_rank_hint`). Keep `fetchPathChildren()` + `fetchSpeciesList()` signatures unchanged.
  - Test: RED-first `frontend/tests/api.test.ts`: `test_fetch_roots_returns_biota_and_viruses`, `test_fetch_roots_404_returns_not_found`, `test_fetch_path_children_unaffected`. ~50 LOC tests.
  - Verify: `vitest run frontend/tests/api.test.ts` → all pass.
  - Rollback: revert this commit; `fetchKingdoms` returns and `Cascade.tsx` keeps working against `/api/kingdoms`. Backend unaffected.
- [ ] 4.2 Update `frontend/src/components/Cascade.tsx`: change the initial fetch from `fetchKingdoms()` → `fetchRoots()`; add label inference for `"subphylum"` and `"biota"` in the rank-name capitalizer; add a `RANK_LABEL_OVERRIDES` map (case-insensitive). The reducer (`Cascade.state.ts`) is path-agnostic — no change.
  - Test: RED-first `frontend/tests/Cascade.pathAware.test.tsx`: `test_path_aware_renders_biota_dropdown_first`, `test_path_aware_subphylum_appears_for_chordata`, `test_path_aware_subphylum_collapsed_for_arthropoda`. Update `frontend/tests/Cascade.ui.test.tsx`: mock `/api/kingdoms` → `/api/roots` returning Biota + Viruses. ~150 LOC tests.
  - Verify: `vitest run frontend/tests/` → all pass.
  - Rollback: revert this commit; Cascade falls back to kingdom-as-root semantics. Backend unaffected.
- [ ] 4.3 Verify: `npm run lint && npm run typecheck && vitest run` → zero errors.
- [ ] 4.4 Runtime harness:
  - Backend running locally (PR #3 backend).
  - Browser smoke: Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → 12 species render (8 dropdowns).
  - Browser smoke: Biota → Animalia → Arthropoda → Insecta → Lepidoptera → Bombycidae → Bombyx (7 dropdowns; subphylum slot collapsed — only 7 tiers visible).

## Phase 6: Post-merge (after PR #3 green)

- [ ] 6.1 Create `learn-es/2026-08-14-cascade-checklistbank.md` with sections: What / How / Where / Why / How it works / Workflows. Trigger: PR #3 merges green to `develop`.
- [ ] 6.2 Confirm `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"` returns zero hits in `develop`.

## Conventions

- Worktrees at `../taxon-worktrees/cascade-checklistbank-pr{1,2a,2b,3,4}` branched from `develop`.
- Conventional commits in English; no AI attribution. Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`.
- Strict TDD per `openspec/config.yaml`: every production task has a RED-first test before GREEN.
- Pencil + `impeccable` gate applies to PR #4 only — backend chain (#1 → #2a → #2b → #3) is unblocked.
- Spanish mirror of this file: `documents-es/openspec/changes/cascade-checklistbank/tasks-es.md` (created at write time, faithful translation, neutral/professional register).