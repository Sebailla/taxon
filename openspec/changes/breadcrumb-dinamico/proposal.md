# Proposal: breadcrumb-dinamico

## Intent

Breadcrumb (`Breadcrumb.tsx` at `App.tsx:94`) only renders after species resolution. Two upgrades mid-cascade: (1) breadcrumb stays visible, mirroring the path being built (Biota → Kingdom → … → current rank); (2) clicking any segment opens the same 13-link grid the species row produces — but for that taxon's name.

## Scope

### In Scope

- Render breadcrumb when `state.path.length > 0`; drop `resolved !== null` gate in `App.tsx`.
- Each segment becomes a `<button>`; click opens a per-taxon 13-link grid in `<aside>`.
- New `GET /api/{path}/taxon-links` (1–7 segments, no epithet) resolving the deepest segment via `resolve_path_by_display_level` and emitting the 13-link substitution.
- Species-links and breadcrumb-taxon's links coexist; last-clicked panel wins.

### Out of Scope

- Filesystem / iframe / switches (`species-folder-explorer`); CoL tree (`arbol-col-browse`); `LinksResponse.links` contract changes; persisting segment across reloads.

## Capabilities

### New Capabilities

- `taxon-breadcrumb-links`: per-taxon dispatch envelope resolving any cascade path (1–7 segments, no epithet) into 13 substituted links.

### Modified Capabilities

- `species-search-links`: REQUIREMENT — dispatch endpoint MUST accept a path with no epithet; deepest segment's name is the substitution target. Delta spec.
- `taxonomy-hierarchy`: REQUIREMENT — the cascade path is exposed as a permanent breadcrumb with one clickable segment per picked rank (incl. intermediates). Delta spec.

## Approach

**Option (a)** — new backend endpoint. Frontend option (c) duplicates `build_search_links` and ships template URLs to the browser; `species-search-links` pins substitution server-side. Endpoint: `resolve_path_by_display_level` walks `parent_segments`, then `build_search_links(taxon.name, templates)` — same as `species_links`. New `TaxonLinksResponse{ taxon, links }` keeps `LinksResponse.species` non-null. **Frontend**: `Breadcrumb` adds `onSelect?: (path: string[]) => void`; segments as `<button type="button">`. `App.tsx` adds `breadcrumbLinks` state + fetch keyed by `path.join("|")`; reuses `<SpeciesLinks>`.

## Affected Areas

- Frontend: `Breadcrumb.tsx`, `App.tsx`, `api.ts` (modified); `SpeciesLinks.tsx` (reused, none).
- Backend: `taxon/api/router.py`, `taxon/api/schemas.py` (modified); `taxon/api/{sqlite_resolver,hierarchy,search_links}.py` (reuse, none).
- Tests: `taxon/tests/test_api_router.py`, `frontend/tests/Breadcrumb.test.tsx` (200/404 + 12-item + substitution; click handler).

## Risks

- **Medium** Off-tuple intermediates inflate breadcrumb → cap to 7 canonical ranks.
- **Low** Per-segment click races species-links fetch → per-panel AbortController.
- **Low** Endpoint shadows `/api/.../links` → `/taxon-links` suffix + distinct tag.
- **Low** 12-item invariant breaks for non-species → `build_search_links` reused; existing suite covers it.

## Rollback Plan

`git revert <merge-commit>` per PR. Every PR is additive: optional `onSelect` with no-op default, additive envelope, no destructive deletes.

## Dependencies

- `taxon.api.hierarchy.resolve_path_by_display_level`; `taxon.search_links.build_search_links` + `docs/sources/templates.md`.

## Success Criteria

- [ ] `path=["Animalia","Chordata"]`, no species resolved → breadcrumb renders two clickable segments.
- [ ] Clicking "Chordata" opens a 13-link grid; every `{q}` = `quote_plus("Chordata")` byte-for-byte vs `templates.md`.
- [ ] `GET /api/Animalia%7CChordata/taxon-links` → `TaxonLinksResponse{ taxon:{name:"Chordata",rank:"phylum",...}, links:[13 items] }`.
- [ ] `GET /api/{kingdom}/.../{epithet}/links` unchanged (no regression).
- [ ] Species resolution still opens species-links; clicking breadcrumb after does NOT clear it.