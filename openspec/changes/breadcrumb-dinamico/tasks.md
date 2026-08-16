# Tasks: breadcrumb-dinamico

## Review Workload Forecast

Estimated changed lines: backend ~225 (PR1) + frontend ~395 (PR2).
Chained PRs: Yes (delivery `auto-chain`). Chain strategy: stacked-to-main. Risk: Low.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

- **PR1 backend** — route+schema+pytest. Test: `pytest taxon/tests/test_api_router_taxon_links.py -q`. Harness: `uvicorn`+`curl /api/Animalia%7CChordata/taxon-links`. Rollback: revert PR1 (route+schema+test only).
- **PR2 frontend** — store+Breadcrumb.onSelect+App panel+vitest. Test: `npx vitest run Breadcrumb.dynamic.test App.taxonLinks.test api.taxonLinks.test`. Harness: `npm run dev`+click segment→13-link grid. Rollback: revert PR2 (store+Breadcrumb+App.tsx only).

## Phase 1: Backend RED

- [x] 1.1 New `taxon/tests/test_api_router_taxon_links.py`; assert 200+`TaxonLinksResponse{taxon,links}`+`taxon.name=="Chordata"`+`rank=="phylum"`+`len(links)==13` on `/api/Animalia%7CChordata/taxon-links`. Fails (no route).
- [x] 1.2 Substitution: load `docs/sources/templates.md`, `quote_plus("Chordata")`, assert each `url` byte match. Fails.
- [x] 1.3 Canonical-name: fixture `display_name="Chordata Bateson, 1885"`; `Bateson`/`1885` absent from every url. Fails.
- [x] 1.4 404: unknown `Atlantis`, `Animalia%7CBadPhylum`; 404 names bad segment. Fails.
- [x] 1.5 Cap: 8-segment path → 404 body explains 7-segment cap. Fails.
- [x] 1.6 Regression: `/api/{k}/.../{epithet}/links` still 13 links. Fails until 2.4.

## Phase 2: Backend GREEN

- [x] 2.1 Add `TaxonLinksResponse(_ORMBase){taxon:TaxonResponse, links:list[SearchLinkItem]}` to `taxon/api/schemas.py`; append `__all__`. 1.1 passes.
- [x] 2.2 Register `GET /{path:path}/taxon-links` in `taxon/api/router.py` after `/kingdoms`+`/path-children`; split `|`; `1<=len<=7` else `NotFoundError`. 1.5 passes.
- [x] 2.3 Resolve via `resolve_path_by_display_level(session, segments)`; `None`→`NotFoundError(f"taxon not found: {segments[-1]!r}")`. 1.4 passes.
- [x] 2.4 Build response: `TaxonResponse.model_validate(row)` + `build_search_links(row.name, load_templates(_TEMPLATES_PATH))`. 1.1–1.3, 1.6 pass.
- [x] 2.5 `pytest taxon/tests -q`; zero regression in species-links + SQLite suites.

## Phase 3: Frontend RED

- [x] 3.1 New `frontend/tests/Breadcrumb.dynamic.test.tsx`: render w/ `onSelect`; click `Chordata`; handler called `["Animalia","Chordata"]`. Fails (no button).
- [x] 3.2 Click first segment → handler `["Animalia"]`; deepest `aria-current="page"`. Fails.
- [x] 3.3 Render w/o `onSelect`; click does not throw; `<nav>` renders. Fails.
- [x] 3.4 New `frontend/tests/store.cascadePath.test.ts`: `setPath(["A","B"])` updates state; subscriber fires. Fails.
- [x] 3.5 New `frontend/tests/api.taxonLinks.test.ts`: mock 200 `{taxon,links:13}`; URL `/Animalia%7CChordata/taxon-links`, `status==="ok"`, `links.length==13`. Fails.
- [x] 3.6 404: mock 404 `detail="taxon not found: 'Atlantis'"`; `status==="not-found"`. Fails.
- [x] 3.7 New `frontend/tests/App.taxonLinks.test.tsx`: dispatch `path:change` `["Animalia","Chordata"]`; advance timers; one fetch fires; panel renders 13 `<a>`. Fails.
- [x] 3.8 Dispatch `["Animalia","Chordata"]` then `["Animalia"]` before first resolves; exactly one in-flight `fetch` survives. Fails.

## Phase 4: Frontend GREEN

- [x] 4.1 Add `"zustand": "^5"` to `frontend/package.json` `dependencies`; `npm install`.
- [x] 4.2 Add `TaxonLinksResponse` + `fetchTaxonLinks(pathSegments, init?)` to `frontend/src/api.ts` (mirror `fetchPathChildren`). 3.5, 3.6 pass.
- [x] 4.3 New `frontend/src/store/cascadePath.ts`: zustand store `{path:string[]; setPath(p:string[]):void}` default `path:[]`. 3.4 passes.
- [x] 4.4 Modify `Breadcrumb.tsx`: add `onSelect?: (path: string[]) => void`; segments `<button type="button">` w/ `aria-current="page"` on deepest; keep chevron+`font-mono`+`bg-surface`. 3.1–3.3 pass.
- [x] 4.5 Modify `Cascade.tsx`: dispatch `path:change` `CustomEvent<{path:string[]}>` in `set-path` consumer when `state.path` changes; verify via `cascadeDynamicTiers.test.tsx`.
- [x] 4.6 Modify `App.tsx`: add `breadcrumbLinks` state + `useEffect` keyed by `cascadePath` w/ `AbortController`; abort on cleanup; `setResolved` clears panel. Drop `resolved !== null` gate; render `<Breadcrumb>` when `cascadePath.length > 0`. 3.7, 3.8 pass.
- [x] 4.7 `npx vitest run`; zero regression in `Breadcrumb.test.tsx`, `api.test.ts`, `Cascade.ui.test.tsx`, `taxonSelect.test.ts`.
- [x] 4.8 `npm run typecheck` + `npm run lint`; fix strict-TS / unused-prop warnings.