# Archive: species-search-dispatcher

## Status

**Archived 2026-08-13.** The species-search-dispatcher change shipped
end-to-end across seven chained PRs (#2, #4, #6, #8, #10, #12, #14)
and the change folder is moved here per the OpenSpec convention.

## What landed

The change delivered a read-only species search web app that
replaces the legacy Google Sheets navigator:

- Backend: FastAPI + SQLAlchemy + SQLite with 12 cascade, lookup,
  and links endpoints (`taxon/api/`).
- Frontend: React + Vite + Tailwind with a 6-step dropdown cascade
  and 12-link grid (`frontend/`).
- Design: Pencil canvas + impeccable audit (`taxon.pen`,
  `docs/design/design-audit.md`, `docs/design/approval.md`).
- Docs + CI: top-level README, Spanish mirror, frontend CI job
  (`README.md`, `documents-es/README-es.md`,
  `.github/workflows/ci.yml`).

## Spec archive

The four delta specs from this change live in their canonical
location under `openspec/specs/`:

- `openspec/specs/taxonomy-hierarchy/spec.md`
- `openspec/specs/species-list-by-genus/spec.md`
- `openspec/specs/species-lookup/spec.md`
- `openspec/specs/species-search-links/spec.md`
- `openspec/specs/inclusion-filters/spec.md`

These specs are now the source of truth for the cascade UI
contract. Future changes that modify the surface must update the
canonical spec under `openspec/specs/<capability>/spec.md` rather
than this archived change.

## Why archived

- All Phase 1-5 tasks are marked `[x]` in `tasks.md`.
- The seven chained PRs all merged to `develop` with green CI
  (Python 3.11, Python 3.12, Node 20).
- 108 tests passing (80 backend + 28 frontend).
- `mypy --strict` clean, `ruff check` + `ruff format --check` clean,
  `tsc --noEmit` clean, ESLint 0 errors, production build succeeds.

## Lessons captured

- `/learn-es/2026-08-09-pr1-parser-schema-import-search-links.md`
- `/learn-es/2026-08-09-pr2a-api-foundation-slice.md`
- `/learn-es/2026-08-09-pr2b-api-hierarchy-slice.md`
- `/learn-es/2026-08-11-pr2c-species-lookup-links-slice.md`
- `/learn-es/2026-08-12-phase-3-pencil-impeccable.md`
- `/learn-es/2026-08-12-phase-4-frontend.md`
- `/learn-es/2026-08-12-species-search-dispatcher.md` (end-to-end)

## Acceptance evidence

| Phase | PR | Tests | Status |
| --- | --- | --- | --- |
| Phase 1 | #2 | 10 | merged |
| Phase 2A | #4 | 12 | merged |
| Phase 2B | #6 | 18 | merged |
| Phase 2C | #8 | 37 | merged |
| Phase 3 | #10 | 0 (docs only) | merged |
| Phase 4 | #12 | 28 | merged |
| Phase 5 | #14 | 0 (docs + CI only) | merged |
| **Total** | | **108** | |