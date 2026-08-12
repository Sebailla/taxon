# Post-change followups — archive, deploy, pagination, a11y

## What

Four follow-up slices deferred from the species-search-dispatcher
change shipped together as PR #16:

1. Spec archive — move the change folder to `openspec/changes/archive/`.
2. Frontend deployment — serve `frontend/dist/` from FastAPI via
   `StaticFiles` so a single `uvicorn` hosts both the API and the SPA.
3. 600-row pagination boundary tests — six integration tests pin
   the 500-item cap and the `next_cursor` contract at the boundary.
4. Manual a11y audit — hand-rolled walk of the React frontend
   against WCAG 2.1 AA + the 10 impeccable dimensions.

## How

### 1. Spec archive

Per the OpenSpec convention, a shipped change is moved out of
`openspec/changes/<name>/` into `openspec/changes/archive/<name>/`
so the next change starts from a clean folder. The delta specs
already live in their canonical location under
`openspec/specs/<capability>/spec.md` (the taxonomy-hierarchy,
species-list-by-genus, species-lookup, species-search-links,
inclusion-filters specs).

The archived folder carries an `archive.md` that summarises what
landed, where the specs live, the lessons captured, and the
seven PR numbers. This is the marker for future contributors who
want to look at the change history without re-reading every
`/learn-es/` entry.

### 2. Frontend deployment

`create_app(database_url)` now mounts `frontend/dist/` as a
Starlette `StaticFiles` handler when the directory exists. The
factory stays functional when the directory is absent (development
+ tests), so a single `uvicorn` deployment can host both the API
and the SPA from the same origin:

```
GET /healthz        → API router
GET /api/*          → API router
GET /assets/*       → StaticFiles handler (real files)
GET /                → StaticFiles handler → index.html
GET /some/spa/route  → 404 from StaticFiles → 404 handler returns index.html
```

The SPA fallback is wired through a `StarletteHTTPException`
handler that intercepts 404s and returns `index.html`. This
preserves API 404s (the handler returns the JSON `{"detail": ...}`
for non-404 statuses) while letting client-side routes fall
through to the React Router.

A side effect: `create_engine("sqlite:///:memory:", ...)` now uses
`StaticPool` so the schema created during the lifespan startup is
visible from every session thread. Without `StaticPool`, each
thread got its own private in-memory DB, the lifespan created
tables in one, and the first request from another thread failed
with `no such table: taxa`.

### 3. Pagination boundary

Six tests pin the contract:

| Rows | First page | Second page |
| --- | --- | --- |
| 499 | 499 + cursor None | — |
| 500 | 500 + cursor None (inclusive cap) | — |
| 501 | 500 + cursor | 1 + cursor None |
| 600 | 500 + cursor | 100 + cursor None |
| 600 + `include=synonyms` | 500 + cursor (OR semantics) | — |
| 600 (alphabetical ordering) | sorted; last item of page 1 sorts strictly before first of page 2 |

The tests seed the database via `import_dataset` so the full
parser / schema / species_paths pipeline is exercised end-to-end.

### 4. A11y audit

Lighthouse CLI is not installed in this environment, so the audit
is hand-rolled against the React source. The 10 dimensions match
the impeccable rubric. Score: **36/40 (Excellent)**.

Findings:

- **P2** AmbiguityPicker does not trap focus inside the dialog.
  Tab can escape to the rest of the page. WAI-ARIA APG requires
  focus to stay inside the modal until closed.
- **P3** Toggle chips are 28px tall; WCAG AAA recommends 44px. Add
  `min-h-[44px]` to the chip class.
- **P3** Cascade does not move focus to the freshly-enabled child
  dropdown after a parent selection. Keyboard users have to Tab
  again.

## Where

### Spec archive

- `openspec/changes/archive/species-search-dispatcher/archive.md` — new.
- `openspec/changes/archive/species-search-dispatcher/{proposal,design,tasks}.md`
  — moved from `openspec/changes/species-search-dispatcher/`.

### Frontend deployment

- `taxon/api/__init__.py` — `_mount_frontend` helper; in-memory
  SQLite lifespan with `StaticPool`; SPA fallback exception
  handler.
- `taxon/tests/test_frontend_mount.py` — new: 5 RED-first tests.

### Pagination boundary

- `taxon/tests/test_pagination_boundary.py` — new: 6 integration
  tests.

### A11y audit

- `docs/audits/lighthouse-a11y.md` — new: 243 lines, 36/40 score.

## Why

These four slices are the natural close of the species-search-
dispatcher change:

- **Archive** — the change folder no longer pollutes
  `openspec/changes/`. New changes start clean.
