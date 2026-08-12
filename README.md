# Taxon

A read-only species search dispatcher. Taxon replaces the legacy
Google Sheets navigator "Buscador de Especies Acuáticas"
(`gid=1295156649`) with a FastAPI + SQLite backend and a React
frontend that walks the WoRMS taxonomic cascade from Kingdom down
to Genus and emits 12 dispatch URLs per resolved species.

The system is built around four slices shipped as chained pull
requests against `develop`:

| Slice | PR | What it adds |
| --- | --- | --- |
| Phase 1 | [#2](https://github.com/Sebailla/taxon/pull/2) | Streaming parser, SQLAlchemy schema, batched importer, search-link templates. |
| Phase 2A | [#4](https://github.com/Sebailla/taxon/pull/4) | FastAPI factory, Pydantic schemas, `/healthz`, uvicorn entrypoint. |
| Phase 2B | [#6](https://github.com/Sebailla/taxon/pull/6) | Cascade endpoints (Kingdom → Phylum → … → Genus → species). |
| Phase 2C | [#8](https://github.com/Sebailla/taxon/pull/8) | Species lookup with 200/404/409, inclusion filters, dispatch links. |
| Phase 3 | [#10](https://github.com/Sebailla/taxon/pull/10) | Pencil design (`taxon.pen`) + impeccable audit. |
| Phase 4 | [#12](https://github.com/Sebailla/taxon/pull/12) | React + Vite + Tailwind frontend. |
| Phase 5 | (this README) | Docs + frontend CI + final `/learn-es/`. |

## Architecture

```
┌────────────────┐    ┌─────────────────────────┐    ┌──────────────────┐
│  React + Vite  │───▶│  FastAPI + SQLAlchemy  │───▶│  SQLite (taxon.db)│
│  + Tailwind    │    │  + Pydantic             │    │  + taxa table    │
│  (frontend/)   │    │  (taxon/api/*)          │    │  + species_paths │
└────────────────┘    └─────────────────────────┘    └──────────────────┘
        ▲                          │
        │                          ▼
        │                  ┌────────────────────┐
        │                  │  taxon.import_data  │
        │                  │  (streaming parser) │
        │                  └────────────────────┘
        │                          │
        │                          ▼
        │                  ┌────────────────────┐
        │                  │  WoRMS dataset      │
        │                  │  dataset-2011.txt   │
        │                  └────────────────────┘
```

The frontend is a pure SPA. In development, Vite proxies `/api` to
`http://127.0.0.1:8000`. In production, the same backend serves
the built `frontend/dist/` assets.

## Repository layout

```
taxon/
├── taxon/                 # Backend (Python)
│   ├── parser.py          # Streaming indentation-stack parser
│   ├── schema.py          # SQLAlchemy models (Taxon, SpeciesPath)
│   ├── import_data.py     # Batched streaming importer
│   ├── search_links.py    # 12 search-source URL templates
│   ├── main.py            # Uvicorn entrypoint
│   └── api/               # FastAPI surface
│       ├── __init__.py    # App factory + lifespan + exception handlers
│       ├── router.py      # 12 cascade + lookup + links endpoints
│       ├── schemas.py     # Pydantic response models
│       ├── hierarchy.py   # Path-name resolver
│       ├── species.py     # Species list + lookup helpers
│       ├── errors.py      # HTTP-mapped exception classes
│       └── db.py          # Request-scoped session dependency
├── frontend/              # Frontend (TypeScript + React)
│   ├── src/
│   │   ├── api.ts         # Typed API client
│   │   ├── App.tsx        # Root composition
│   │   ├── components/
│   │   │   ├── Cascade.tsx
│   │   │   ├── Toggles.tsx
│   │   │   ├── SpeciesList.tsx
│   │   │   ├── SpeciesLinks.tsx
│   │   │   ├── AmbiguityPicker.tsx
│   │   │   └── Breadcrumb.tsx
│   │   └── index.css      # Tailwind + design tokens
│   ├── tests/             # Vitest + Testing Library
│   ├── tailwind.config.js # Design tokens (Phase 3 audit follow-ups)
│   └── vite.config.ts     # Dev server with /api proxy
├── taxon.pen              # Pencil design (Phase 3)
├── docs/                  # English documentation
│   ├── design/            # Audit, approval, blocked log
│   ├── sources/           # Captured WoRMS source + link templates
│   └── ci.md              # CI workflow contract
├── documents-es/          # Spanish mirrors
├── learn-es/              # Post-merge learning entries
├── openspec/              # Spec-Driven Development artifacts
├── pyproject.toml         # Python packaging
└── .github/workflows/
    └── ci.yml             # Backend + frontend CI
```

## Setup

### Prerequisites

- Python 3.11+ (3.11 and 3.12 are CI-tested).
- Node 20+ for the frontend.
- A WoRMS taxonomy dump. The repo ships with a reference fixture;
  real data lives at `/Users/sebailla/Developer/research/worm/dataset-2011.txt`
  or any file matching the WoRMS text format.

### Backend

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Build the SQLite database from the WoRMS dump:
.venv/bin/python -m taxon.import_data \
    /path/to/dataset-2011.txt ./data/taxon.db

# Run the API server:
.venv/bin/python -m taxon.main
# → uvicorn running on http://127.0.0.1:8000
```

The lifespan on startup checks the database URL; in-memory SQLite
(used by tests) auto-creates the schema, file-backed SQLite
assumes the schema already exists from the import step.

### Frontend

```bash
cd frontend
npm install
npm run dev
# → Vite dev server on http://127.0.0.1:5173 (proxies /api to :8000)
```

To build a production bundle:

```bash
npm run build
# → dist/ ready to serve from the backend
```

## Development workflow

### Tests

```bash
# Backend (Python)
.venv/bin/python -m pytest -v               # all tests
.venv/bin/python -m pytest -v taxon/tests/test_api_hierarchy.py
.venv/bin/python -m mypy taxon/              # strict mode
.venv/bin/python -m ruff check .            # lint
.venv/bin/python -m ruff format --check .   # format check

# Frontend (TypeScript)
cd frontend
npm test            # vitest, single run
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # production bundle
```

### Branching and PRs

- All integration happens on `develop`. `main` is production and
  only receives release PRs.
- Work happens in a worktree under `../taxon-worktrees/<name>`.
- Every feature / fix lands as a PR against `develop` with a
  linked approved issue (`status:approved`).
- Commit messages follow Conventional Commits. No
  `Co-Authored-By` trailers.
- CI runs on every PR; both backend (Python 3.11 + 3.12) and
  frontend (Vitest + typecheck + build) must pass.

### Spec-driven development

OpenSpec artifacts live under `openspec/`:

- `openspec/changes/species-search-dispatcher/` — proposal, design,
  tasks for the change that built Taxon.
- `openspec/specs/` — full delta specs for taxonomy-hierarchy,
  species-lookup, species-search-links, species-list-by-genus,
  inclusion-filters.

Future changes follow the same pattern: proposal → specs → design
→ tasks → apply → verify → archive.

## API summary

Every endpoint is mounted under `/api`. The frontend hits them
through the Vite proxy in dev, and through the same origin in
production.

| Method | Path | Behaviour |
| --- | --- | --- |
| GET | `/healthz` | Liveness probe. |
| GET | `/api/_meta` | Smoke check (returns `{"phase": "2B"}`). |
| GET | `/api/kingdoms` | List every Kingdom-rank taxon. |
| GET | `/api/{kingdom}/phyla` | Phylum children. |
| GET | `/api/{kingdom}/{phylum}/classes` | Class children. |
| GET | `/api/{kingdom}/{phylum}/{class}/orders` | Order children. |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/families` | Family children. |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/genera` | Genus children. |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species` | Paginated species list (cap 500). |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}` | Single-species lookup (200/404). |
| GET | `/api/species/{genus}/{epithet}` | Pair-only lookup (200/404/409). |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}/links` | 12 dispatch URLs. |

Path-name semantics are case-insensitive against the canonical
`Taxon.name`. Each segment is anchored on the parent identified by
the previous segment; the path's rank context disambiguates same-
named taxa under different parents.

The species list accepts `include=synonyms,extinct,uncertain,unassigned`
(CSV, OR semantics, unknown values ignored, default accepted-only)
and `cursor=<opaque>` for pagination after the 500-item cap.

## Design

The cascade UI follows the Pencil design in `taxon.pen` (Phase 3).
The design was generated via the Pencil CLI (`pen --agent codex`)
and audited under the `impeccable` skill (17/20, Good). Two follow-ups
from the audit land in the React implementation:

- Badge backgrounds use Tailwind tokens (`bg-red-50`, `bg-amber-50`,
  `bg-green-50`, `bg-blue-50`) instead of the 10 hard-coded hex
  values from the design.
- The font stack declares `system-ui, Inter, sans-serif` so the
  user's OS font wins before Inter loads.

`docs/design/design-audit.md` documents the audit. `docs/design/approval.md`
records the sign-off. `docs/design/blocked.md` documents the Pencil
MCP server bug we hit before pivoting to the CLI.

## Acceptance evidence

- **Backend**: 80 tests across 6 files (parser, schema, importer,
  search-links, app factory, hierarchy, species-list, species-lookup,
  species-links). `mypy --strict` clean. `ruff check` + `ruff format
  --check` clean.
- **Frontend**: 28 tests (19 API client + 9 component). TypeScript
  strict mode clean. ESLint clean. Production build 154 KB JS / 49
  KB gzip.
- **End-to-end**: backend on `:8000`, frontend on `:5173` with
  the `/api` proxy. Resolve a species like `Girardinichthys
  multiradiatus` to see the 12-link grid render.

## License

This project is private research code. No license granted at this
time.