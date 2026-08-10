# What

`taxon` PR 1 — foundational backend: streaming indentation-stack
parser, SQLAlchemy `Taxon` + `SpeciesPath` models with marker columns
and indexes, batched streaming importer with dependency-aware flushing,
and a 12-template search-link loader with verbatim URL parity.

# How

- Python 3.11+ with FastAPI / SQLAlchemy / SQLite on the backend,
  pytest + ruff + mypy for tooling.
- Strict RED→GREEN TDD per task, 13 unit and integration tests, all
  passing in ~6 s locally.
- Streaming parser holds only the currently-open ancestor chain
  (O(depth) memory, ~30 ranks in WoRMS).
- Importer batches 1,000 rows per transaction and flushes when a child
  references a parent still pending in the same batch.
- Species-path projection uses a stack of currently-open ancestors
  (O(depth), bounded) and OR-folds the four marker flags
  (`is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`)
  through every ancestor.
- Author-citation stripping heuristic splits the verbatim source label
  into a canonical `name` (used for case-insensitive lookup) and a
  `display_name` (verbatim, used for display), per
  `taxonomy-hierarchy/spec.md:33`.
- Judgment Day round 1 → 2 CRITICAL (citation in `name`, memory
  bound), round 2 → both `fixed`, terminal `JUDGMENT: APPROVED ✅`.

# Where

- `taxon/parser.py` — streaming indentation-stack parser with marker
  extraction and canonical/display split.
- `taxon/schema.py` — `Taxon` (self-referential `parent_id`) and
  `SpeciesPath` (denormalised breadcrumb) with marker mixin and
  indexes.
- `taxon/import_data.py` — `import_dataset` CLI entrypoint;
  `_populate_species_paths` bounded-memory projection.
- `taxon/search_links.py` — `load_templates` and `build_search_links`
  over `docs/sources/templates.md`.
- `taxon/tests/` — 4 test modules (parser, schema, import,
  search-links), 13 tests.
- `pyproject.toml` — package metadata, deps, mypy `strict = true`.
- `docs/sources/templates.md` — captured verbatim templates.
- `.github/workflows/ci.yml` — GitHub Actions workflow added in the
  CI commit (see below).

# Why

- The WoRMS spreadsheet the user maintains cannot be reasoned about
  past a few hundred rows. A database-backed dispatcher lets us
  scale to all 1.39 M taxa with bounded memory and stable response
  shapes.
- Separating canonical `name` from verbatim `display_name` is
  required by the spec: the cascade URL segments need
  case-insensitive canonical-name resolution, but the UI must show
  the original WoRMS label with author citations and status markers
  intact.
- Bounded memory in the species-path projection is required because
  the dataset is ~1.4 M rows; the naive `O(total_taxa)` implementation
  would consume several hundred MB and was caught by Judgment Day
  round 1.
- Dependency-aware batch flushing is required because SQLAlchemy
  generates `parent_id` only after the parent insert is flushed; the
  batch boundary has to be drawn just before a child references a
  parent still pending.

# How it works

1. `python -m taxon.import_data` reads the WoRMS dataset
   line-by-line through `parse_taxa`, builds `Taxon` rows in batches
   of 1,000, and inserts them inside a transaction. When a child's
   parent is still in the pending batch, the importer flushes the
   batch first so the parent's autoincrement id is available.
2. After the taxa table is fully populated, `_populate_species_paths`
   streams taxa in `id ASC` order, maintaining a stack of currently
   open ancestors. When the current taxon's parent is on top of the
   stack, the inherited path and markers are copied; otherwise the
   stack is popped until it is. For every species row, the inherited
   breadcrumb (Kingdom..Species) and OR-folded markers are written
   to `species_paths` in batches.
3. At request time (PR 2 territory), the API layer can resolve
   `SpeciesPath` rows by `species` or by `(genus, epithet)` without
   recursive CTEs.
4. `search_links.build_search_links(species, templates)` substitutes
   each template's `{q}` placeholder with
   `urllib.parse.quote_plus(species, safe='')`, producing exactly 12
   `(source, label, url)` entries in the documented order, with the
   Photos URL's literal `&` separators preserved verbatim.

# Workflows

- Git: `develop` is the integration base; PRs target `develop`, never
  `main`. `main` is production and only moves via a manual
  `develop` → `main` PR.
- CI: `.github/workflows/ci.yml` runs on every push to `develop` and
  every PR against `develop`. Backend job matrix: Python 3.11 +
  3.12. Steps: `ruff check`, `ruff format --check`, `mypy`, `pytest`.
  First successful run: 50 s.
- Branch protection (recommended, not yet enabled): require both
  `backend (python 3.11)` and `backend (python 3.12)` checks to
  pass before merging into `develop`.
- TDD: strict RED→GREEN per task. Each task produced a `test(...)`
  commit followed by a `feat(...)` commit. The 4 fix commits from
  Judgment Day round 1 sit on top.
- Worktree usage: feature work happens in
  `../<repo>-worktrees/<feature-name>`; the main checkout stays on
  `develop` clean.

# Discoveries

- **`Taxon.parent_id` requires dependency-aware batch flushing.**
  SQLAlchemy populates autoincrement ids only on flush, so a child
  referencing a parent in the same pending batch needs the batch to
  be flushed first. The fix is in `import_data.py` lines around the
  `if parent_source_id in batch_source_ids` branch.
- **Author citations belong in `display_name`, not `name`.** The
  dataset formats names like `"Apororhynchus hemignathi (Shipley,
  1896) Shipley, 1899"`; the trailing parenthetical + author + year
  is a citation, not part of the canonical taxon. The citation
  stripper preserves subgenus parentheses (no year inside) and
  handles particles (`d'`, `de`, `van`, `von`, etc.) and accents
  (`Tantaleán`, `Barčák`).
- **The naive `_populate_species_paths` used O(total_taxa) memory.**
  Switching to a stack of currently-open ancestors brought it to
  O(depth), independent of the dataset size.
- **Setuptools flat-layout detection fails with two top-level
  packages.** `pyproject.toml` must pin `[tool.setuptools] packages
  = ["taxon"]` explicitly so `pip install -e ".[dev]"` does not
  refuse to build when both `taxon/` and `openspec/` are present.