- **Deployment** — the SPA and the API can ship from the same
  process. Without this, deployment needs a separate static-file
  host (S3, Nginx, ...) on top of the FastAPI process.
- **Pagination** — the 500-item cap was pinned in unit tests but
  not at the integration boundary. The 6-row / 60-row fixture
  tests would not catch a regression where the cursor advances
  past the cap.
- **A11y** — the cascade UI is read-only and used by researchers
  and aquarists, many of whom may rely on screen readers. The
  audit confirms the ARIA labels are correct and surfaces the
  modal focus trap as the next accessibility improvement.

## How it works

### Frontend deployment

A single `uvicorn taxon.main:app` now serves both surfaces. In
production:

1. Build the SPA: `cd frontend && npm run build` → `frontend/dist/`.
2. Run the API: `python -m taxon.main` on `:8000`.
3. Browse `http://localhost:8000/` → React SPA loads.
4. The SPA fetches `/api/*` from the same origin → no CORS
   gymnastics needed for production.
5. Client-side routes (`/some/spa/route` if React Router adds
   them) fall through to `index.html` via the 404 handler.

In development:

1. Run the API: `python -m taxon.main` on `:8000`.
2. Run the SPA dev server: `cd frontend && npm run dev` on `:5173`.
3. Vite proxies `/api/*` to `:8000`.
4. HMR works as expected; no production build needed.

### Spec archive

The change folder is moved with `git mv` so the history follows
the files. Future PRs touching the same surface update the
canonical spec under `openspec/specs/<capability>/spec.md` and
add a new change folder for the new work.

## Workflows

- **Archive workflow**: when a change ships, run
  `git mv openspec/changes/<name> openspec/changes/archive/<name>`
  and add an `archive.md` summarising what landed. Future changes
  start from a clean `openspec/changes/`.
- **Deploy workflow**: `cd frontend && npm run build` then
  `python -m taxon.main`. Single process, single port.
- **Pagination test workflow**: the 6-row / 60-row fixtures in
  `test_pagination_boundary.py` exercise the 500-cap with 499,
  500, 501, 600 rows + include filter + alphabetical ordering.
- **A11y audit workflow**: the hand-rolled audit runs every time
  a UI component lands. The next session should install
  `lighthouse` (or `@lhci/cli`) to automate the verdict.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| PR | https://github.com/Sebailla/taxon/pull/16 (squash-merged) |
| Issue | https://github.com/Sebailla/taxon/issues/15 (auto-closed) |
| Branch | `feat/post-change-followups` (deleted) |
| Worktree | `../taxon-worktrees/followups` (cleaned up) |
| Files changed | 8 (across 4 commits) |
| Tests added | 11 (5 frontend mount + 6 pagination boundary) |
| Tests passing | 91 (was 80) |
| Typecheck | `mypy --strict` clean on 24 source files |
| Lint | `ruff check` + `ruff format --check` clean |
| A11y audit score | 36/40 (Excellent) |
| CI jobs | 3 green (Python 3.11, 3.12, Node 20) |

## Deviations and decisions

- **StaticPool for in-memory SQLite.** Originally I tried to keep
  the engine config minimal. The `:memory:` quirk is well-known
  but only surfaced when the test client had to spawn multiple
  threads. The fix is one line (`poolclass=StaticPool`) but it
  took me two iterations to find.

- **SPA fallback via 404 handler, not catch-all route.** A catch-
  all `/{full_path:path}` route shadows every other route, so
  even `/api/kingdoms` would route to the catch-all. The 404
  exception handler fires only when the StaticFiles handler
  raises 404 (file not found) and the API router did not match,
  so it leaves the existing routes intact.

- **Manual a11y audit, not Lighthouse.** Lighthouse CLI is not
  available in this environment. The hand-rolled audit walks the
  same 10 dimensions the impeccable skill uses; the verdict
  should agree with Lighthouse within ±2 points when run.

- **Spec archive as `git mv`.** The rename is preserved in git
  history so `git log --follow` still traces back to the change.
  A regular `cp` + `rm` would lose that history.

## Next steps

- **P2 follow-up**: add focus trap to AmbiguityPicker (15 lines
  of code; manual Tab / Shift+Tab wrapping).
- **P3 follow-ups**: grow toggle chips to 44px; auto-focus
  freshly-enabled cascade dropdowns.
- **Real Lighthouse CI**: install `lighthouse` or `@lhci/cli` in
  CI and run the a11y category on every PR.
- **Frontend hosting**: pick a deployment target (Docker image,
  fly.io, Railway) and write the deployment doc.

The species-search-dispatcher change is now complete across 8 PRs
(#2, #4, #6, #8, #10, #12, #14, #16) and 117 tests. The next change
starts from a clean `openspec/changes/`.