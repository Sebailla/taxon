# What

`taxon` PR 2A — primera rebanada del API layer: app factory de FastAPI con
SQLAlchemy engine manejado por lifespan, modelos Pydantic v2 para respuestas,
un placeholder vacío de `APIRouter` para que las próximas rebanadas no toquen
factory/lifespan, y un entrypoint de uvicorn. Cierra con 25 tests pasando
(13 de PR 1 + 12 nuevos) y `ruff`/`mypy` strict limpios.

# How

- FastAPI 0.141 + Pydantic 2.13 + Starlette 1.6 + SQLAlchemy 2.0.
- `taxon/api/__init__.py` exporta `create_app(database_url=None)` que arma
  el engine SQLAlchemy dentro de un `lifespan` async context manager,
  registrando handlers para 404 (`NotFoundError`), 409 (`AmbiguousError`) y
  500 default. Devuelve un `FastAPI` con `/healthz` y `/openapi.json`
  siempre disponibles.
- `taxon/api/schemas.py` define las response models Pydantic v2 con
  `model_config = ConfigDict(from_attributes=True)` para mapear desde las
  filas de SQLAlchemy sin escribir adapters: `TaxonResponse`,
  `SpeciesPathResponse`, `HealthResponse`, `CandidateRef`, `ErrorResponse`.
- `taxon/api/router.py` registra un `APIRouter(prefix="/api")` con una ruta
  `/api/_meta` que devuelve `{"phase": "2A"}`. Marcada explícitamente como
  smoke y NO remover por Sub-PR 2B/2C; los siguientes slices agregan
  rutas a este router.
- `taxon/main.py` corre `uvicorn.run("taxon.api:create_app", factory=True,
  host="127.0.0.1", port=8000, reload=True)` cuando se invoca como script.
- `taxon/tests/test_api_app.py` agrega 12 tests RED-first que cubren
  shape del factory, schemas, marker flags, error envelope con/sin
  candidates, y OpenAPI emission.
- Test runner usa `fastapi.testclient.TestClient` (Starlette 1.6 lo
  provee), que requiere `httpx` instalado.

# Where

- `taxon/api/__init__.py` — `create_app`, lifespan, exception classes,
  handlers, `/healthz`, dev CORS.
- `taxon/api/schemas.py` — `TaxonResponse`, `SpeciesPathResponse`,
  `HealthResponse`, `CandidateRef`, `ErrorResponse`.
- `taxon/api/router.py` — `APIRouter(prefix="/api")` con `/api/_meta`
  smoke route.
- `taxon/main.py` — entrypoint `python -m taxon.main`.
- `taxon/tests/test_api_app.py` — 12 tests RED-first.
- `pyproject.toml` — agrega `httpx` a los extras `dev` (descubierto por CI
  failure en primer intento, ver Discoveries).

# Why

- PR 1 dejó los datos vivos en SQLite pero sin superficie HTTP. Sin el
  factory y los schemas no se puede razonar sobre contrato de respuesta.
- Pydantic v2 strict + mypy strict requiere evitar el keyword clash con
  `class`/`order` (reservados de Python). Se usan nombres explícitos
  `class_name`/`order_name` que mapean directo desde las columnas
  SQLAlchemy sin `Field(alias=...)` (ver Discoveries).
- El router placeholder con `/api/_meta` garantiza que el archivo no
  quede vacío bajo ruff y deja un punto de integración estable para 2B/2C
  sin que tengan que tocar `taxon/api/__init__.py`.

# How it works

1. `from taxon.api import create_app; app = create_app()` arma el engine
   SQLAlchemy en `sqlite:///./data/taxon.db` (crea `data/` si no existe).
2. `with TestClient(app) as client:` abre el lifespan, instancia el engine
   y lo cierra limpio al salir — los tests no filtran conexiones.
3. `client.get("/healthz")` devuelve 200 con `{"status":"ok"}`.
4. `client.get("/openapi.json")` contiene `/healthz`, `/openapi.json`,
   `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/api/_meta`.
5. Para instanciar schemas con datos de SQLAlchemy: pasar la fila como
   kwargs (`TaxonResponse.model_validate(row)` con
   `from_attributes=True`).
6. `python taxon/main.py` arranca uvicorn con reload, exponiendo la app en
   `127.0.0.1:8000` para uso local.

# Workflows

- CI: workflow `CI` corre en push a `develop` y PR contra `develop` con
  matrix Python 3.11 + 3.12. Steps: `ruff check`, `ruff format --check`,
  `mypy taxon/`, `pytest taxon/tests/ -v`. Duración ~50 s.
- Branching: la cadena planeada originalmente era feature-branch-chain,
  pero `AGENTS.md §4.2.4` exige PR contra `develop`. Por eso cada sub-PR
  (2A, 2B, 2C) targetea `develop` y se mergea en serie (stacked-to-main
  model). El branch tracker original (`feature/species-search-dispatcher`)
  se renombró a `feat/species-search-dispatcher-api-foundation` para
  reflejar el scope recortado.
- Worktree: el trabajo de 2A ocurrió en
  `/Users/sebailla/Developer/taxon-worktrees/species-search-dispatcher/`
  con venv propio. El `.venv` del checkout principal no se reutiliza
  para evitar pisar dependencias entre PRs paralelos.

# Discoveries

- **Starlette 1.6 / FastAPI 0.141 cambió el contrato de TestClient.**
  El viejo `from fastapi.testclient import TestClient` ya no funciona
  sin `httpx` instalado. CI rompe con `RuntimeError: The
  starlette.testclient module requires the httpx2 package`. Fix:
  agregar `httpx` a los extras `dev` de `pyproject.toml`. Vale como
  dependencia de test, NO de runtime — el API no depende de httpx.
- **`Field(alias="class")` choca con mypy strict.** Pydantic v2 acepta
  el alias en runtime pero mypy strict solo ve el alias como kwarg
  válido y rechaza `SpeciesPathResponse(class_=...)`. La salida
  limpia es usar nombres Python que NO colisionen con keywords
  reservados (`class_name`, `order_name`) y mapear directo desde la
  columna SQLAlchemy del mismo nombre. Si se necesita alias real,
  la salida es `model_validator(mode="before")` — más caro.
- **AGENTS.md §4 regla local gana sobre la cadena planeada.** La
  sesión anterior eligió feature-branch-chain (memoria), pero §4.2.4
  dice PR contra `develop`. La regla local es ley. Renombrar el
  branch fue trivial; la consecuencia operacional es que los sub-PRs
  2B/2C ahora se apilan en serie contra `develop` (stacked-to-main).
- **El skill `branch-pr` exige infra que el repo no tiene.** El skill
  asume labels `status:approved`, workflows `Check Issue Reference`,
  etc. El repo solo tiene `ci.yml`. Aplicamos el espíritu del skill
  (issue-first + label + body estructurado con `Closes #N`) sin
  esperar bloqueos automáticos que no existen.
