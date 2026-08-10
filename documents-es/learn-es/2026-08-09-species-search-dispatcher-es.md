# Qué

`taxon` PR 1 — backend fundacional: parser de pila de indentación
streaming, modelos SQLAlchemy `Taxon` y `SpeciesPath` con columnas de
marcadores e índices, importador streaming con flushes dependientes
del grafo, y un cargador de 12 templates de search-link con paridad
verbatim de URLs.

# Cómo

- Python 3.11+ con FastAPI / SQLAlchemy / SQLite en backend,
  pytest + ruff + mypy para tooling.
- TDD estricto RED→GREEN por tarea, 13 tests unitarios y de
  integración, todos pasando en ~6 s en local.
- El parser streaming mantiene sólo la cadena de ancestros
  actualmente abiertos (memoria O(depth), ~30 ranks en WoRMS).
- El importador procesa batches de 1.000 filas por transacción y
  flushea cuando un hijo referencia a un padre todavía pendiente en
  el mismo batch.
- La proyección de `species_paths` usa una pila de ancestros
  actualmente abiertos (O(depth), acotada) y aplica OR sobre los
  cuatro flags de marcador (`is_synonym`, `is_extinct`,
  `is_uncertain`, `is_unassigned`) a través de cada ancestro.
- La heurística de stripping de citas de autor divide la etiqueta
  verbatim de origen en un `name` canónico (usado para lookup
  case-insensitive) y un `display_name` (verbatim, usado para
  mostrar), según `taxonomy-hierarchy/spec.md:33`.
- Judgment Day ronda 1 → 2 CRITICAL (cita en `name`, cota de
  memoria), ronda 2 → ambos `fixed`, terminal
  `JUDGMENT: APPROVED ✅`.

# Dónde

- `taxon/parser.py` — parser streaming de pila de indentación con
  extracción de marcadores y split canónico/verbatim.
- `taxon/schema.py` — `Taxon` (auto-referencia en `parent_id`) y
  `SpeciesPath` (breadcrumb desnormalizado) con mixin de marcadores
  e índices.
- `taxon/import_data.py` — entrypoint CLI `import_dataset`;
  proyección de memoria acotada `_populate_species_paths`.
- `taxon/search_links.py` — `load_templates` y `build_search_links`
  sobre `docs/sources/templates.md`.
- `taxon/tests/` — 4 módulos de test (parser, schema, import,
  search-links), 13 tests.
- `pyproject.toml` — metadata del paquete, dependencias, mypy
  `strict = true`.
- `docs/sources/templates.md` — templates verbatim capturados.
- `.github/workflows/ci.yml` — workflow de GitHub Actions agregado
  en el commit de CI (ver abajo).

# Por qué

- La planilla de WoRMS que mantiene el usuario no se puede razonar
  más allá de unos pocos cientos de filas. Un dispatcher respaldado
  por base de datos nos permite escalar a los 1,39 M de taxones con
  memoria acotada y formas de respuesta estables.
- Separar el `name` canónico del `display_name` verbatim es
  requerido por el spec: los segmentos de URL del cascade necesitan
  resolución case-insensitive por nombre canónico, pero la UI debe
  mostrar la etiqueta original de WoRMS con citas de autor y
  marcadores de estado intactos.
- La cota de memoria en la proyección de species-path es necesaria
  porque el dataset tiene ~1,4 M de filas; la implementación naive
  O(total_taxa) consumiría varios cientos de MB y fue cazada en la
  ronda 1 de Judgment Day.
- El flushing del batch dependiente del grafo es necesario porque
  SQLAlchemy genera el `parent_id` sólo después del flush del
  insert del padre; el límite del batch debe trazarse justo antes
  de que un hijo referencie a un padre todavía pendiente.

# Cómo funciona

1. `python -m taxon.import_data` lee el dataset de WoRMS línea por
   línea a través de `parse_taxa`, construye filas `Taxon` en
   batches de 1.000 y las inserta dentro de una transacción.
   Cuando el padre de un hijo todavía está en el batch pendiente, el
   importador flushea el batch primero para que el id
   autoincremental del padre esté disponible.
2. Una vez que la tabla de taxones está completamente poblada,
   `_populate_species_paths` streamea los taxones en orden
   `id ASC`, manteniendo una pila de ancestros actualmente
   abiertos. Cuando el padre del taxón actual está en el tope de la
   pila, se copian el path y los marcadores heredados; si no, la
   pila se popea hasta que lo esté. Para cada fila de especie, el
   breadcrumb heredado (Kingdom..Species) y los marcadores
   aplicados con OR se escriben a `species_paths` en batches.
3. En tiempo de request (territorio del PR 2), la capa de API puede
   resolver filas de `SpeciesPath` por `species` o por
   `(genus, epithet)` sin CTEs recursivas.
4. `search_links.build_search_links(species, templates)` sustituye
   cada placeholder `{q}` de los templates con
   `urllib.parse.quote_plus(species, safe='')`, produciendo
   exactamente 12 entradas `(source, label, url)` en el orden
   documentado, con los separadores `&` literales de la URL de
   Photos preservados verbatim.

# Workflows

- Git: `develop` es la base de integración; los PRs targetean
  `develop`, nunca `main`. `main` es producción y sólo se mueve
  mediante un PR manual `develop` → `main`.
- CI: `.github/workflows/ci.yml` corre en cada push a `develop` y
  en cada PR contra `develop`. Matrix del job de backend: Python
  3.11 + 3.12. Pasos: `ruff check`, `ruff format --check`, `mypy`,
  `pytest`. Primera corrida exitosa: 50 s.
- Branch protection (recomendado, todavía no activado): requerir
  que pasen los checks `backend (python 3.11)` y
  `backend (python 3.12)` antes de mergear a `develop`.
- TDD: RED→GREEN estricto por tarea. Cada tarea produjo un commit
  `test(...)` seguido de un commit `feat(...)`. Los 4 commits de
  fix de la ronda 1 de Judgment Day se apoyan arriba.
- Uso de worktree: el trabajo de feature sucede en
  `../<repo>-worktrees/<feature-name>`; el checkout principal se
  queda limpio en `develop`.

# Descubrimientos

- **`Taxon.parent_id` requiere flushing de batch dependiente del
  grafo.** SQLAlchemy puebla los ids autoincrementales sólo en el
  flush, así que un hijo que referencia a un padre en el mismo
  batch pendiente necesita que el batch se flushee primero. El fix
  está en `import_data.py` cerca del branch
  `if parent_source_id in batch_source_ids`.
- **Las citas de autor van en `display_name`, no en `name`.** El
  dataset formatea nombres como
  `"Apororhynchus hemignathi (Shipley, 1896) Shipley, 1899"`; el
  paréntesis + autor + año del final es una cita, no parte del
  taxón canónico. El stripper de citas preserva los paréntesis de
  subgénero (sin año adentro) y maneja partículas (`d'`, `de`,
  `van`, `von`, etc.) y acentos (`Tantaleán`, `Barčák`).
- **La implementación naive de `_populate_species_paths` usaba
  memoria O(total_taxa).** Cambiar a una pila de ancestros
  actualmente abiertos la llevó a O(depth), independiente del
  tamaño del dataset.
- **La detección flat-layout de setuptools falla con dos paquetes
  top-level.** `pyproject.toml` debe fijar explícitamente
  `[tool.setuptools] packages = ["taxon"]` para que
  `pip install -e ".[dev]"` no rehúse el build cuando coexisten
  `taxon/` y `openspec/`.
