# PR 2C — API species lookup slice

## What

Completed the API layer with the three endpoints that finish the
species-search flow: a paginated, inclusion-filtered species list; a
single-species resolver with 409 ambiguity disambiguation; and the
per-species dispatch URLs the legacy spreadsheet encoded.

## How

- New module `taxon/api/species.py` exposes the helpers the router
  needs:
  - `InclusionFilter` — parses the `include` CSV query parameter
    into the four inclusion classes; `accepted_only` predicate is
    the SQL `accepted OR (any enabled toggle)` so the response
    always includes accepted species alongside any additional class.
  - `list_species_page` — paginates the direct species children of
    a genus using a 500-item cap; the cursor is the canonical
    `name` of the last row in the page so pagination is stable
    across database re-imports.
  - `build_breadcrumb` — walks the parent chain and emits the
    Kingdom → Phylum → … → Genus breadcrumb, dropping the leading
    Biota superdomain so the breadcrumb matches the cascade UI's
    Kingdom-first UX.
  - `find_species_by_pair` — matches a species by joining the
    resolved genus's name with the supplied epithet (`<genus>
    <epithet>` is how WoRMS stores the canonical species name).
- `taxon/api/router.py` extends `/api/{path}/{genus}/species` with
  `include=` and `cursor=` query parameters and adds three new
  endpoints:
  - `/api/{path}/{genus}/{epithet}` — full-breadcrumb lookup
    (always unambiguous).
  - `/api/species/{genus}/{epithet}` — pair-only lookup (200/404/
    409 with `candidates[]` when the pair collides).
  - `/api/{path}/{genus}/{epithet}/links` — emits the 12 dispatch
    URLs.
- `taxon/api/schemas.py` adds six new response models:
  `SpeciesListResponse` (envelope for paginated lists),
  `SpeciesListItem`, `SpeciesLookupResponse`, `LinksResponse`,
  `MarkerFlags`, `AmbiguityCandidate`, `SearchLinkItem`.
- `taxon/api/__init__.py` — the `AmbiguousError` handler now
  normalises candidates through `AmbiguityCandidate` so the wire
  shape carries `canonical_name` + `display_name` alongside
  `id` + `breadcrumb`.

## Where

- `taxon/api/species.py` — new helpers.
- `taxon/api/router.py` — extended species list + three new endpoints.
- `taxon/api/schemas.py` — six new response models.
- `taxon/api/__init__.py` — AmbiguousError handler normalisation.
- `taxon/tests/test_api_species_list.py` — 14 RED-first contract tests.
- `taxon/tests/test_api_species_lookup.py` — 12 RED-first contract tests.
- `taxon/tests/test_api_species_links.py` — 11 RED-first contract tests.
- `taxon/tests/test_api_app.py` — ErrorResponse test uses
  AmbiguityCandidate.
- `taxon/tests/test_api_hierarchy.py` — `/species` tests updated for
  envelope + inclusion classes.

## Why

The cascade UI alone is not enough to drive the species-search
flow. The frontend also needs to:

1. List the species under a genus, with toggles for extinct /
   synonyms / uncertain / unassigned taxa. Without the inclusion
   filters the cascade would only show accepted taxa.
2. Paginate the species list — some genera in WoRMS carry more
   than 500 species.
3. Resolve a `(genus, epithet)` pair to a single species, with
   ambiguity surfaced when the same pair exists under multiple
   parent breadcrumbs. Without 409 the UI would silently pick one
   and confuse the user.
4. Emit the 12 dispatch URLs for the resolved species so the
   cascade can fan out to the same sources the spreadsheet
   encoded.

## How it works

The species-list endpoint accepts `include=` as a CSV string. The
predicate for any enabled toggle is `accepted OR (any enabled
toggle)` so accepted species are always included alongside the
additional class. With all four toggles on, every species passes.

The pagination cap is 500 items per response. The cursor is the
canonical `name` of the last row in the page (not the id) so a
re-import with the same source yields the same cursor pagination.

The lookup endpoints come in two flavours:

- **Full-breadcrumb** (`/api/{path}/{genus}/{epithet}`): the path's
  Kingdom → … → Genus segments anchor the resolution; ambiguity
  cannot occur.
- **Pair-only** (`/api/species/{genus}/{epithet}`): scans every genus
  sharing the name; 200 when exactly one species matches, 404 when
  zero, 409 with `candidates[]` when multiple. Each candidate
  carries its full Kingdom → Genus breadcrumb so the UI can render
  a disambiguation picker.

The links endpoint reuses the templates parsed by
`taxon.search_links` from `docs/sources/templates.md` and substitutes
`{q}` via `urllib.parse.quote_plus(species, safe="")`. The Sci-hub
URL is `https://sci-hub.ru/match/{q}`. The 12-link order matches the
row order in the templates file.

