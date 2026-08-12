# Taxon

Un despachador de búsqueda de especies de solo lectura. Taxon
reemplaza el navegador legacy de Google Sheets "Buscador de
Especies Acuáticas" (`gid=1295156649`) con un backend FastAPI +
SQLite y un frontend React que recorre la cascada taxonómica de
WoRMS desde Reino hasta Género y emite 12 URLs de despacho por
cada especie resuelta.

El sistema se construyó en cuatro rebanadas enviadas como pull
requests encadenados contra `develop`:

| Rebanada | PR | Qué agrega |
| --- | --- | --- |
| Fase 1 | [#2](https://github.com/Sebailla/taxon/pull/2) | Parser en streaming, esquema SQLAlchemy, importador por lotes, plantillas de enlaces de búsqueda. |
| Fase 2A | [#4](https://github.com/Sebailla/taxon/pull/4) | Factoría FastAPI, esquemas Pydantic, `/healthz`, entrypoint uvicorn. |
| Fase 2B | [#6](https://github.com/Sebailla/taxon/pull/6) | Endpoints de cascada (Reino → Filo → … → Género → especie). |
| Fase 2C | [#8](https://github.com/Sebailla/taxon/pull/8) | Búsqueda de especie con 200/404/409, filtros de inclusión, enlaces de despacho. |
| Fase 3 | [#10](https://github.com/Sebailla/taxon/pull/10) | Diseño Pencil (`taxon.pen`) + auditoría impeccable. |
| Fase 4 | [#12](https://github.com/Sebailla/taxon/pull/12) | Frontend React + Vite + Tailwind. |
| Fase 5 | (este README) | Documentación + CI del frontend + `/learn-es/` final. |

## Arquitectura

```
┌────────────────┐    ┌─────────────────────────┐    ┌──────────────────┐
│  React + Vite  │───▶│  FastAPI + SQLAlchemy  │───▶│  SQLite (taxon.db)│
│  + Tailwind    │    │  + Pydantic             │    │  + tabla taxa     │
│  (frontend/)   │    │  (taxon/api/*)          │    │  + species_paths │
└────────────────┘    └─────────────────────────┘    └──────────────────┘
        ▲                          │
        │                          ▼
        │                  ┌────────────────────┐
        │                  │  taxon.import_data  │
        │                  │  (parser streaming) │
        │                  └────────────────────┘
        │                          │
        │                          ▼
        │                  ┌────────────────────┐
        │                  │  Dataset WoRMS       │
        │                  │  dataset-2011.txt   │
        │                  └────────────────────┘
```

El frontend es un SPA puro. En desarrollo, Vite hace proxy de
`/api` a `http://127.0.0.1:8000`. En producción, el mismo backend
sirve los assets construidos de `frontend/dist/`.

## Distribución del repositorio

```
taxon/
├── taxon/                 # Backend (Python)
│   ├── parser.py          # Parser en streaming con pila de indentación
│   ├── schema.py          # Modelos SQLAlchemy (Taxon, SpeciesPath)
│   ├── import_data.py     # Importador por lotes en streaming
│   ├── search_links.py    # 12 plantillas de URLs de búsqueda
│   ├── main.py            # Entrypoint uvicorn
│   └── api/               # Superficie FastAPI
│       ├── __init__.py    # Factoría de app + lifespan + manejadores de excepciones
│       ├── router.py      # 12 endpoints de cascada + búsqueda + enlaces
│       ├── schemas.py     # Modelos de respuesta Pydantic
│       ├── hierarchy.py   # Resolver de path-name
│       ├── species.py     # Lista de especies + helpers de búsqueda
│       ├── errors.py      # Clases de excepción mapeadas a HTTP
│       └── db.py          # Dependencia de sesión por request
├── frontend/              # Frontend (TypeScript + React)
│   ├── src/
│   │   ├── api.ts         # Cliente API tipado
│   │   ├── App.tsx        # Composición raíz
│   │   ├── components/
│   │   │   ├── Cascade.tsx
│   │   │   ├── Toggles.tsx
│   │   │   ├── SpeciesList.tsx
│   │   │   ├── SpeciesLinks.tsx
│   │   │   ├── AmbiguityPicker.tsx
│   │   │   └── Breadcrumb.tsx
│   │   └── index.css      # Tailwind + tokens de diseño
│   ├── tests/             # Vitest + Testing Library
│   ├── tailwind.config.js # Tokens de diseño (seguimiento de auditoría Fase 3)
│   └── vite.config.ts     # Servidor dev con proxy /api
├── taxon.pen              # Diseño Pencil (Fase 3)
├── docs/                  # Documentación en inglés
│   ├── design/            # Auditoría, aprobación, log de bloqueo
│   ├── sources/           # Fuente WoRMS + plantillas de enlaces
│   └── ci.md              # Contrato de workflow CI
├── documents-es/          # Espejos en español
├── learn-es/              # Entradas de aprendizaje post-merge
├── openspec/              # Artefactos de Spec-Driven Development
├── pyproject.toml         # Empaquetado Python
└── .github/workflows/
    └── ci.yml             # CI de backend + frontend
```

## Configuración

### Prerrequisitos

- Python 3.11+ (3.11 y 3.12 están probados en CI).
- Node 20+ para el frontend.
- Un dump de taxonomía WoRMS. El repositorio incluye un fixture
  de referencia; los datos reales viven en
  `/Users/sebailla/Developer/research/worm/dataset-2011.txt` o
  cualquier archivo que coincida con el formato de texto WoRMS.

### Backend

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

# Construir la base de datos SQLite desde el dump de WoRMS:
.venv/bin/python -m taxon.import_data \
    /ruta/al/dataset-2011.txt ./data/taxon.db

# Ejecutar el servidor API:
.venv/bin/python -m taxon.main
# → uvicorn corriendo en http://127.0.0.1:8000
```

El lifespan al arrancar valida la URL de la base de datos; SQLite
en memoria (usado en tests) auto-crea el esquema, SQLite en archivo
asume que el esquema ya existe desde el paso de import.

### Frontend

```bash
cd frontend
npm install
npm run dev
# → Servidor dev de Vite en http://127.0.0.1:5173 (proxy /api a :8000)
```

Para construir un bundle de producción:

```bash
npm run build
# → dist/ listo para servir desde el backend
```

## Flujo de desarrollo

### Tests

```bash
# Backend (Python)
.venv/bin/python -m pytest -v               # todos los tests
.venv/bin/python -m pytest -v taxon/tests/test_api_hierarchy.py
.venv/bin/python -m mypy taxon/              # modo strict
.venv/bin/python -m ruff check .            # lint
.venv/bin/python -m ruff format --check .   # chequeo de formato

# Frontend (TypeScript)
cd frontend
npm test            # vitest, ejecución única
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # bundle de producción
```

### Branching y PRs

- Toda la integración ocurre en `develop`. `main` es producción y
  solo recibe PRs de release.
- El trabajo ocurre en un worktree bajo
  `../taxon-worktrees/<nombre>`.
- Cada feature / fix aterriza como un PR contra `develop` con un
  issue aprobado vinculado (`status:approved`).
- Los mensajes de commit siguen Conventional Commits. Sin trailers
  `Co-Authored-By`.
- CI corre en cada PR; tanto el backend (Python 3.11 + 3.12) como
  el frontend (Vitest + typecheck + build) deben pasar.

### Spec-driven development

Los artefactos de OpenSpec viven bajo `openspec/`:

- `openspec/changes/species-search-dispatcher/` — propuesta, diseño,
  tasks del cambio que construyó Taxon.
- `openspec/specs/` — specs delta completas para taxonomy-hierarchy,
  species-lookup, species-search-links, species-list-by-genus,
  inclusion-filters.

Cambios futuros siguen el mismo patrón: propuesta → specs → diseño
→ tasks → apply → verify → archive.

## Resumen de la API

Cada endpoint está montado bajo `/api`. El frontend los consume
a través del proxy de Vite en dev, y del mismo origen en
producción.

| Método | Path | Comportamiento |
| --- | --- | --- |
| GET | `/healthz` | Probe de liveness. |
| GET | `/api/_meta` | Smoke check (devuelve `{"phase": "2B"}`). |
| GET | `/api/kingdoms` | Lista todos los taxa de rango Kingdom. |
| GET | `/api/{kingdom}/phyla` | Hijos Phylum. |
| GET | `/api/{kingdom}/{phylum}/classes` | Hijos Class. |
| GET | `/api/{kingdom}/{phylum}/{class}/orders` | Hijos Order. |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/families` | Hijos Family. |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/genera` | Hijos Genus. |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species` | Lista paginada de especies (cap 500). |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}` | Búsqueda de especie única (200/404). |
| GET | `/api/species/{genus}/{epithet}` | Búsqueda por par (200/404/409). |
| GET | `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}/links` | 12 URLs de despacho. |

La semántica de path-name es case-insensitive contra el `Taxon.name`
canónico. Cada segmento se ancla al padre identificado por el
segmento previo; el contexto de rango del path desambigua taxa con
el mismo nombre bajo distintos padres.

La lista de especies acepta
`include=synonyms,extinct,uncertain,unassigned` (CSV, semántica OR,
valores desconocidos ignorados, default accepted-only) y
`cursor=<opaque>` para paginación después del cap de 500 items.

## Diseño

La UI de cascada sigue el diseño Pencil en `taxon.pen` (Fase 3).
El diseño fue generado vía el CLI de Pencil (`pen --agent codex`)
y auditado bajo el skill `impeccable` (17/20, Bien). Dos
seguimientos de la auditoría aterrizan en la implementación React:

- Los fondos de badges usan tokens de Tailwind (`bg-red-50`,
  `bg-amber-50`, `bg-green-50`, `bg-blue-50`) en lugar de los 10
  valores hex codificados del diseño.
- El stack tipográfico declara `system-ui, Inter, sans-serif` para
  que la fuente del sistema operativo del usuario gane antes de
  que Inter cargue.

`docs/design/design-audit.md` documenta la auditoría.
`docs/design/approval.md` registra la firma.
`docs/design/blocked.md` documenta el bug del servidor MCP de
Pencil que encontramos antes de pivotar al CLI.

## Evidencia de aceptación

- **Backend**: 80 tests en 6 archivos (parser, schema, importer,
  search-links, app factory, hierarchy, species-list,
  species-lookup, species-links). `mypy --strict` limpio.
  `ruff check` + `ruff format --check` limpios.
- **Frontend**: 28 tests (19 de cliente API + 9 de componentes).
  TypeScript modo strict limpio. ESLint limpio. Build de
  producción 154 KB JS / 49 KB gzip.
- **End-to-end**: backend en `:8000`, frontend en `:5173` con el
  proxy `/api`. Resolver una especie como `Girardinichthys
  multiradiatus` para ver el grid de 12 enlaces renderizado.

## Licencia

Este proyecto es código de investigación privado. No se concede
licencia en este momento.