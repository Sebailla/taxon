## Exploration: cascade-checklistbank

### Current State

The cascade backend currently serves three path-aware endpoints (`GET /api/kingdoms`, `GET /api/path-children`, `GET /api/species-list`) backed by the GBIF Species API (`https://api.gbif.org/v1`). The implementation landed in three PRs that merged to `develop`:

- `f958aa1` — `feat(gbif): add GBIF client and taxon parser` (`taxon/gbif.py`).
- `aedbaa0` — `feat(gbif): route cascade endpoints through GBIF client` (`taxon/api/router.py` wired through `Depends(_get_gbif_client)`).
- `d51c50a` — `feat(gbif): add path resolver with rank-aware tier selection` (`taxon/api/gbif_path_children.py`).
- Fix `4bed7ff` — added `class` to `CASCADE_TIERS`.
- Cleanup `222efe3` — reformat.

**Smoke test failure (reason for pivot).** The live dev server returned only 4 phyla under `Animalia` (Arthropoda, Chordata, Cnidaria, Mollusca) — GBIF's backbone is incomplete relative to the user's domain. ChecklistBank's COL2024 release exposes 34 real phyla under `Animalia`, plus the previously missing root (`Biota`) and the subphylum tier that GBIF collapses. The user has confirmed the pivot to CLB.

**Code shape that needs to change:**

