# Design: breadcrumb-dinamico

## Technical Approach

New `GET /api/{path}/taxon-links` resolves a 1–7 segment cascade path via `resolve_path_by_display_level` and reuses `build_search_links` to emit the same search-source substitution the species-links endpoint produces. Frontend turns `Breadcrumb` segments into `<button>`s, drops the `resolved !== null` gate in `App.tsx`, and adds a panel keyed by `path.join("|")` whose fetch aborts on segment change or species resolution (last-clicked wins). Maps to `taxon-breadcrumb-links` spec + deltas for `species-search-links` / `taxonomy-hierarchy`.

## Architecture Decisions

| # | Choice | Tradeoff | Decision |
|---|--------|----------|----------|
| 1 | New backend endpoint vs frontend substitution | Pin substitution server-side; preserves `species-search-links` invariant; avoids shipping template URLs | New endpoint (proposal Option a) |
| 2 | `{path:path}` capture vs slash-separated | Matches `fetchPathChildren` / `fetchSpeciesList` convention | `{path}` with `\|` join |
| 3 | Reuse `SpeciesLinks` for per-taxon grid | One renderer, one a11y test surface | Reuse `<SpeciesLinks links={...} />` |
| 4 | One panel keyed by path vs two parallel | "Last-clicked wins" avoids duplication; spec allows it | Single panel |
| 5 | Breadcrumb visible whenever `path.length > 0` | Required by `taxonomy-hierarchy` delta | Drop `resolved !== null` gate |
| 6 | `App.tsx` tracks cascade path via `useState` | Path is the only mid-cascade state App needs; `Cascade` owns its own reducer | New `useState<string[]>` |
| 7 | Per-panel `AbortController` keyed by path | Races bounded; matches `Cascade.tsx` | One `useEffect` per panel change |
| 8 | Field order `taxon, links` in `TaxonLinksResponse` | Matches user mental model | `taxon` before `links` |
| 9 | Hard cap `len(path) ≤ 7` | Off-tuple intermediates could inflate breadcrumb | Reject `len > 7` with 422 |

## Data Flow

```
[ click segment N ] → Breadcrumb onSelect(trail.slice(0, N+1))
  → App: setBreadcrumbPath + useEffect keyed by path.join("|")
  → fetchTaxonLinks → GET /api/{path}/taxon-links
      router: len>7 → 422; resolve_path_by_display_level →
      build_search_links(taxon.name, templates); 404 if unresolved
  → ApiResult<TaxonLinksResponse> → setBreadcrumbLinks(data)
  → <aside>: <Breadcrumb /> + <SpeciesLinks links={...} />
  → species click → setResolved + setSpeciesLinks (clears breadcrumb panel)
"last clicked wins"
```

## File Changes

- **Backend modify**: `taxon/api/router.py` (add `GET /{path:path}/taxon-links` after `/kingdoms`/`/path-children`; reuse `resolve_path_by_display_level` + `load_templates` + `build_search_links`), `taxon/api/schemas.py` (add `TaxonLinksResponse{taxon, links}`; export from `__all__`).
- **Frontend modify**: `frontend/src/api.ts` (add `TaxonLinksResponse` + `fetchTaxonLinks`), `Breadcrumb.tsx` (add `onSelect?: (path: string[]) => void`; segments → `<button type="button">`; keep chevron + `font-mono` + `bg-surface`), `App.tsx` (new `cascadePath` state; `breadcrumbLinks` + `breadcrumbStatus`; `useEffect` w/ `AbortController`; drop `resolved` gate; one `<aside>` toggling species-links ↔ breadcrumb-links). **Reuse**: `SpeciesLinks.tsx` (none).
- **Tests create**: `Breadcrumb.dynamic.test.tsx` (click → `onSelect(trail.slice(0, idx+1))`; keyboard; `aria-current`), `App.taxonLinks.test.tsx` (panel state + `AbortController` races), `api.taxonLinks.test.ts` (`fetchTaxonLinks` 200/404/`%7C`), `test_router_taxon_links.py` (200+shape; 1/2/7-seg; 404+422; substitution vs `templates.md`).
- **Docs create**: `documents-es/openspec/changes/breadcrumb-dinamico/design-es.md` (Spanish mirror).

## Interfaces / Contracts

**Backend — `taxon/api/schemas.py`**: `TaxonLinksResponse(_ORMBase)` with `taxon: TaxonResponse`, `links: list[SearchLinkItem]`; appended to `__all__`.

