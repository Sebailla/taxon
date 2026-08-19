# SETUP — Cómo levantar el sistema

> **Alcance**: instrucciones para levantar Taxon (backend FastAPI + frontend React) en local desde cero en macOS, Linux o WSL. Cubre los dos modos de operación: una **demo rápida** con la base ya poblada en `data/taxon.db`, y la **carga completa** desde el dataset original.
>
> **Audiencia**: developer técnicas/os que clonan el repo y necesitan el sistema corriendo en menos de 10 minutos.
>
> **Convención de fuentes**: el **importador** parsea el dataset **WoRMS** (`dataset-2011.txt` — World Register of Marine Species) y vuelca la jerarquía completa a SQLite. El **árbol que ve el usuario en pantalla** es **CoL** (Catalogue of Life) — 5 roots: Eukaryota, Archaea, Bacteria, Viruses, incertae sedis. La base `data/taxon.db` contiene ambas jerarquías fusionadas; la UI siempre muestra los 5 roots CoL.

## Prerrequisitos

| Herramienta | Versión mínima | Verificación |
|-------------|-----------------|--------------|
| Python | 3.11 (CI prueba 3.11 + 3.12) | `python3 --version` |
| Node.js | 20 (CI prueba 20 LTS) | `node --version` |
| npm | 10 (incluido con Node 20) | `npm --version` |
| git | 2.30+ | `git --version` |
| Compilador C mínimo | cualquiera (para `pysqlite` si es necesario) | `gcc --version` o `clang --version` |

**Para la carga completa desde el dataset original** (opcional, ya viene demo poblada en `data/taxon.db`):

