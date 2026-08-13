# CoL DwC-A import path (PR #26)

## What

Added a new import path that ingests the Catalogue of Life
DwC-A archive into the same SQLite schema that the existing
WoRMS path populates. After this PR lands, operators can run:

```
python -m taxon.col_import /path/to/NameUsage.tsv --database data/taxon.db
```

to swap the 1.39M-row WoRMS dataset for CoL's 7.87M rows
covering all kingdoms (Animalia, Plantae, Fungi, Chromista,
plus several prokaryote and virus kingdoms) with the cascade
UI and all 14 existing endpoints unchanged.

The WoRMS path in `taxon/import_data.py` is untouched. The
choice of which archive to seed remains a per-deployment
decision (the WoRMS dataset is faster to seed; CoL is
5.6× larger and richer).

## How

### New parser: `taxon/col_parser.py`

Streams the 2.9 GB NameUsage TSV. Same `(parent_source_id,
ParsedTaxon)` shape as the WoRMS parser so the two paths share
the `Taxon` / `SpeciesPath` schema. Column mapping (full list in
the module docstring):

- `col:ID`               → source_id
- `col:parentID`         → parent_source_id
- `col:scientificName`   + `col:authorship` → display_name
- `col:rank`             → rank
- rank-specific canonical name from `col:uninomial` /
  `col:genericName` / `col:specificEpithet` /
  `col:infraspecificEpithet`, falling back to
  `col:scientificName` when a row omits the decomposed parts
- `col:status` (synonym / ambiguous synonym / misapplied) →
  is_synonym; (`provisionally accepted`) → is_uncertain;
  (`col:extinct` == "true") → is_extinct;
  (`col:rank` == "unranked") → is_unassigned

Validation:
- header must contain all required column names (raises
  `ValueError` with the missing list otherwise);
- data rows must have the same cell count as the header
  (the published CoL archive ships a strict count per row).

### New ingester: `taxon/col_import.py`

Three-pass strategy, all in-memory maps, no re-streaming:

1. **Insert pass** — stream the TSV, batch-insert into `Taxon`
   with `parent_id = NULL`. Foreign keys disabled at the engine
   level during the import (every insert has an orphan
   `parent_id` until pass 2). Two maps built on the side:
   `source_to_database_id` (CoL source_id → autoincrement
   Taxon.id) and `parent_source_by_child` (child source_id →
   parent source_id).

2. **Parent-wiring pass** — one `UPDATE taxa SET parent_id = ...`
   per distinct parent, batched across every child that points
   to it. Roots whose parent is outside the imported subset
   (the implicit Biota superdomain) are left with `parent_id =
   NULL`. Those are the roots of the imported forest, not bugs.

3. **Species-path pass** — for every row whose rank is species
   (or any infraspecific rank), insert a `SpeciesPath` row
   using the rank-resolved columns `col:kingdom` (65),
   `col:phylum` (64), `col:class` (62), `col:order` (60),
   `col:family` (57), `col:genus` (53), plus the binomen from
   `col:scientificName` + `col:authorship`. CoL populates those
   columns per row in its own dump, so the breadcrumb is in
   the data — no recursive walk needed.

Memory bound: ~100 MB per in-memory map at 7.87M rows. Both
fit comfortably in modern RAM. If the dataset grows past ~50M
rows, the second pass should switch to writing the parent
edges to disk and reading them back.

### Tests

10 RED-first unit tests in `taxon/tests/test_col_parser.py`
covering the parser contract end-to-end. 4 RED-first
integration tests in `taxon/tests/test_col_import.py` covering
the SQLite ingester:

- `test_col_import_persists_all_fixture_rows` — all 63 fixture
  rows land in `Taxon`.
- `test_col_import_wires_parent_ids_via_two_pass_strategy` —
  `NNWV` (species) resolves to `84LYY` (its genus) even when
  `NNWV` is parsed before `84LYY`.
- `test_col_import_projects_species_paths_from_resolved_columns`
  — `Buffonellaria cornuta` ends up in `SpeciesPath` with the
  full breadcrumb (kingdom Animalia, phylum Bryozoa, etc.)
  and `is_extinct = True`.
- `test_col_import_marks_synonym_status` — `63J5L` (genus
  `Paracoccidium`) has `is_synonym = True` because its
  `col:status = "synonym"`.

The fixture `taxon/tests/fixtures/col_subset.tsv` is a
63-row real slice of the live CoL archive with every parent_id
that appears in a child row also present as its own row, so the
importer can resolve the chain without external lookups.

## Where

- `taxon/col_parser.py` — new, 225 lines.
- `taxon/col_import.py` — new, 343 lines.
- `taxon/tests/test_col_parser.py` — new, 135 lines.
- `taxon/tests/test_col_import.py` — new, 100 lines.
- `taxon/tests/fixtures/col_subset.tsv` — new, 64 lines.

No existing files modified. The WoRMS import path stays
byte-for-byte unchanged.

## Why

The CoL DwC-A archive integrates WoRMS + ITIS + NCBI + GBIF +
~21,000 specialised taxonomic catalogues into a single DwC-A
release. Moving from WoRMS alone to CoL:

- grows the taxon count 5.6× (1.39M → 7.87M);
- expands coverage from marine-only (WoRMS) to all kingdoms;
- surfaces status (accepted / synonym / provisionally accepted
  / ambiguous synonym / misapplied) instead of an inferred `=`
  marker in the label prefix;
