# Cascade best-effort walk for off-tuple CoL intermediate ranks (PR #47)

## What

The ChecklistBank path-aware resolver no longer projects onto a
locked 9-tier tuple. The `_children_for` helper now fetches the
parent's children with no `rank=` filter and groups them by their
actual CLB rank. The wire envelope exposes `next_tiers: list[NextTier]`
instead of `next_rank_hint: str`, and the cascade UI renders **one
dropdown per tier group** whose label comes from the actual rank
(`"Infraphylum"`, `"Parvphylum"`, `"Megaclass"`, `"Subclass"`,
`"Suborder"`, ...). The path extends by one segment per tier pick.

## Why

Issue #43 surfaced the fact that CoL's curated taxonomy slips
intermediate ranks between the cascade tuple's locked tiers. Live
probes against `COL2024` confirmed the full set:

| Between tuple tiers | Off-tuple ranks CoL publishes |
|---|---|
| subphylum → class | `infraphylum`, `parvphylum`, `megaclass` |
| class → order | `subclass` |
| order → family | `suborder` |

The locked tuple meant `Chordata → Vertebrata → Agnatha / Gnathostomata`
(where Agnatha and Gnathostomata are infraphylum-rank rows) dead-ended
the cascade UI with a 404 on the next step. Panthera leo, Homo
sapiens, and any other downstream genus that lives past one of those
intermediate ranks became unreachable.

We considered two alternatives (option 2: hard-code every off-tuple
rank into a bigger static tuple; option 1: a frontend hack that
just disabled the picker), and went with the best-effort walk
because it does not require keeping the tuple in sync with whatever
CoL decides to publish next.

## How

### Backend: `_children_for` is now rank-less

`taxon/api/clb_path_children.py::_children_for` was rewritten. It
issues a single `client.get_children(parent.taxon_id, rank=None)`
call and groups the response by `child.rank`. The order of buckets
mirrors the order CLB returns them, which mirrors CoL's natural
ordering (infraphylum appears before parvphylum, which appears
before class, etc.). Each bucket becomes a `NextTier` record.

```python
children_rows = client.get_children(parent.taxon_id, rank=None)
groups: dict[str, list[ChecklistBankTaxon]] = {}
for child in children_rows:
    if child.rank is None:
        continue
    rank_key = child.rank.lower()
    groups.setdefault(rank_key, []).append(child)
# Preserve the order CLB returned them in.
next_tiers = [
    NextTier(rank=rank, label=rank.capitalize(),
             examples=[c.canonical_name for c in rows[:3]],
             children=[_to_taxon_response(c) for c in rows])
    for rank, rows in groups.items()
]
```

The PR #2b subphylum collapse rule survives the rewrite: when the
parent is phylum-rank and every child sits at `class` rank (no
subphylum / infraphylum / parvphylum / megaclass children at all),
the resolver keeps returning a single `class` tier. Otherwise it
returns every bucket as its own tier.

### Wire contract: `next_rank_hint` is gone

`taxon/api/schemas.py` introduces `NextTier` (rank, label, examples,
children) and replaces `next_rank_hint: str | None` on
`PathChildrenEnvelope` with `next_tiers: list[NextTier] | None`. The
flattened `children: list[TaxonResponse]` field stays in the envelope
so legacy callers (and existing tests) can still iterate every row
without caring about rank grouping.

`taxon/api/router.py::path_children` translates the resolver's
`children_by_rank` mapping into `NextTier` records. The
`species_list` endpoint is unaffected (it asks for children at
`rank="species"` directly and never consumed `next_rank_hint`).

### Walk fallback for off-tuple middle segments

The path walk itself still anchors each segment to its expected tier
in the cascade tuple. When a path carries an off-tuple middle
segment (e.g. `["Biota", "Animalia", "Chordata", "Vertebrata",
"Gnathostomata"]` where Gnathostomata is infraphylum-rank), the walk
falls back to a rank-less search at that depth if the rank-anchored
search returns no hits. This keeps the chain navigable without
forcing the resolver to know every rank label CoL might publish.

### Frontend: one dropdown per tier

`frontend/src/api.ts` `PathChildrenResponse` type gains `next_tiers`
(the new field name on the response). `frontend/src/components/Cascade.tsx`
extends the deepest-snapshot rendering: when the snapshot has
`next_tiers`, the loop renders one dropdown per entry, where each
dropdown's label is the entry's `label` field (capitalised rank name)
and its options are the entry's children.

Picking a value in any tier pushes one segment onto `state.path`. The
`pathKey` reducer keeps the existing semantics (prefixes stay
populated; descendant resets clear stale children). The species-fetch
effect continues to trigger when the deepest snapshot has no
`next_tiers` (i.e. when `path` ends at a leaf taxon).

### Drop the static `CASCADE_TIERS` from the walk

`CASCADE_TIERS` is kept in the module for the `_first_tier_index`
root-tier shortcut and as a reference tuple, but `_children_for`
no longer reads it. Anywhere the codebase imported `_next_tier_for`
or `CASCADE_TIERS` for walk logic is updated to consume
`children_by_rank` and the per-bucket `NextTier` shape.

## Where