**Backend — `taxon/api/router.py`**: new `GET /{path:path}/taxon-links` (registered after `/kingdoms` / `/path-children`). Validate `len(segments) ∈ [1, 7]` → `HTTPException(422)` else. Walk via `resolve_path_by_display_level(session, segments)` → `NotFoundError(f"taxon not found: {segments[-1]!r}")` if `None`. Substitute via `build_search_links(taxon_row.name, load_templates(_TEMPLATES_PATH))`. Payload `{ "taxon": TaxonResponse, "links": [13 items in templates.md order] }`. Sample bodies match species-links shape (no `species` field; just `taxon`).

**Frontend — `frontend/src/api.ts`**: `TaxonLinksResponse` interface + `fetchTaxonLinks(pathSegments, init)` mirroring `fetchSpeciesList` — `path = pathSegments.map(encodeURIComponent).join("|")`, then `apiGet<TaxonLinksResponse>(\`/${path}/taxon-links\`, init)`.

**Frontend — `Breadcrumb` prop**: `onSelect?: (path: string[]) => void`. `App.tsx` calls `onSelect(trail.slice(0, idx + 1))` per button; deepest segment carries `aria-current="true"`.

**Frontend — `App.tsx` state**: `cascadePath: string[]` via `useState`; `breadcrumbLinks: BreadcrumbLinksState | null` (`{status: "idle"; data} | {status: "loading"} | {status: "error"}`). `useEffect` keyed by `cascadePath.join("|")` + per-panel `AbortController`; abort in cleanup. Existing `setResolved` resets `breadcrumbLinks` (last-clicked wins). `cascadePath` updates via new `path:change` window event dispatched by `Cascade.tsx`'s `set-path` reducer consumer.

## Testing Strategy

Backend (`pytest`): shape + 1/2/7-seg paths + 422 + 404; substitution byte-equality vs `templates.md` per template; canonical-name (not `display_name`); stability across consecutive requests; no `/links` regression. Frontend component (`vitest`): click → `onSelect(trail.slice(0, idx+1))`; keyboard Enter/Space; `aria-current`; no-op default. Frontend integration (`vitest`): species-click clears breadcrumb panel; segment-click clears species panel; `AbortController` cancels stale fetch. Frontend client: `fetchTaxonLinks` 200/404/`%7C`. Accessibility (`vitest-axe`): button names, `aria-current`, no duplicate landmarks. **Strict TDD**: every task writes test file first (RED), asserts failure, implements minimum (GREEN), refactors.

## Threat Matrix

N/A — no shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary changed. Only network surface is one new HTTP route served by the existing FastAPI app; existing `APIRouter` + `NotFoundError` / `HTTPException` machinery covers the boundaries.

## Migration / Rollout

No migration. New endpoint is additive; `Breadcrumb.onSelect` is optional (no-op default). Rollback = `git revert <merge-commit>` per PR. No destructive deletes.

### PR split forecast (`chained-pr`)

| Slice | Files | Lines | Verdict |
|-------|-------|-------|---------|
| 1 — backend | `router.py` (~35 add), `schemas.py` (~10 add), `test_router_taxon_links.py` (~180 new) | ~225 | Single PR, well under 400 |
| 2 — frontend | `App.tsx` (~50), `api.ts` (~20), `Breadcrumb.tsx` (~15), 3 new test files (~310) | ~395 | Single PR, just under 400 |

Forecast guard: Decision needed before apply **No** (both slices <400); Chained PRs recommended **No**; 400-line budget risk **Low**. Re-forecast if slice 2 grows; split App-state vs Breadcrumb-prop into a 3rd PR if needed.

## Open Questions

1. **13 links confirmed.** Spec, design and code all emit exactly 13 links. This design reuses `build_search_links` verbatim, so `load_templates` enforces `==13` row count. User sign-off received: 2026-08-15.
2. **Cascade-path signal.** `App.tsx` learns path only via `taxon:select` (post-resolution). Options: (a) new `path:change` window event from `Cascade.tsx`'s `set-path` reducer consumer; (b) lift `cascadeReducer` into `App.tsx`. **Recommend (a)** — minimal blast radius, mirrors `taxon:select`.
3. **Path encoding.** `{path:path}` captures slashes; literal `/` in a segment could confuse the router. Encoder percent-encodes `/` to `%2F`; route registered after `/kingdoms` / `/path-children` so catch-all won't shadow. Confirm with one pytest that `path=%2F` yields 422/404, not route collision.