## Workflows

- CI: GitHub Actions runs `pytest + ruff + mypy` on Python 3.11 and
  3.12 for every PR. Sub-PR 2C passes both jobs green.
- Branching: stacked-to-main chain strategy. Each sub-PR targets
  `develop`; release PRs from `develop` to `main`.
- TDD: every endpoint ships with RED-first contract tests before the
  implementation lands.
- `/_meta` smoke probe is kept (now returns `{"phase": "2C"}`) so
  future sub-PRs can prove the router is mounted at all.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| PR | https://github.com/Sebailla/taxon/pull/8 |
| Issue | https://github.com/Sebailla/taxon/issues/7 (auto-closed) |
| Branch | `feat/species-search-dispatcher-api-species-lookup-links` (squash-merged, branch deleted) |
| Worktree | `../taxon-worktrees/pr2c-species-lookup-links` (cleaned up) |
| Files changed | +1655 / -47 across 9 files |
| Tests added | 37 (cumulative total: 80) |
| Tests passing | 80/80 locally; CI green on Python 3.11 + 3.12 |
| Mypy strict | clean on 22 source files |
| Ruff check | clean |
| Ruff format | clean |

## Deviations

- **Two lookup endpoints, not one.** The original slice plan reserved
  the 409 ambiguity flow for Sub-PR 2C but kept it on the same
  `/api/{path}/{genus}/{epithet}` endpoint. Once the implementation
  started it became clear that the full-breadcrumb path is *always*
  unambiguous — the path's Kingdom → Genus segments anchor the
  resolution by construction. The 409 case only fires when the
  caller does not supply a breadcrumb. So the slice ships two
  endpoints: `/api/{path}/{genus}/{epithet}` (200/404, canonical) and
  `/api/species/{genus}/{epithet}` (200/404/409, lookup-by-pair).
  Both share the `SpeciesLookupResponse` shape.

- **Pagination cursor uses canonical names, not ids.** Names are
  immutable once captured; ids are not. A re-import with the same
  source yields the same cursor pagination. The trade-off is that
  two taxa sharing a case-folded name would break the cursor — but
  the dataset's `Taxon.name` is unique within a parent, so the
  cursor's tie-breaker on the raw `Taxon.name` keeps pagination
  deterministic.

- **`/species` response shape changed from Sub-PR 2B.** Sub-PR 2B
  returned a bare `list[TaxonResponse]`; Sub-PR 2C wraps it in an
  envelope `{items: [...], next_cursor: str | None}`. The 2B
  tests were updated to unwrap the envelope; the wire shape for
  existing consumers is a breaking change but the cascade UI
  does not yet exist so no client is affected.

- **`AmbiguityCandidate` replaced `CandidateRef` on the wire.**
  Sub-PR 2A defined `CandidateRef(id, breadcrumb)` because the
  ambiguity use case was speculative. Sub-PR 2C needed
  `canonical_name` + `display_name` on each candidate so the UI
  can render the disambiguation list without a second request.
  The 2A `ErrorResponse` test was updated to use
  `AmbiguityCandidate`; the response shape for plain 404s
  (which omit `candidates`) is unchanged.

- **`pathlib.Path` renamed to `PathLib` in router.py.** FastAPI
  exposes `fastapi.Path` for path parameters and the import line
  `from pathlib import Path` shadowed it. The router module is the
  only place where the conflict surfaced; aliasing to `PathLib`
  resolves it without touching other modules.