- `taxon/gbif.py` — `GbifClient` (4 methods: `get_taxon`, `get_children`, `search`, `_request`), `GbifTaxon` dataclass (16 fields keyed by integer `key`/`nub_key`), `GBIF_BASE_URL = "https://api.gbif.org/v1"`. Total 236 lines.
- `taxon/api/gbif_path_children.py` — `list_path_children` resolver (326 lines). Key contracts:
  - `CASCADE_TIERS = ("kingdom", "phylum", "class", "order", "family", "genus", "species")` (7 tiers).
  - `_resolve_deepest` walks the path via `_search_under_parent` using `higherTaxonKey` + `rank` filters.
  - Filters children to `cascade_ranks_lower = {r.lower() for r in RANK_TO_DISPLAY_LEVEL}`.
  - `next_rank_hint` is a hard-coded 7-element dict mapping GBIF rank → next rank.
  - `_to_taxon_row` bridges GBIF rows to the legacy `TaxonRow` (the cascade UI's input contract).
- `taxon/api/router.py` — three cascade endpoints (`/kingdoms`, `/path-children`, `/species-list`) wired through `Depends(_get_gbif_client)`. `/kingdoms` uses `gbif.search(name="", rank="KINGDOM", accepted_only=True, limit=100)` and dedupes by `nub_key`. Tests override `_get_gbif_client` via `app.dependency_overrides[_get_gbif_client] = lambda: client` to inject `_StubClient`.
- `taxon/tests/test_gbif.py` (257 lines), `taxon/tests/test_gbif_path_children.py` (409 lines), `taxon/tests/test_api_gbif_router.py` (335 lines) — all use `httpx.MockTransport` with `_StubClient` to mimic GBIF.
- `frontend/src/components/Cascade.tsx` (359 lines) + `frontend/src/components/Cascade.state.ts` (175 lines) — path-driven reducer, one dropdown per non-leaf response, `nextRankHint` used to label the next dropdown. **The cascade does not assume a fixed tier count** — it renders N dropdowns where N depends on how many non-leaf snapshots the backend returns.
- `frontend/src/api.ts` — `fetchKingdoms()`, `fetchPathChildren()`, `fetchSpeciesList()` typed wrappers.
- `taxon.pen` — Pencil design file for the cascade UI (encrypted; accessed only via Pencil MCP).

**What the live CLB API returns (verified via curl):**

- `GET /dataset/COL2024/tree` → `{"total":2, "result":[{id:"5T6MX", rank:"unranked", name:"Biota", childCount:7}, {id:"V", rank:"unranked", name:"Viruses", childCount:31}]}`.
- `GET /dataset/COL2024/tree/5T6MX/children?limit=10` → 7 kingdoms under Biota (Animalia=N, Archaea=R, Bacteria, Chromista=C, Fungi=F, Plantae=P, Protozoa=Z).
- `GET /dataset/COL2024/tree/N/children?limit=100` → 34 phyla under Animalia (Acanthocephala, Annelida, Arthropoda, … Xenacoelomorpha).
- `GET /dataset/COL2024/tree/CH2/children?limit=100` → 3 subphyla under Chordata (Cephalochordata, Tunicata, Vertebrata).
- `GET /dataset/COL2024/tree/8V4V3/children` → 2 infraphyla under Vertebrata (Agnatha, Gnathostomata).
- `GET /dataset/COL2024/tree/BMGVD/children` → 2 subclasses under Mammalia (Prototheria, Theria).
- `GET /dataset/COL2024/nameusage/search?q=Panthera&rank=genus&limit=5` → returns the genus with a `classification[]` array containing every ancestor's id/name/rank (so the resolver can find ancestors without per-rank `higherTaxonKey` calls).
- `GET /dataset/COL2024/nameusage/search?q=&rank=kingdom&limit=20` → 18 hits (some duplicates the resolver must dedupe by ID).

**Shape differences (GBIF → CLB):**

| Concern | GBIF | CLB |
| --- | --- | --- |
| ID type | `int` (e.g. 1, 44, 9703) | opaque `str` (e.g. "5T6MX", "CH2", "8V4V3") |
| Canonical key | `nubKey` (integer) | none — `id` is the only stable key per dataset |
| Root | direct 8 kingdoms | Biota (unranked) → 7 kingdoms; Viruses (unranked) → 31 realms |
| Tier granularity | 6 main ranks (no subphylum) | real subphylum tier (3 subphyla under Chordata) |
| Search filter | `?higherTaxonKey=` | not supported — must walk children by `id` |
| Field names | `canonicalName`, `scientificName`, `parentKey`, `numDescendants`, `kingdom`/`phylum`/`order`/`family`/`genus`/`species` (breadcrumbs) | `name`, `labelHtml`, `parentId`, `count` (descendants), `childCount` (direct children), `authorship`, `rank`, `status` |
| Breadcrumb | pre-resolved kingdom/phylum/… on the row | `classification[]` array on search hits only — `/tree/{id}/children` does NOT include ancestors |
| Search endpoint | `/v1/species/search` | `/dataset/COL2024/nameusage/search` |
| Children endpoint | `/v1/species/{key}/children` | `/dataset/COL2024/tree/{id}/children` |
| Taxon detail | `/v1/species/{key}` | `/dataset/COL2024/taxon/{id}/info` (heavier — only used when needed) |

**Issue #32 status.** Closed. Its body described the GBIF migration (3 slices) — the approach the user picked at the time. The new change is a *pivot* (different API + different cascade shape), so it gets a fresh change name `cascade-checklistbank` and a new issue, not a re-use of #32.

**Operational constraints inherited from Engram `sdd-init/taxon` (observation #3566):**

- Every OpenSpec artifact MUST have a Spanish mirror under `/documents-es/openspec/changes/cascade-checklistbank/` with the `-es` suffix.
- Conventional commits (`type(scope): description`), no AI attribution, English.
- UI design MUST be authored in Pencil MCP and audited under `impeccable` BEFORE frontend code lands.
- Worktree from `develop` at `../taxon-worktrees/cascade-checklistbank`.
- All PRs target `develop`. After merge: `/learn-es/2026-08-14-cascade-checklistbank.md`.
- Branch-pr skill: taxon repo does NOT use `status:approved` or `type:*` labels — use the real flow (PR #29/#30/#31 as reference).

### Affected Areas

- `taxon/gbif.py` — replace the GBIF client. Same shape (stateless HTTP client + dataclass), new field names, string keys. Rename to `taxon/checklistbank.py` (preferred) or keep the module name and replace the contents (cheaper diff). The router's `Depends(_get_gbif_client)` should be renamed in lockstep.
- `taxon/api/gbif_path_children.py` — rewrite the resolver. CLB's search does NOT support `higherTaxonKey`, so the walk must use `/tree/{id}/children` plus name-match. Also: `next_rank_hint` mapping changes (Biota → kingdom; kingdom → phylum; phylum → subphylum/class; subphylum → class; class → order; …). Renaming to `taxon/api/clb_path_children.py` is consistent with the module rename but doubles the diff; cheaper alternative is to keep the module name and update the body.
- `taxon/api/router.py` — three endpoint bodies change. `/api/kingdoms` is now CLB's 7 kingdoms under Biota (or includes Biota + kingdoms). The dependency override `_get_gbif_client` must be renamed (or aliased).
- `taxon/api/schemas.py` — `PathChildrenEnvelope`, `TaxonResponse`, `SpeciesListItem` are unchanged (they're the public contract). No schema change needed unless we expose Biota as a row.
- `taxon/tests/test_gbif.py` — replace with `test_checklistbank.py`. New `_StubClient` mocks `/dataset/COL2024/tree/{id}/children` and `/dataset/COL2024/nameusage/search`.
- `taxon/tests/test_gbif_path_children.py` — replace with `test_clb_path_children.py`. New tier constants (8 tiers incl. Biota). Tests for subphylum bucket (parent: phylum → next_rank_hint = "subphylum" or "class").
- `taxon/tests/test_api_gbif_router.py` — replace with `test_api_clb_router.py`. New mock shapes (string IDs, `parentId`/`childCount`/`labelHtml`).
- `frontend/src/api.ts` — `fetchKingdoms()` either becomes `fetchRoots()` (returns Biota + Viruses) or stays as `fetchKingdoms()` and only returns kingdoms. The cascade's first dropdown displays "Biota" → kingdoms (8 options). This needs a product call.
- `frontend/src/components/Cascade.tsx` — must handle Biota as a real tier in the path (Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → species). The reducer's path-key logic is path-agnostic, so the only change is in label inference and how the root fetch returns its rows.
- `frontend/src/components/Cascade.state.ts` — `nextRankHint: string | null` is already rank-agnostic. No structural change needed if the backend returns "subphylum" as the next hint.
- `frontend/tests/Cascade.pathAware.test.tsx`, `frontend/tests/Cascade.ui.test.tsx`, `frontend/tests/api.test.ts` — fixtures update. Mock paths now include Biota.
- `taxon.pen` (encrypted) — Pencil MCP design file. The cascade visual gains one extra dropdown (Biota) and the subphylum tier label. **Must be updated under `impeccable` audit BEFORE frontend code lands**, per AGENTS.md §5.
- `openspec/changes/cascade-checklistbank/` — proposal.md, design.md, tasks.md, exploration.md, plus specs deltas.
- `documents-es/openspec/changes/cascade-checklistbank/` — Spanish mirrors (`-es` suffix).
- `learn-es/2026-08-14-cascade-checklistbank.md` — post-merge learning entry.

### Approaches

1. **Full migration: replace GBIF client, resolver, and router endpoints with CLB equivalents.** Drop the `taxon/gbif.py` module (rename → `taxon/checklistbank.py`); keep the cascade UI's tier-rendering logic unchanged (it was already path-agnostic).
   - Pros: single source of truth; deletes 4 files of now-dead GBIF plumbing (`gbif.py`, `test_gbif.py`, `test_gbif_path_children.py`, `test_api_gbif_router.py`); tests stay honest. The Cascade UI gets Biota + subphylum "for free" because it renders N dropdowns from snapshots, not a fixed tier count.
   - Cons: every GBIF-named symbol in the codebase must be renamed (`GbifClient` → `ChecklistBankClient`, `GbifTaxon` → `ChecklistBankTaxon`, `_get_gbif_client` → `_get_checklistbank_client`, etc.). The Pencil design gains an extra tier slot — a small but real UI design pass.
   - Effort: Medium (3 PRs — see chain strategy below).

2. **Hybrid: keep GBIF client + add CLB adapter.** Keep `taxon/gbif.py` for legacy endpoints; add `taxon/checklistbank.py` alongside. The router picks one based on a feature flag or query param. The frontend keeps the same GBIF contract for the breadth of users and exposes CLB only behind `?source=clb`.
   - Pros: low blast radius; rollback is a flag flip; the legacy 8-kingdom surface still works.
   - Cons: doubles the test surface; two sources of truth; the user said "GBIF backbone is incomplete, pivot" — keeping GBIF as a fallback defeats the purpose. Two APIs = two cascading behaviors to keep consistent.
   - Effort: High (3-4 PRs of plumbing, plus an ongoing maintenance burden).

3. **Parallel CLB-only endpoints, keep GBIF everywhere else.** Add `/api/clb/path-children` and `/api/clb/kingdoms`; mount them under a new prefix. The frontend's `fetchKingdoms()` and `fetchPathChildren()` flip to the new URLs. The old `/api/path-children` stays GBIF-backed for any consumer that depends on the previous behavior.
   - Pros: same as Hybrid (rollback) but more isolated.
   - Cons: the user has no consumer that depends on GBIF; the legacy endpoints become dead code. The `/api/clb/...` URL surface is awkward.
   - Effort: Medium-High (3-4 PRs).

### Recommendation

**Approach 1 (full migration).** Replace GBIF with CLB end-to-end. The codebase has no GBIF consumer besides the cascade router; hybrid or parallel approaches leave dead code and a second source of truth. The Cascade UI's path-agnostic design (one dropdown per non-leaf snapshot, `nextRankHint` labeling) absorbs Biota + subphylum with no UI logic change — only the Pencil design gains a slot.

**Chain strategy — 3 PRs (within the 400-line budget):**

- **PR #1 — `feat(checklistbank): add CLB client and taxon parser`** (~250 lines). New `taxon/checklistbank.py` (~200 lines) + `taxon/tests/test_checklistbank.py` (~250 lines, 9-10 RED-first tests). Mirrors the shape of the existing `taxon/gbif.py` + `taxon/tests/test_gbif.py` so reviewers familiar with the GBIF slice can compare side-by-side.
- **PR #2 — `feat(checklistbank): path resolver with Biota root + subphylum tier`** (~400 lines). New `taxon/api/clb_path_children.py` (~280 lines, replaces `gbif_path_children.py`) + `taxon/tests/test_clb_path_children.py` (~350 lines, 11-12 tests including Biota root, subphylum bucket, Chordata → Vertebrata → Mammalia chain). The 8-tier tuple becomes `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` — subphylum is the new tier.
- **PR #3 — `feat(api): route cascade endpoints through ChecklistBank client`** (~350 lines). Wire `taxon/api/router.py` to `Depends(_get_checklistbank_client)`; update `taxon/tests/test_api_checklistbank_router.py` (350 lines, 4 tests); delete `taxon/gbif.py` + `taxon/tests/test_gbif.py` + `taxon/tests/test_gbif_path_children.py` + `taxon/tests/test_api_gbif_router.py` (~1,200 lines of deletions). After this PR, the GBIF code is fully removed.

**Then a separate UI slice (PR #4, outside the SDD change if it exceeds the budget):**

- **PR #4 — `feat(frontend): render Biota + subphylum in the cascade UI.** Pencil design pass first under `impeccable`. Update `frontend/src/components/Cascade.tsx` (label inference for "subphylum" and "biota"), update `frontend/src/api.ts` (`fetchKingdoms` becomes `fetchRoots` returning Biota + Viruses), update test fixtures. This is a chained PR that lands after PR #3 once the backend is green.

**Estimated total diff (excluding deletions):** ~1,400-1,600 lines added across 3 backend PRs, plus ~150-200 lines frontend in PR #4. Each PR stays under the 400-line budget if commits are split per `work-unit-commits` skill (parser + client in one commit; tests + parser in the next; router swap + test deletions in the third).

**Self-chained base.** PR #1 → PR #2 → PR #3 → PR #4 chain from `develop`. The Pencil design for PR #4 lives in a sibling worktree from `develop` so it doesn't block the backend chain.

### Risks

- **CLB rate limiting / availability.** CLB is a public read-only endpoint with no auth, but it does enforce rate limits (5-10 req/s per IP). The cascade's worst case (Animalia → phyla → Chordata → subphylum → class → subclass → …) can be 8-9 requests deep per dropdown click. Recommend a per-request TTL cache (60-120s) on the resolver. Effort: small, can be a follow-up PR if load testing shows the need.
- **Subphylum tier breaks paths that previously worked.** A user with a saved URL `path=Animalia|Chordata|Mammalia|Carnivora|Felidae|Panthera` (GBIF shape) would now need `path=Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera` (CLB shape — subphylum Vertebrata inserted). The breadcrumb helper already strips a leading Biota; subphylum insertion is a *deeper* path change, not a leading one. Mitigation: keep the resolver tolerant of a missing subphylum (treat subphylum as optional; if `Chordata` → `Vertebrata` returns no match, fall back to `Chordata` → `Mammalia` directly using `/tree/{id}/children?rank=class`).
- **Pencil design + impeccable review gates the UI.** Per AGENTS.md §5, PR #4 cannot land before the design is reviewed. This is a serial dependency that adds 1-2 days to the frontend slice but is non-negotiable.
- **Subphyla under most phyla are absent.** CLB's tree has 3 subphyla under Chordata but 0 under Arthropoda (the most-speciose phylum). The "subphylum" tier will be empty for most chains — the resolver must gracefully show "no subphyla, here are classes" without breaking the reducer. Recommendation: when a phylumn has 0 subphylum children, treat phylum as the parent for the *next* tier (i.e. return `next_rank_hint = "class"` instead of `next_rank_hint = "subphylum"` for an empty subphylum tier).
- **Test fixtures will need updating.** The 257 + 409 + 335 test lines for GBIF cascade shapes cannot be reused for CLB shapes (string IDs, new field names). Net effect: ~1,000 lines of test fixture rewriting. Mitigation: the test contracts (path walks to leaf, `next_rank_hint` propagates, 404 on bad segment) are the same — only the fixture shapes change.
- **Live API can drift.** CoL releases a new dataset annually (COL2025 expected). The resolver must use a magic key (the brief mentions `3LR` for latest, `COL2024` for the annual release) and the proposal should pin the dataset key for reproducibility while documenting how to upgrade.
- **GBIF code as leftover.** PR #3 deletes `taxon/gbif.py`, the three test files, and the `_get_gbif_client` dependency override. Reviewers must confirm the dead code is gone, not just shadowed.

### Ready for Proposal

Yes, with three confirmations to record in the proposal:

1. **Tier list** — `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` (9 tiers). The subphylum tier is shown when present, hidden otherwise (the resolver emits `next_rank_hint = "class"` for a phylum with no subphylum children).
2. **Root tier behaviour** — the first dropdown shows Biota + Viruses as 2 options (not 8 kingdoms directly); picking Biota reveals its 7 kingdoms in the next dropdown. The previous behavior of "kingdom dropdown = 8 options" is gone.
3. **Dataset key pinning** — pin to `COL2024` for the first release; document the `3LR` magic key path for a future upgrade.

The orchestrator should tell the user that the proposal phase can launch with those three decisions baked in, and that PR #4 (frontend) is a separate chain because it depends on Pencil + impeccable review.

The orchestrator should NOT proceed to proposal without confirming these three decisions with the user first — they are user-facing cascade shape choices that the proposal cannot make alone.