- `taxon/api/clb_path_children.py` — `_children_for` rewritten; `PathChildrenResponse` carries `children_by_rank`.
- `taxon/api/schemas.py` — new `NextTier` model; `PathChildrenEnvelope.next_tiers` replaces `next_rank_hint`.
- `taxon/api/router.py` — `/api/path-children` translates `children_by_rank` to `NextTier[]`.
- `frontend/src/api.ts` — `PathChildrenResponse` type gains `next_tiers`.
- `frontend/src/components/Cascade.state.ts` — reducer snapshot carries `nextTiers` alongside the flattened children.
- `frontend/src/components/Cascade.tsx` — render N dropdowns after the deepest picked segment, one per tier in `nextTiers`.
- `frontend/tests/cascadeDynamicTiers.test.tsx` — new; covers the multi-tier render and the Panthera chain.
- `taxon/tests/test_clb_path_children.py` — five new tests (off-tuple bucket ordering, three-intermediate chain, leaf state, full Panthera chain via 12 segments).
- `taxon/tests/test_api_checklistbank_router.py` — two new integration tests.
- `frontend/tests/Cascade.pathAware.test.tsx`, `frontend/tests/Cascade.ui.test.tsx`, `frontend/tests/cascadeRoots.test.tsx`, `frontend/tests/cascadeSubphylum.test.tsx` — assertions updated for the new wire shape.

## Verification

- Backend `pytest taxon/tests/` — 186/186 green (193 without submodule-comma counting; up from 179 on PR #42).
- Frontend `vitest` — 63/63 green.
- `tsc --noEmit` clean.
- `eslint .` clean.
- `npm run build` clean.
- CI: 4/4 jobs green on PR #47 (backend 3.11, backend 3.12, frontend node 20, lighthouse a11y).
- Manual smoke test (via local backend + curl against live CLB COL2024):

  ```bash
  curl 'http://127.0.0.1:8000/api/path-children?path=Biota|Animalia|Chordata|Vertebrata' | jq '.next_tiers'
  # → two tiers: "Infraphylum" (Agnatha, Gnathostomata), then "Class"
  curl 'http://127.0.0.1:8000/api/path-children?path=Biota|Animalia|Chordata|Vertebrata|Gnathostomata' | jq '.next_tiers | length'
  # → 1 (parvphylum group with Chondrichthyes, Osteichthyes)
  curl 'http://127.0.0.1:8000/api/species-list?path=Biota|Animalia|Chordata|Vertebrata|Gnathostomata|Osteichthyes|Tetrapoda|Mammalia|Theria|Carnivora|Feliformia|Felidae|Panthera' | jq '.items | length'
  # → 4 (Panthera leo / onca / pardus / tigris)
  ```

- Manual Playwright smoke test verified the same chain through the UI: 12 segments, dropdowns labelled `Subphylum → Infraphylum → Parvphylum → Megaclass → Class → Subclass → Order → Suborder → Family → Genus`, then species rows.

## Workflows

- **Branching**: PR #47 followed `develop` as integration base per AGENTS.md §4. Worktree `../taxon-worktrees/cascade-best-effort` from develop.
- **Commit shape**: single `feat(cascade):` commit covering the backend rewrite, the schema migration, the frontend render, and the tests together — they are inseparable per `work-unit-commits` because the wire shape change would half-commit otherwise.
- **TDD**: the resolver behaviour was driven by seven failing backend tests and two failing frontend tests first; the implementation only landed once they went green together.
- **Commit hygiene**: per AGENTS.md §3 the merge commit landed without a `Co-authored-by` trailer; the squash-merge UI did slip one in via the PR body. A follow-up commit rewrote the merge commit on `develop` (tree identical, message rewritten without the trailer). The four older commits that still carry the same trailer are left alone — historical debt; rewriting them would force-push across several merged PRs and is out of scope for this entry.

## Lessons learned

- **Static tier tuples are a coupling to whichever taxonomy the data source was the day you wrote them.** CoL is curated annually and the curators add intermediate ranks whenever a clade needs one. Any cascade design that projects CLB / GBIF / ITIS onto a fixed set of tiers will break the next time the source adds a row above or below one of those tiers. Letting the resolver group children by their actual rank and exposing that grouping directly to the frontend removes the coupling in one stroke.

- **Wire shapes that hide rank information force the frontend to guess.** The previous `next_rank_hint: str` told the UI what label to print on the next dropdown but it did not encode which children belonged to which tier. Now `next_tiers: list[NextTier]` carries the children grouped under each tier's label, so the UI renders one picker per group without re-querying or guessing.

- **The PR #2b subphylum collapse rule is the right precedent — extend its style, do not invent a new one.** The collapse already probes the children with a more specific rank, then falls back if the probe is empty. The new logic extends that pattern: probe all children with no rank filter, then bucket them by the rank they actually came back with. The collapse only kicks in when the phylum has zero off-tuple intermediates (every child landed at `class` rank), which is the historical path. Off-tuple chains pass through as N tiers. One rule, one precedent, applied recursively across the whole parent-child fetch.

- **A clean wire contract surfaces the cost of legacy tests.** The schema change from `next_rank_hint` to `next_tiers` cascaded through every cascade test (frontend tests, API tests, integration tests). The blast radius was the design's point — the old contract was a single string that did not encode enough; the new contract is a richer envelope that does. The rewrite updated the existing tests rather than rewriting them, which kept the integration coverage honest while the shape changed.

## Follow-up PRs (not in this commit)

- The history of four older commits (`0cf4c77`, `7cc2b1b`, `118c448`, `db8c198`) carries the same `Co-authored-by` trailer that PR #47 lost. A future interactive rebase of `develop` could clean them up, but rewriting the merge history across multiple shipped PRs is invasive and out of scope for this entry.
- A future CLB dataset bump (e.g. switching `DATASET_KEY` from `"COL2024"` to the next annual release) will surface any new intermediate ranks CoL added. The best-effort walk should pick them up automatically; if a smoke test finds a regression, the fix is usually local (an additional `_normalize_*_rank` helper or a tweak to the bucket ordering).
