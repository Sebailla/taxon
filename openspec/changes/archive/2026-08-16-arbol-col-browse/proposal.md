# Proposal: arbol-col-browse

## Intent

The 7-dropdown cascade (`frontend/src/components/Cascade.tsx`) breaks on `data/col.db` (1.65 GB CoL import) — no `biota` rank rows, so the resolver walks a synthesized root that no longer exists. Replace the linear cascade with a CoL-style hierarchical tree (`frontend/src/components/TaxonomicTree.tsx`) that lazy-loads children by parent id, indents by rank, renders `rank: Name Authorship • N spp.` rows, and exposes "Find taxon" + `Source` + `Extant only` filters. Closes issue #67. The `breadcrumb-dinamico` invariant stays verbatim.

## Scope

### In Scope
- Backend: `GET /api/tree/children?parent_id={id}` + `GET /api/tree/search?q={q}`; new `taxon/api/tree.py` + `taxon/api/search.py`; schema additions.
- Frontend: replace `Cascade.tsx` + `Cascade.state.ts` with `TaxonomicTree.tsx` + `TaxonomicTree.state.ts` (Zustand cache keyed by `parent_id`).
- Frontend: "Find taxon" `<input>` with 200ms debounce; `Source` + `Extant only` checkboxes; keep emitting `path:change` and writing `cascadePath`.
- `documents-es/openspec/changes/arbol-col-browse/proposal-es.md` per AGENTS.md §1.

### Out of Scope
- `species-search-links`, `species-lookup`, `species-list-by-genus`, `inclusion-filters` (verbatim).
- `Breadcrumb.tsx` aria-label rename; cross-reload persistence; `species-folder-explorer`.
- `Source` filter wiring (no-op CoL-only first PR); `species_count` materialization (lazy + later projection).

## Capabilities

### New Capabilities
- `taxonomic-tree-browse`: CoL-style hierarchical tree with lazy-expand, caret rows, indent by rank, `rank: Name Authorship • N spp.` rows, `Source` + `Extant only` filters, `path:change` dispatch.
- `taxon-tree-search`: name/display_name LIKE search with ranked relevance (exact > prefix > substring), 200ms debounce, limit 8, FTS-ready contract.

### Modified Capabilities
- `taxonomy-hierarchy`: add `GET /api/tree/children?parent_id={id}` and `GET /api/tree/search?q={q}` endpoints. Existing path-resolver semantics stay verbatim.

## Approach

**Approach 3 (hybrid).** Backend adds the two tree endpoints; the existing `/{path:path}/taxon-links` keeps feeding the breadcrumb-links panel. Parent-id addressing bypasses the `Biota` bug. `authorship` is a derived split (`name` vs `display_name` tail); `species_count` is a recursive CTE over `taxa` (lazy `null` for nodes with >100k direct children, fills on demand). `<Toggles>` "extinct" chip folds into the new "Extant only" checkbox. Strict TDD per `openspec/config.yaml strict_tdd: true`. Pencil design + impeccable audit gate the frontend PR per AGENTS.md §5.

## Affected Areas

| Area | Impact |
|------|--------|
| `frontend/src/components/Cascade.tsx` + `Cascade.state.ts` | Removed |
| `frontend/src/components/TaxonomicTree.tsx` + `TaxonomicTree.state.ts` | New |
| `frontend/src/App.tsx`, `api.ts`, `Toggles.tsx` | Modified |
| `frontend/tests/` | Modified (delete cascade tests; add tree tests) |
| `taxon/api/tree.py` + `taxon/api/search.py` | New |
| `taxon/api/schemas.py`, `router.py`, `sqlite_resolver.py` | Modified (`list_tree_children`, no Biota synthesis) |
| `taxon/tests/test_api_router_tree.py` | New |
| `openspec/specs/taxonomy-hierarchy/spec.md` | Modified (MODIFIED Requirements) |
| `taxon.pen` | Modified (design + impeccable audit) |
| `documents-es/openspec/changes/arbol-col-browse/proposal-es.md` | New (Spanish mirror) |

## Risks

| Risk | Lik | Mitigation |
|------|-----|------------|
| `species_count` cost at deep nodes (Eukaryota → 2.4M species) | Med | lazy `null` >100k children; cache at parent_fetch; projection later |
| `Source` filter has no backend | Low | ship UI as no-op (CoL-only) first PR |
| Cascade deletion breaks a cross-importing test | Low | re-grep `from.*Cascade` before delete |
| Pencil + impeccable + TDD = 3-gate chain | Med | Pencil slice first; PR blocked without design sign-off |
| Frontend PR approaches 400-line budget | Med | chained PR forecast in `sdd-tasks` (Pencil/visual, tests, App wiring) |
| No FTS index on `name`/`display_name` at scale | Med | 200ms debounce + `LIMIT 8` cap; FTS in follow-up |

## Rollback Plan

Each PR is additive: backend PR adds new endpoints without touching the path-resolver; frontend PR adds new component before deleting `Cascade`. `git revert <merge-commit>` per PR surgically unwinds. The 2 CRITICAL failures in `cascadeDynamicTiers.test.tsx` close naturally with the Cascade deletion — no separate fix PR needed.

## Dependencies

- `taxon.api.hierarchy.resolve_path_by_display_level` (verbatim, drives `taxon-links`).
- `docs/sources/templates.md` (verbatim, 13-link substitution).
- `taxon.pen` design pass + `impeccable` audit per AGENTS.md §5.

## Success Criteria

- [ ] `GET /api/tree/children?parent_id=2` returns `id`, `name`, `authorship`, `rank`, `has_children`, `species_count`, `parent_id`, marker flags.
- [ ] `GET /api/tree/search?q=Euk` returns ≤8 items ranked exact > prefix > substring; debounced 200ms client-side.
- [ ] `GET /api/tree/children?parent_id=2&include=extant_only` returns only `is_extinct=false` rows.
- [ ] Tree explores `Eukaryota → Animalia → Chordata` without the `Biota` bug; root rows are real `domain` rows.
- [ ] `path:change` CustomEvent fires on every explore; breadcrumb-links panel renders 13 links.
- [ ] `breadcrumb-dinamico` tests stay green; `cascadeDynamicTiers.test.tsx` deleted.
- [ ] `pytest` + `vitest` suites green; CI on `develop` green.
- [ ] `/learn-es/YYYY-MM-DD-arbol-col-browse.md` entry created after merge.
- [ ] Pencil design + impeccable audit pass merged before any frontend code.
