# Design: Species Search Dispatcher

## Technical Approach
Build a read-only FastAPI service over SQLite and a React 18/Vite/Tailwind SPA. A streaming, single-pass parser reads `/Users/sebailla/Developer/research/worm/dataset-2011.txt`, maintains an indentation stack, inserts every taxon in batches, and emits a denormalized `species_paths` row for each species. Strict TDD proceeds parser → schema/import → queries/API → typed client/components. Pencil MCP design and an `impeccable` audit gate all frontend implementation.

## Architecture Decisions

### Decision: SQLite adjacency-list + `species_paths` projection
**Choice**: `taxa(parent_id)` preserves every rank/status; `species_paths` stores the complete Kingdom→Species breadcrumb and marker flags.
**Alternatives**: Recursive CTEs per request add read cost; per-rank tables cannot faithfully model irregular/infraspecific depths.
**Rationale**: Direct hierarchy/species queries, deterministic ambiguity candidates, and full source fidelity.

### Decision: Stream the original dataset
**Choice**: Parse `/Users/sebailla/Developer/research/worm/dataset-2011.txt` with O(n) time, O(depth) memory, and batched transactions.
**Alternatives**: Independently parsing four split parts.
**Rationale**: A split may start mid-branch and lose ancestor state.

### Decision: Encoded path names with explicit ambiguity
**Choice**: Case-insensitive path-name resolution; unknown segments return 404, collisions return 409 with stable `candidates[]` breadcrumbs. Numeric IDs remain response/candidate identifiers.
**Alternatives**: ID-only routes.
**Rationale**: Meets the readable-route contract without guessing among duplicate names.

### Decision: Templates are loaded from the documentation source
**Choice**: Parse `docs/sources/templates.md` once at application startup into an immutable ordered set of 12 templates; substitute every template with `quote_plus(species, safe='')`, including Sci-hub (`https://sci-hub.ru/match/{q}`).
**Alternatives**: Duplicate templates in Python.
**Rationale**: Prevents drift and preserves the literal M9 Photos URL.

### Decision: Cascade fetches one level at a time
**Choice**: Each selection fetches only the next rank; parent changes clear descendants and abort stale requests. The sixth surface is a fixed, cursor-paginated species list (500 maximum/page).
**Alternatives**: Send the 1.39M-row tree to the browser.
**Rationale**: Predictable payloads and responsive navigation.

## Data Flow

```text
dataset-2011.txt -> streaming parser -> batched taxa inserts
                                          |
                                          v
                                 species_paths projection
                                          |
                         FastAPI queries/routes (404/409)
                             |                    |
                       React cascade      12-link builder
```

## File Changes

| File | Action | Description |
|---|---|---|
| `pyproject.toml`, `.gitignore` | Create | Python/tooling dependencies; ignore generated DB/caches. |
| `taxon/db.py`, `taxon/schema.py` | Create | Engine/session and `Taxon`/`SpeciesPath` models with indexes. |
| `taxon/parser.py`, `taxon/import_data.py` | Create | Stack parser and idempotent batched import CLI. |
| `taxon/search_links.py` | Create | Immutable template loader and exact URL builder. |
| `taxon/api/{__init__,router,schemas}.py`, `taxon/main.py` | Create | App factory, response models, hierarchy/species/link routes. |
| `tests/test_{parser,schema,import_data,api_hierarchy,api_species,api_links}.py` | Create | Backend RED-first unit/integration coverage. |
| `frontend/` | Create | Vite/React/Tailwind config and app shell. |
| `frontend/src/{api,Cascade,Toggles,SpeciesLinks,AmbiguityPicker}.tsx` | Create | Typed client and UI behavior. |
| `frontend/tests/` | Create | Vitest/Testing Library component tests. |
| `.pen` | Create via Pencil MCP | Approved UI design; never accessed as plain text. |
| `README.md`, `documents-es/README-es.md` | Create | Run/import instructions and Spanish mirror. |
| `data/taxon.db` | Generate, gitignored | Rebuildable SQLite database. |

## Interfaces / Contracts

`Taxon` stores source ID, parent, rank, canonical/display names, and four boolean markers. `SpeciesPath` stores species ID, canonical ranks through genus, species name/display, and markers. Hierarchy responses contain exactly `{id,name,display_name}`. Species pages contain `items[]` plus optional opaque `next_cursor`; `include` recognizes four classes with OR semantics and ignores unknown values. Unique lookup returns species plus breadcrumb; ambiguity returns `409 {"candidates":[...]}` ordered by breadcrumb. Links return exactly 12 `{source,label,url}` entries in template order.

Routes cover `/api/kingdoms`, successive encoded Kingdom→Genus child paths, `/species?include=&cursor=`, and `/api/species/{genus}/{epithet}/links`; a fully qualified breadcrumb lookup resolves a selected 409 candidate.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit BE | Parser/schema/links | Markers and combinations, quoted Candidatus, irregular depth, exact templates, Photos, Sci-hub, `quote_plus`. |
| Integration BE | Import/API | Temporary SQLite; counts/integrity; case-insensitive paths; stable ordering; 404/409; filters; 500-item cursor. |
| Unit/Component FE | Client/cascade/UI | 409 typing, descendant reset, abort races, toggles OR semantics, loading/error/empty, 12 links and breadcrumbs. |
| E2E | Full flow | Deferred/optional Playwright. |

## Threat Matrix
HTTP routing is application behavior, but the specialized execution/automation boundaries are N/A: no documentation execution, Git selection, commit/push handling, PR commands, shell, subprocess, or process integration.

## Migration / Rollout
Greenfield; regenerate with `python -m taxon.import_data`. No feature flags. The first foundational PR is intentionally monolithic.

## Open Questions
None blocking.