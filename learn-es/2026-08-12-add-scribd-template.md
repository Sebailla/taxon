# Add Scribd as the 13th search-source template (PR #25)

## What

Added `Scribd` as the 13th search-source template at the end of
the dispatch list (after Sci-hub). The URL is the verbatim
`https://es.scribd.com/search?query={q}`, following the same
`{q}` substitution convention as the other 12 templates. Bumped
the `load_templates` count guard from 12 to 13 and updated two
test files to expect 13 templates.

This is the first new template added since the original 12 were
captured from the legacy Google Sheet on 2026-08-09.

## How

### Templates file

One new row in `docs/sources/templates.md`:

```markdown
| Sci-hub      | `https://sci-hub.ru/match/{q}` (substitutes species) |
| Scribd       | `https://es.scribd.com/search?query={q}` |
```

Order is preserved by the parser regex; adding a row at the end
places Scribd last in the dispatch grid.

### Count guard

`taxon/search_links.py`:

```python
if len(templates) != 13:
    raise ValueError(f"Expected exactly 13 search templates, found {len(templates)}")
```

The guard exists to catch drift between the spreadsheet (now
templates.md) and the test expectations. Every future template
addition requires bumping this number and the corresponding test
asserts.

### Tests

`taxon/tests/test_search_links.py`:

- `test_load_templates_preserves_exact_order_and_verbatim_urls`
  now asserts the 13-tuple ordered list ending in `"Scribd"`,
  checks the new URL at index `-1`, and re-points the existing
  Sci-hub and Photos asserts to indices `-2` and `-3`
  respectively.
- `test_build_search_links_uses_quote_plus_for_every_template`
  asserts the substituted URLs end with the Scribd-encoded query
  and the second-to-last is still Sci-hub.

`taxon/tests/test_api_species_links.py`:

- The envelope-count test renamed from
  `test_links_envelope_emits_exactly_twelve_links` to
  `..._thirteen_links`, count 12 → 13.
- The order test reads from templates.md at runtime, so it picks
  up the new row automatically. Only the docstring is updated.

The order test reads from disk at every run, which makes the
suite resilient to additions/removals as long as the templates
file stays the single source of truth.

## Where

- `docs/sources/templates.md` — one row added.
- `taxon/search_links.py` — count guard bumped.
- `taxon/tests/test_search_links.py` — order + count assertions.
- `taxon/tests/test_api_species_links.py` — count assertion + docstrings.

## Why

The 12 templates shipped in PR #16 came from the legacy Google
Sheet captured on 2026-08-09. This is the first new template
since then, requested explicitly to expand the dispatch options
for Spanish-speaking users of the species search tool. The
Scribd search URL was captured from the upstream endpoint; no
JS-rendered DOM was needed to discover the query parameter.

### On the modal/iframe question

The user also asked whether Scribd could open in an in-app modal
iframe instead of a new tab. I investigated the upstream site
before committing: `https://es.scribd.com/search?query=...`
returns a Cloudflare/F5 anti-bot "Client Challenge" shell under
`Content-Security-Policy: default-src 'self'`, which blocks
cross-origin framing from any non-scribd domain. An iframe
inside `taxon.localhost` would show the challenge page, not the
search results — a worse UX than opening a new tab. The new
source therefore keeps the same `<a target="_blank">` behaviour
as the other 12 for consistency. The decision is documented in
the PR body so future readers do not re-litigate it.

## How it works

When the user clicks a species row:

1. The Cascade dispatches the `taxon:select` event with the
   resolved breadcrumb + parent segments (now Zod-validated per
   PR #24).
2. The App builds `/api/{path}/{genus}/{epithet}/links` (with the
   genus segment included, per PR #22).
3. The FastAPI endpoint calls `load_templates()` which reads
   `docs/sources/templates.md` and returns 13 ordered templates.
4. `build_search_links()` substitutes `quote_plus(species)` into
   each template. The 13th template (Scribd) yields
   `https://es.scribd.com/search?query={encoded_species}`.
5. The endpoint returns the 13-link envelope; the frontend
   renders the 4-column grid with Scribd at position 13
   (visually below Sci-hub in the same row flow).

## Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). All green. The lighthouse job audits the
  production frontend bundle which includes the new link
  source as a button — no accessibility regression because
  `<a target="_blank" rel="noopener noreferrer">` already
  covers all 13 sources.
- **Reviews** — 2 `work-unit-commits`:
  1. `f66b37a test(backend): add Scribd as the 13th search-source template (RED-first)`
  2. `77d44b6 feat(backend): add Scribd as the 13th search-source template`
- **Future additions** — when the spreadsheet gains a 14th row,
  the workflow is: edit `templates.md`, bump the count guard,
  bump the order tuple test, bump the count assertion. No other
  code changes needed.

## Lessons learned

- **The count guard in `load_templates` is a drift detector, not
  an arbitrary limit.** It catches the failure mode where
  someone edits `templates.md` without updating the tests. Worth
  keeping, even though it adds a tiny maintenance burden on each
  addition.
- **`X-Frame-Options` and CSP `frame-ancestors` are silent
  contract changes for any "embed an external site" feature.**
  Always check `curl -sI` for the response headers before
  promising iframe embedding to a user. The Cloudflare/F5
  challenge page is the most common blocker for academic
  sources (Sci-hub, ResearchGate, Academia.edu are all in the
  same boat).
- **The order test reads from `templates.md` at runtime** — that
  pattern (assert against the live doc, not a hardcoded list)
  scales better than maintaining two sources of truth. The
  hardcoded list in `test_search_links.py` is still there
  because it also pins the Photos URL stability and the Sci-hub
  source position; for pure order checks the disk-read version
  wins.
- **`work-unit-commits` keeps RED and GREEN readable in
  isolation.** A reviewer can read the test commit and see
  exactly what the contract is, then read the implementation
  commit and see exactly what changed to satisfy it.
