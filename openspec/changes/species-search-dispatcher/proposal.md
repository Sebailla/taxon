# Proposal: Species Search Dispatcher

## Intent
Today the user navigates the WoRMS taxonomy and per-species search links through a Google Sheets spreadsheet that is hard to maintain, hard to share, and offers no programmatic access. This change replaces the spreadsheet with a typed backend (Python + FastAPI + SQLite) plus a React cascading-select UI so both researchers and aquarists can browse Kingdom→Genus, pick a species, and dispatch to the same 12 search sources the sheet encodes today.

## Scope
### In Scope
- One end-to-end foundational PR: backend parser, SQLite schema, FastAPI endpoints, React UI, one dataset slice green.
- 12 search-link endpoints/URLs matching `docs/sources/templates.md` verbatim, including the literal M9 Photos URL.
- HTTP 409 Conflict with `candidates[]` for ambiguous species lookups.
- 5 cascading dropdowns (Kingdom→Phylum→Class→Order→Family→Genus) + 6th fixed scrollable species list.
- Toggle filters for extinct (`†`), synonyms (`=`), uncertain (`?`), unassigned; default accepted-only.
### Out of Scope
- Auth, multi-user, write paths (taxon is read-only).
- Production hosting, Docker, cloud deploy.
- E2E Playwright suite (optional layer, deferred).
- Localization beyond the existing Spanish UI copy.

## Capabilities
### New Capabilities
- `taxonomy-hierarchy`: browse Kingdom→Genus via path-name URL-encoded routes.
- `species-list-by-genus`: list species for a given Genus (6th list).
- `species-lookup`: resolve a (genus, epithet) pair; return 409 with candidates on ambiguity.
- `species-search-links`: emit 12 dispatch URLs per species, verbatim from the sheet templates.
- `inclusion-filters`: toggle extinct/synonyms/uncertain/unassigned; default accepted-only.
### Modified Capabilities
- (none — greenfield)

## Approach
SQLite adjacency-list (`taxa` table with `parent_id`) plus a materialized `species_paths` projection for O(1) hierarchy lookup. Streaming parser over `dataset-2011.txt` (1,394,847 lines) with batched inserts and benchmarked acceptance criteria. FastAPI exposes path-name URL-encoded routes (`/api/kingdoms/{k}/phyla/{p}/.../genera/{g}/species`). Ambiguity resolved by returning HTTP 409 with full breadcrumb candidates so the UI can show a picker. React 18 + Vite + TailwindCSS 3 SPA with five cascading dropdowns and a fixed sixth species list. Strict TDD from the parser outward: failing test → impl → green. First PR is monolithic and foundational; subsequent changes split by capability.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `/Users/sebailla/Developer/taxon/` | New | greenfield project root |
| `/Users/sebailla/Developer/research/worm/dataset-2011.txt` | Read-only source | input data (1.39M lines, WoRMS-2011) |
| `/Users/sebailla/Developer/taxon/docs/sources/templates.md` | New | search-link templates captured from sheet |
| `taxon/data/taxon.db` | New (local) | SQLite DB, deletable for rollback |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 1.39M-row import performance | Med | streaming parser, batched SQLite inserts, indexed acceptance benchmarks |
| Genus name collisions across parents | High (known) | API returns 409 with candidates; UI shows picker |
| Photos URL contains tracking params that may rot | Low | preserved verbatim for sheet parity; env override noted |
| HTTP vs HTTPS mixed content | Low | preserved for sheet parity; security caveat in README |
| Part-file boundaries mid-branch | Med | re-stream from original dataset, not the 4 split parts |
| Branching policy confusion | Low | AGENTS.md documented; first PR explicitly targets develop |
| UI workflow gate skipped | Med | Pencil MCP + impeccable review MUST precede any UI code |

## Rollback Plan
- Revert the PR that introduces the foundational backend+frontend slice.
- Database is local SQLite under `taxon/data/taxon.db` — delete the file to drop schema and data.
- No external dependencies or cloud resources to roll back.

## Dependencies
- `/Users/sebailla/Developer/research/worm/dataset-2011.txt` must remain readable (read-only).
- Python 3.11+, Node 20+.
- No external SaaS dependencies.

## Success Criteria
- [ ] `/api/kingdoms/{name}/phyla/{name}/.../genera/{name}/species` returns species list.
- [ ] `/api/species/{genus}/{epithet}/links` returns 12 search links with URLs matching the sheet templates verbatim.
- [ ] Ambiguous species lookups return HTTP 409 with `candidates[]`.
- [ ] React UI shows 5 cascading dropdowns + fixed species list; toggles for extinct/synonyms.
- [ ] pytest + vitest suites green; CI on `develop` green.
- [ ] `/learn-es/2026-08-09-...` entry created after merge.

## Operational Notes
- PR targets `develop` (never `main`). Worktree under `../taxon-worktrees/species-search-dispatcher`.
- UI design MUST be authored in Pencil MCP and audited under `impeccable` before any frontend code lands.
- Conventional commits; no AI attribution; messages in English (`docs(es): …` for Spanish-only docs).
- Every artifact (this proposal included) MUST have a Spanish mirror under `/documents-es/openspec/`.