- gives us extinct flags as a real boolean column (`col:extinct`)
  instead of a `†` prefix that the WoRMS parser had to parse
  out of the label;
- pre-resolves each row's kingdom → genus in its own columns,
  so the species-path projection no longer needs a depth-first
  walk.

The user's explicit request was "re-seed completo a CoL,
pasar solo las 6 columnas que tenemos: Kingdom, Phylum, Class,
Order, Family, Genus y especie (todas)". The CoL columns 65/64/62/60/57/53 give us exactly that
breadcrumb per row, which is why the species-path pass can
read them directly without walking the tree.

## How it works

When the operator runs `python -m taxon.col_import`:

1. The CLI defaults to the CoL archive at
   `/Users/sebailla/Developer/research/e8ce17c8-47c4-4b10-8316-7b699472c3b1/NameUsage.tsv`
   (overridable via `TAXON_COL_DATASET`).
2. `import_col_dataset(source, database)` drops and recreates
   the `taxa` and `species_paths` tables.
3. Pass 1 streams the TSV. The `parse_col_taxa` generator yields
   rows; `parse_col_taxa` validates each row's cell count, the
   two maps accumulate, and every 1,000 rows the batch flushes
   into `Taxon` (with `parent_id = NULL`).
4. Pass 2 issues one `UPDATE` per distinct parent source_id
   across every child that points to it. One round trip per
   parent; one transaction overall.
5. Pass 3 re-streams the TSV (this time without parsing it)
   and writes 18 species-path rows per 1,000 batch.

After the CLI exits, `data/taxon.db` has the WoRMS schema
populated with CoL data, and the existing cascade UI /
endpoints work unchanged.

## Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). All green. No new workflows.
- **Reviews** — 3 `work-unit-commits`:
  1. `93d8046 test(data): add CoL parser unit tests with a real-row fixture`
  2. `14ef442 feat(data): add CoL DwC-A NameUsage TSV parser`
  3. `cd92551 feat(data): add CoL DwC-A import path (SQLite ingester)`
  Reviewer can read the parser in isolation, the tests pin the
  parser contract, and the ingester commit is the smallest
  possible diff (no parser changes).
- **Local seed** — `python -m taxon.col_import` on the 2.9 GB
  archive takes 1-3 hours and produces a SQLite of roughly
  500 MB - 1 GB. Same `data/taxon.db` filename the WoRMS path
  uses, so swapping is a one-line path change.
- **Production deployment** — the API server points at
  `data/taxon.db` regardless of which path seeded it. The
  cascade UI's only interaction is via `Taxon` /
  `SpeciesPath`, so both sources are interchangeable.

## Lessons learned

- **CoL rows are NOT in depth-first order.** Verified against
  the live archive — the first 50 rows mix species, genus,
  order, suborder. The WoRMS parser relies on indentation to
  maintain an ancestor stack; that pattern cannot work for
  CoL. The three-pass strategy + in-memory parent map is the
  minimum that handles the unordered rows correctly.

- **CoL pre-resolves the breadcrumb per row.** The rank-resolved
  columns (50/53/57/60/62/64/65) carry kingdom → genus for
  every row, including synonym rows. The species-path pass
  reads them directly; no recursive walk is needed. The
  WoRMS path needed a depth-first walk to build the same
  projection — that complexity is gone.

- **Two parallel import modules beat one polymorphic one.**
  `taxon/import_data.py` (WoRMS, depth-first, single-pass)
  and `taxon/col_import.py` (CoL, unordered, three-pass)
  share the `Taxon` and `SpeciesPath` models but differ in
  every step. Forcing them through one function with an
  `if format == ...` branch per step would have hurt
  readability more than the duplication of the entry point.

- **In-memory maps beat re-streaming the file.** The CoL
  archive is 2.9 GB; re-streaming twice would triple I/O.
  The two maps (source_to_database_id + parent_source_by_child)
  cost ~200 MB at 7.87M rows. Cheap enough.

- **`dict(parsed)` cast at batch time.** `ParsedTaxon` is a
  TypedDict; mypy strict rejects appending a TypedDict into
  `list[dict[str, Any]]`. The explicit `dict(parsed)` cast is
  the cleanest workaround, and the SQL insert path treats the
  row as a plain dict anyway.

- **Real-data fixtures are the only honest fixtures.** The
  63-row fixture is a real slice of the CoL archive with
  every parent_id that appears in a child row also present as
  its own row, so the importer can resolve the chain without
  external lookups. Synthesised fixtures would have hidden
  the column-offset bugs we caught early (`_COL_FAMILY = 56`
  not 57, etc.).

## Follow-up opportunities (out of scope for this PR)

- Import `VernacularName.tsv` (154 MB, 1.99M rows) as a new
  `VernacularName` table joined to `Taxon` by `source_id`.
  Would unlock a "search by common name" feature.
- Import `Distribution.tsv` (140 MB) for a future
  distribution map UI.
- Add a kingdom selector to the cascade UI; today the UI
  walks Kingdom → Genus assuming a single root kingdom, which
  works for WoRMS but not for CoL (Animalia, Plantae, Fungi,
  etc. all start at the same indent level).
- Replace the WoRMS path as the default once the new dataset
  has been validated in production for a few weeks.
