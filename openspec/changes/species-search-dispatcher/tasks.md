# Tasks: Species Search Dispatcher

## Review Workload Forecast

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Lines changed: 600-900. Delivery strategy: ask-on-risk. 6 chained PRs; child base = previous PR branch. Units: (1) parser+schema+import_data+search_links; (2) FastAPI+409; (3) Pencil+impeccable; (4) React+Cascade; (5) SpeciesLinks+Toggles+AmbiguityPicker; (6) Docs+CI+`/learn-es`.

## Phase 1: Foundation / Infrastructure

- [x] 1.1 Create `taxon/pyproject.toml` deps (fastapi, uvicorn, sqlalchemy, pydantic, pytest, ruff, mypy).
- [x] 1.2 Create `taxon/.gitignore` excluding `data/`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.pen`.
- [x] 1.3 RED test `taxon/tests/test_parser.py` with fixtures: †, =, ?, [unassigned], Candidatus, deep nesting.
- [x] 1.4 GREEN impl `taxon/taxon/parser.py` streaming indentation stack + marker extraction.
- [x] 1.5 RED test `taxon/tests/test_schema.py` for `Taxon`/`SpeciesPath` invariants + marker columns.
- [x] 1.6 GREEN impl `taxon/taxon/schema.py` SQLAlchemy models with marker columns + indexes.
- [x] 1.7 RED test `taxon/tests/test_import.py` for count/integrity against `dataset-2011.txt`.
- [x] 1.8 GREEN impl `taxon/taxon/import_data.py` batched streaming inserts against `dataset-2011.txt`.
- [x] 1.9 RED test `taxon/tests/test_search_links.py` for verbatim URL parity vs `templates.md` (incl. Sci-hub `https://sci-hub.ru/match/{q}`), `quote_plus(s, safe='')`.
- [x] 1.10 GREEN impl `taxon/taxon/search_links.py` parses `docs/sources/templates.md`, emits 12 URLs.

## Phase 2: API Layer

- [ ] 2.1 RED test `taxon/tests/test_api_hierarchy.py` for cascade scenarios (404, 409, ordering, casing).
- [ ] 2.2 RED test `taxon/tests/test_api_species_list.py` for `/genera/{g}/species` + `include=` + cursor.
- [ ] 2.3 RED test `taxon/tests/test_api_links.py` for 12 entries on `/species/{genus}/{epithet}/links`.
- [ ] 2.4 RED test `taxon/tests/test_api_ambiguity.py` for 409 with breadcrumb `candidates[]`.
- [ ] 2.5 GREEN impl `taxon/taxon/api/__init__.py` FastAPI app factory + Pydantic schemas.
- [ ] 2.6 GREEN impl `taxon/taxon/api/router.py` URL-encoded routes + 409 handler.
- [ ] 2.7 GREEN impl `taxon/taxon/main.py` uvicorn entrypoint.

## Phase 3: Frontend Design (BEFORE code per AGENTS.md §5)

- [ ] 3.1 Create `taxon/.pen` via Pencil MCP: cascade + ambiguity picker + species-links panel.
- [ ] 3.2 Audit under `impeccable` (a11y, hierarchy, typography, color, motion, anti-patterns); iterate.
- [ ] 3.3 Document approval in `taxon/docs/design/approval.md` (date + sign-off).

## Phase 4: Frontend Implementation

- [ ] 4.1 Scaffold `taxon/frontend/` Vite (React 18 + TS + TailwindCSS 3) + Vitest/Testing Library.
- [ ] 4.2 (R) test `taxon/frontend/tests/api.test.ts` typed client + 409 handling.
- [ ] 4.3 (G) impl `taxon/frontend/src/api.ts` typed client.
- [ ] 4.4 (R) test `taxon/frontend/tests/Cascade.test.tsx` reset-on-parent-change + abort stale + loading/error/empty.
- [ ] 4.5 (G) impl `taxon/frontend/src/Cascade.tsx` 5 dropdowns + 6th fixed scrollable species list.
- [ ] 4.6 (R) test `taxon/frontend/tests/SpeciesLinks.test.tsx` 12 buttons + external-link attrs.
- [ ] 4.7 (G) impl `taxon/frontend/src/SpeciesLinks.tsx`.
- [ ] 4.8 (R) test `taxon/frontend/tests/Toggles.test.tsx` OR semantics + default off.
- [ ] 4.9 (G) impl `taxon/frontend/src/Toggles.tsx`.
- [ ] 4.10 (R) test `taxon/frontend/tests/AmbiguityPicker.test.tsx` lists candidates with breadcrumb.
- [ ] 4.11 (G) impl `taxon/frontend/src/AmbiguityPicker.tsx`.

## Phase 5: Documentation & Cleanup

- [ ] 5.1 Write `taxon/README.md` (EN) + ES mirror `taxon/documents-es/README-es.md`.
- [ ] 5.2 Set up CI on `develop` (pytest, vitest, ruff, mypy, eslint).
- [ ] 5.3 Post-merge green: `/learn-es/2026-08-09-species-search-dispatcher.md`.
- [ ] 5.4 Conventional commits: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`; no AI attribution.