- Dataset **WoRMS** `dataset-2011.txt` (~1.39M líneas, World Register of Marine Species). No se incluye en el repo por tamaño. Bájalo desde el sitio oficial de WoRMS (https://www.marinespecies.org/) o úsalo desde tu copia local. La importación se hace con `python -m taxon.import_data`.

## 1. Clonar el repo

```bash
git clone https://github.com/Sebailla/taxon.git
cd taxon
```

## 2. Levantar el backend

El backend expone la API REST bajo `/api/*`. Arranca en `http://127.0.0.1:8000`.

### 2.1 Crear el virtualenv e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

`.[dev]` instala las dependencias de runtime (`fastapi`, `pydantic`, `sqlalchemy`, `uvicorn`) más las de dev (`pytest`, `mypy`, `ruff`, `httpx`).

### 2.2 Decidir qué base de datos usar

Hay dos opciones:

**A. Demo rápida — usar la base ya poblada `data/taxon.db`**

La base pre-poblada ya está en el repo. La crea el importador en CI desde `dataset-2011.txt` y la commitea; la abres directamente sin correr el import tú.

```bash
# .env o export directo
export TAXON_DATABASE_URL="sqlite:///./data/taxon.db"
```

**B. Carga completa — importar el dataset WoRMS original**

Si querés partir de cero o actualizar la base, importá el dataset WoRMS:

```bash
# 1. Bajar dataset-2011.txt (no incluido en el repo) a algún path
ls /path/to/dataset-2011.txt

# 2. Importar — flags opcionales: --database <ruta>, --source <ruta>
#    Por defecto: source=/Users/sebailla/Developer/research/worm/dataset-2011.txt
#                 database=data/taxon.db
python -m taxon.import_data --source /path/to/dataset-2011.txt --database ./data/taxon.db
```

La base resultante contiene tanto la jerarquía WoRMS (padres del cascade) como la jerarquía CoL (los 5 roots que ve la UI). La UI siempre muestra CoL.

**3. Aplicar migraciones** (idempotente — crea las 3 tablas del workspace + asegura el índice compuesto `ix_taxa_parent_rank_name`):

```bash
python -m taxon.migrate apply
```

Flags útiles:
- `--only-index`: solo crea los índices, salta la creación de tablas.
- `--skip-indexes`: solo crea las tablas, salta los índices.

Para preview sin tocar la base:

```bash
python -m taxon.migrate dry-run
```

### 2.3 Arrancar el servidor

```bash
python -m taxon.main
# → uvicorn running on http://127.0.0.1:8000
```

En otra terminal, verificá que está vivo:

```bash
curl http://127.0.0.1:8000/healthz
# → {"status":"ok"}

curl http://127.0.0.1:8000/api/_meta
# → {"phase": "2B"}
```

Probá navegar el árbol taxonómico (siempre CoL — 5 roots):

```bash
# Roots de la cascada (5 CoL kingdoms)
curl -s 'http://127.0.0.1:8000/api/tree/children?parent_id=0' | jq '.children[].name'

# Expandir Animalia (id depende de la base; ver /api/_meta)
curl -s 'http://127.0.0.1:8000/api/tree/children?parent_id=<animalia_id>' | jq '.next_tiers[0]'
```

## 3. Levantar el frontend

El frontend es un SPA React + Vite + Tailwind. En dev corre en `http://127.0.0.1:5173` y proxea `/api/*` al backend en `:8000`.

```bash
cd frontend
npm install
npm run dev
# → Vite dev server on http://127.0.0.1:5173
```

Abrí `http://127.0.0.1:5173` en el navegador. Deberías ver el árbol CoL-style con `Taxonomic Tree` como título, toggles `Source` + `Extant only`, y breadcrumb. Expandí `Eukaryota → Animalia` para ver el tier group "Phyla (34)" funcionando.

### 3.1 Build de producción (opcional)

```bash
cd frontend
npm run build
# → dist/ listo para servir
```

El bundle compilado vive en `frontend/dist/`. El backend FastAPI lo sirve en producción desde la misma origen (no hay proxy).

## 4. Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `TAXON_DATABASE_URL` | `sqlite:///./data/taxon.db` | URL de SQLAlchemy. Acepta `sqlite:///:memory:` para tests. |
| `TAXON_DATASET` | `/Users/sebailla/Developer/research/worm/dataset-2011.txt` | Ruta al dataset WoRMS para el importador. La UI siempre muestra los 5 roots CoL; el dataset WoRMS provee los descendientes. |
| `TAXON_DATABASE` | `data/taxon.db` | DB path para el CLI `taxon.import_data`. |
| `AQUALIFE_ROOT` | `/` | Root del filesystem para `species_folders` (workspace per-species). Solo relevante si usás el workspace. |

Estas variables se pueden setear con `export VAR=value` en el shell, en `.env` (si usás `python-dotenv`), o en el deploy (systemd, docker, etc.).

## 5. Quality gates (CI debe pasar antes de merge)

```bash
# Backend
python -m pytest -v               # todos los tests
python -m mypy taxon/              # strict mode
python -m ruff check .            # lint
python -m ruff format --check .   # format check

# Frontend
cd frontend
npm test            # vitest, single run
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # production bundle
```

CI corre en cada PR contra `develop`. 4 jobs en paralelo:

- `backend (python 3.11)` — pytest + ruff + mypy
- `backend (python 3.12)` — pytest + ruff + mypy
- `frontend (node 20)` — vitest + eslint + tsc + build
- `lighthouse (a11y)` — accessibility audit

## 6. Workflow de desarrollo

### 6.1 Branching (per AGENTS.md §4)

```
main          ← producción, solo recibe PRs desde develop
└─ develop    ← integración, recibe PRs desde worktrees
   └─ feature/<name>  ← cada feature/fix en su worktree
```

`main` no se toca. Cada feature nace en un worktree:

```bash
# Crear worktree desde develop
git worktree add ../taxon-worktrees/<feature-name> -b feat/<name> origin/develop

# Trabajar dentro del worktree
cd ../taxon-worktrees/<feature-name>
# commits + push + PR contra develop
```

### 6.2 Strict TDD

El proyecto está en modo Strict TDD (per `openspec/config.yaml`). Cada work unit arranca con un test RED, después GREEN, después REFACTOR. Para cambios nuevos:

1. Escribir el test → correr → fallar (RED).
2. Implementar el mínimo para pasar (GREEN).
3. Refactor con tests verdes (REFACTOR).
4. Commit + push + PR.

### 6.3 Spec-Driven Development (SDD)

Para cambios sustanciales, el flujo SDD es:

```
proposal → specs → design → tasks → apply → verify → archive
```

Artefactos viven en `openspec/changes/<change-name>/`. Specs durables en `openspec/specs/<capability>/`. Mirror en español obligatorio para todos los artefactos per `AGENTS.md §1`.

### 6.4 Conventional commits

Formato: `type(scope): description` en inglés, imperativo presente.

- Tipos válidos: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`.
- Sin "Co-Authored-By" ni atribución de IA.
- Ejemplo: `feat(api): add next_tiers envelope`, `fix(tree): handle empty children`.

## 7. Troubleshooting

### El backend no arranca con `python -m taxon.main`

- **Error: `ModuleNotFoundError: No module named 'taxon'`** → no corriste `pip install -e ".[dev]"` desde el directorio del repo. Activá el venv y re-instalá.
- **Error: `RuntimeError: Working outside of application context`** → la base no existe. Corré `python -m taxon.import_data` primero o apuntá a `data/taxon.db` con `TAXON_DATABASE_URL`.

### El frontend no proxea al backend

- **Vite dev arranca pero `/api/*` da 404** → el backend en `:8000` no está corriendo. Levantá primero el backend.
- **`CORS policy: ... blocked`** → en dev no hay CORS porque Vite proxea. En producción, el backend y el frontend se sirven desde el mismo origen.

### La base no muestra datos

- **`data/taxon.db` está vacía o corrupta** → reimportá con `python -m taxon.import_data --source /path/to/dataset-2011.txt`.
- **Error: `no such table: taxa`** → corriste `python -m taxon.migrate apply` (crea las tablas del workspace + asegura índices).

### `mypy` falla con muchos errores

Activá el venv antes de cualquier comando:

```bash
source .venv/bin/activate
which python  # debe apuntar a .venv/bin/python
```

### Frontend: `npm test` falla con `Cannot find module`

Faltan dependencias. Corré `npm install` en `frontend/`.

### Permisos en `data/`

Si clonás en un path con permisos restrictivos, SQLite puede no poder escribir. Verificá:

```bash
ls -la data/
chmod -R u+rw data/
```

## 8. Estructura del repo

```
taxon/
├── taxon/                 # Backend (Python)
│   ├── parser.py          # Streaming indentation-stack parser
│   ├── schema.py          # SQLAlchemy models (Taxon, SpeciesPath, ...)
│   ├── import_data.py     # Batched streaming importer (CLI: python -m taxon.import_data)
│   ├── search_links.py    # 12 search-source URL templates
│   ├── main.py            # Uvicorn entrypoint (python -m taxon.main)
│   ├── migrate.py         # Idempotent CLI: python -m taxon.migrate apply
│   └── api/               # FastAPI surface
│       ├── __init__.py    # App factory + lifespan
│       ├── router.py      # /api/* endpoints
│       ├── schemas.py     # Pydantic response models
│       ├── _tree_tiers.py # Shared module: roll-up + per-tier CTE + cursor
│       ├── sqlite_resolver.py  # Path resolver + roll-up helpers
│       ├── hierarchy.py   # Cascade path resolver
│       ├── species.py     # Species list + lookup helpers
│       ├── errors.py      # HTTP-mapped exceptions
│       ├── workspace.py   # Workspace per-species (species-folder-explorer)
│       ├── db.py          # Request-scoped session
│       └── tree.py        # /api/tree/children subtree endpoint
├── frontend/              # Frontend (TypeScript + React + Vite + Tailwind)
│   ├── src/
│   │   ├── api.ts         # Typed API client
│   │   ├── App.tsx        # Root composition
│   │   ├── components/
│   │   │   ├── TaxonomicTree.tsx  # CoL-style tree (PR #69)
│   │   │   ├── Cascade.tsx        # Legacy 7-dropdown (rooted via breadcrumb)
│   │   │   ├── SpeciesList.tsx
│   │   │   ├── SpeciesLinks.tsx
│   │   │   ├── ExplorerPanel.tsx  # Iframe explorer (PR #73)
│   │   │   ├── Breadcrumb.tsx
│   │   │   └── Toggles.tsx
│   │   └── store/
│   │       ├── taxonomicTree.ts  # next_tiers cache + loadMore
│   │       ├── cascadePath.ts
│   │       └── workspace.ts       # Species workspace store
│   ├── tests/             # Vitest + Testing Library
│   ├── tailwind.config.js # Design tokens
│   └── vite.config.ts     # Dev server with /api proxy
├── data/                  # Pre-poblada en el repo
│   ├── taxon.db           # SQLite con WoRMS 2011 + jerarquía CoL (5 roots)
│   └── col.db             # Cache CoL adicional
├── docs/                  # Documentación en inglés
│   ├── design/
│   │   ├── stitch/tree-deep-subtree-design.md
│   │   └── ...
│   └── sources/
├── documents-es/          # Mirror en español
├── learn-es/              # Post-merge learning entries
├── openspec/              # Spec-Driven Development artifacts
│   ├── changes/           # Active changes (proposal, design, tasks)
│   ├── changes/archive/   # Closed changes (archive-report, verify-report)
│   └── specs/             # Durables specs (specs.delta.md)
├── pyproject.toml         # Python packaging
├── .github/workflows/ci.yml
└── README.md              # Resumen del proyecto
```

## 9. Checklist rápida

```bash
# 1. Clonar
git clone https://github.com/Sebailla/taxon.git && cd taxon

# 2. Backend
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m taxon.main &
BACKEND_PID=$!
sleep 2
curl http://127.0.0.1:8000/healthz

# 3. Frontend
cd frontend && npm install && npm run dev
# → http://127.0.0.1:5173

# 4. (Opcional) Migraciones
python -m taxon.migrate apply

# 5. (Opcional) Quality gates
python -m pytest && python -m mypy taxon/ && python -m ruff check .
cd frontend && npm test && npm run typecheck && npm run build
```

Si los 4 health checks pasan, el sistema está corriendo. Listo para desarrollar.
