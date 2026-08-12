# PR 2B — API hierarchy slice

## What

Wired the cascade endpoints from `openspec/specs/taxonomy-hierarchy`
so the frontend can walk Kingdom → Phylum → Class → Order → Family →
Genus → Species by appending one path segment per rank. The leaf
`/species` endpoint ships in this slice so the cascade UI's sixth
scrolling panel has real data to render.

## How

- New module `taxon/api/hierarchy.py` exposes a path-name resolver
  (`resolve_path`) that walks the path segment by segment, anchoring
  each lookup on the parent identified by the previous segment. The
  first segment matches by `rank == 'kingdom'` (not `parent_id IS
  NULL`) because WoRMS attaches a Biota superdomain above every
  kingdom.
- New module `taxon/api/db.py` exposes a `get_db` FastAPI dependency
  that yields a request-scoped SQLAlchemy session bound to the engine
  the lifespan opened.
- `taxon/api/errors.py` extracted `APIError`, `NotFoundError`, and
  `AmbiguousError` from `taxon/api/__init__.py` so the router can
  import `NotFoundError` without creating a circular import.
- `taxon/api/router.py` registers the 7 cascade endpoints +
  `/_meta` smoke probe.
- 18 RED-first contract tests in `taxon/tests/test_api_hierarchy.py`
  pin every endpoint behaviour from the spec.

## Where

- `taxon/api/hierarchy.py` — path-name resolver + dataclass.
- `taxon/api/db.py` — FastAPI session dependency.
- `taxon/api/errors.py` — extracted HTTP error classes.
- `taxon/api/router.py` — 7 cascade endpoints.
- `taxon/api/__init__.py` — re-exports the error classes and
  AppState so existing callers keep working.
- `taxon/tests/test_api_hierarchy.py` — 18 RED-first contract tests.

## Why

The cascade UI is the spine of the species search dispatcher. Without
the hierarchy endpoints the frontend cannot render the six dropdowns
that drive species selection. Slicing the work into Sub-PR 2B (this
slice) keeps the diff small enough to review focus; Sub-PR 2C will
add 409 ambiguity responses, inclusion filters, and the per-species
search-links endpoint on top of the same router.

The 404 strategy (segment-by-segment walk with rank anchoring) avoids
needing a 409 disambiguation layer for the cascade itself: a Kingdom
named "Chromista" and an Order named "Chromista" cannot collide
because the path's rank context fixes each segment's expected rank.
The 409 layer is reserved for Sub-PR 2C's species-name lookups, which
do not have an unambiguous rank context.

## How it works

Path-name resolution proceeds left-to-right:

1. The first segment matches any Taxon whose `name` (case-insensitive)
   equals the segment and whose `rank` equals `'kingdom'`. Anchoring
   on rank instead of `parent_id IS NULL` makes the resolver find
   `Animalia` even though WoRMS sits a `Biota` superdomain above it.
2. Each subsequent segment matches any Taxon whose `name` (case-
   insensitive) equals the segment and whose `parent_id` equals the
   previous match's id. The match's `rank` must equal the expected
   rank at that depth (Phylum, Class, Order, Family, Genus).
3. The leaf endpoint returns the direct children at the requested
   rank (`species` for the genus endpoint) sorted alphabetically by
   canonical `name`.

A 404 is raised when any segment fails to resolve; the error body
identifies the failing segment so the cascade UI can highlight the
dropdown that produced the bad path. Empty children produce an empty
list with status 200, never 404 — the cascade UI treats "no results"
and "rank does not exist" the same way.

## Workflows

- CI: GitHub Actions runs `pytest + ruff + mypy` on Python 3.11 and
  3.12 for every PR. Sub-PR 2B passes both jobs green.
- Branching: stacked-to-main chain strategy. Each sub-PR targets
  `develop`; release PRs from `develop` to `main`.
- TDD: every endpoint ships with a RED-first contract test before the
  implementation lands.
- `/_meta` smoke probe is kept (now returns `{"phase": "2B"}`) so
  future sub-PRs can prove the router is mounted at all.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| PR | https://github.com/Sebailla/taxon/pull/6 |
| Issue | https://github.com/Sebailla/taxon/issues/5 (auto-closed) |
| Branch | `feat/species-search-dispatcher-api-hierarchy` (squash-merged, branch deleted) |
| Worktree | `../taxon-worktrees/pr2b-hierarchy` (cleaned up) |
| Files changed | +878 / -50 across 6 files |
| Tests added | 18 (cumulative total: 43) |
| Tests passing | 43/43 locally; CI green on Python 3.11 + 3.12 |
| Mypy strict | clean on 18 source files |
| Ruff check | clean |
| Ruff format | clean |

## Deviations

- **Path resolution anchors on rank, not parent_id, for the first
  segment.** This deviates from the simpler "match by parent_id IS
  NULL" pattern but matches the WoRMS dataset shape (Biota sits above
  every kingdom). Documented inline in `resolve_path`.
- **`display_name` includes the rank suffix** (e.g. `"Animalia
  [kingdom]"`). This is how the parser constructs the field — it
  preserves the verbatim source label including the bracketed rank.
  Tests assert the rank suffix is present so a future parser refactor
  cannot silently drop it.
- **The `/species` endpoint ships in this slice** even though the
  slice plan originally reserved it for 2C. Moving it forward lets the
  cascade UI's sixth panel render real data without a second sub-PR;
  2C still owns inclusion filters, ambiguity candidates, and the
  per-species search-links endpoint.