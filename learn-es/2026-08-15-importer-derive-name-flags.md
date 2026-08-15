# PR #63 — importer derives is_synonym and is_extinct from name markers

## What

`taxon.indented_import` now derives `is_synonym` and `is_extinct`
flags from the leading character of the `name` column while building
the streaming batch row. A `=` prefix sets `is_synonym = True`, a
`†` (U+2020) prefix sets `is_extinct = True`, and any other leading
character leaves both flags `False`.

Two contract tests pin the derivation and guard against future
regressions where the marker rule could fire on a `=` or `†` that
appears inside an author string.

## How

The GBIF Backbone and the Catalogue of Life indented-tree dumps
encode synonym and extinction signals as inline characters on the
name column itself rather than as metadata keys. The marker
signals arrive in the same line that the parser is already
reading, so the natural place to derive the flags is the same
batch-row construction that already carries `source_id`,
`parent_id`, `name`, `rank`, `display_name`, and `display_level`.

The added lines sit inside `import_indented_dataset`, just before
the `batch.append({...})` call. Two boolean locals capture the
in-band signal:

```
is_synonym = name.startswith("=")
is_extinct = name.startswith("\u2020")
```

and the two new keys join the rest of the row. No new file, no
schema migration, no second pass: the streaming shape is identical
to before and the parent-id rewrite pass is untouched.

The two new tests in `taxon/tests/test_indented_import.py` use a
GBIF-shape fixture with three rows under a single genus: a
synonym (`=Felis catus Linnaeus, 1758`), a plain accepted name
(`Felis silvestris Schreber, 1777`), and an extinct taxon
(`†Actinomycites D. Ellis, 1916`). A second test feeds three
ordinary names that already contain `=` or `†` inside the author
or authorship year string and asserts the flags stay `False`.

The driver detail that bit the first test run: `sqlite3` returns
the `BOOLEAN` columns as `0` / `1` (the SQLAlchemy Boolean type
is rendered as `INTEGER` at the storage layer), so the assertions
cast through `bool(...)` to be driver-agnostic.

## Where

- `taxon/indented_import.py` — 9 lines added at the in-stream
  batch-row construction site.
- `taxon/tests/test_indented_import.py` — 2 new tests:
  `test_import_marks_synonym_and_extinct_from_name` and
  `test_import_does_not_flag_inner_equals_or_dagger_as_marker`.
- Worktree under `../taxon-worktrees/derive-name-flags` for the
  duration of the PR.
- Branch `chore/importer-derive-name-flags` from `develop`
  (`1a80e2b`); merged back as `dcd05ae`.

No existing files outside `taxon/` were touched. No config, no
frontend, no migration, no schema change.

## Why

The shape of the production database at `taxon.db` (2.4 GB) carries
`is_synonym = 1` on 3,231,318 rows (41.05%) and `is_extinct = 1` on
261,738 rows (3.33%). The reader counterpart, the SQLite cascade
resolver in `taxon/api/sqlite_resolver.py`, already filters by
both flags and the cascade UI already depends on that filter.
Until this PR, the importer was the only piece that knew about
the `is_synonym` / `is_extinct` columns without writing to them
— so any re-import of the same dataset would have produced a
silent regression in the cascade UI: the synonym filter would
have stopped hiding anything.

A separate worktree (from session #3892) had previously imported
Catalogue of Life through a CLB-flavoured helper that knew the
metadata block format. That helper lived in the tree only as a
side channel; the canonical importer — the one we ship to
operators — was the one that silently dropped the flags. We
chose to fix the canonical importer directly so the next operator
re-import does not have to know about the side channel.

## How it works

When an operator runs

```
python -m taxon.indented_import <source> --database <db>
```

on a GBIF or COL TextTree, the streaming parser reads each row,
extracts the `{ID=...}` metadata, looks up the depth, and pushes a
row onto the in-memory batch. The new lines run between the
metadata extraction and the `batch.append({...})`:

1. `is_synonym = name.startswith("=")` fires for every synonym
   line — the same lines that already showed as rejected in
   downstream search engines because the cascade UI treats them
   as invisible.
2. `is_extinct = name.startswith("\u2020")` fires for every
   fossil / extinct lineage.

Both flags persist in the schema columns the cascade UI already
queries; no API or frontend change is needed.

The end-to-end reproducibility check that closed the PR:

- A 488 MB COL26.7 XR TextTree (7,871,065 rows) is pre-processed
  with a one-line `{ID=<line_number>}` injection per row, then
  imported into `data/col.db`. The SHA256 of the source_id set
  differs from the production DB (`88f98ac2...` vs
  `4818c3950e...`) because the two DBs use different source_id
  encodings (CLB canonical IDs vs file line numbers), but the two
  population counts match to the row:

  - `is_synonym`: 3,231,318 on both.
  - `is_extinct`: 261,738 on both.

That match is the proof that the derivation in the canonical
importer reproduces the same database the production DB was
seeded with, without depending on a side-channel helper.

## Workflows

- **CI** — 4 jobs (backend Python 3.11, backend Python 3.12,
  frontend node 20, lighthouse a11y). All green in under 60 s on
  GH-hosted runners. No new workflows.
- **Reviews** — 2 work-unit commits:
  1. `feat(importer): derive is_synonym and is_extinct from name markers`
  2. `test(importer): cover is_synonym and is_extinct derivation`
  Reviewer reads the implementation first (one self-contained
  block at the batch-row site), then validates the contract
  with the two new tests.
- **Local seed** — the importer now reproduces the production
  `data/taxon.db` flags from a GBIF Backbone or COL TextTree
  without any post-import SQL patch. The previous side-channel
  helper is dead code as of this PR; the canonical importer is
  the single seed path.
- **Pre-procesado para COL TextTree** — el archivo
  `dataset-315834.txtree` que publica COL no trae metadata block,
  así que sigue siendo necesario inyectar `{ID=<line_number>}`
  por línea antes de invocar al importer. Ese pre-procesado es
  un `sed` / script Python externo de ~5 líneas; no forma parte
  del importer.
- **Production deployment** — the API server points at
  `data/taxon.db` regardless of how it was seeded. No config
  change required after merging this PR.

## Lessons learned

- **In-band signals belong to the importer, not to the
  reader.** The cascade UI had been compensating for an importer
  bug since PR #57. Fixing the importer is the smaller surface
  area and avoids pinning the contract on a side-channel helper.

- **Boolean columns at the SQLite layer return integers, not
  bool.** A test written against `sqlite3` raw will see `0` /
  `1`, not `True` / `False`. Going through `bool(row[2])` keeps
  the assertion readable and makes the test future-proof if the
  storage type ever changes.

- **Marker detection is a one-character prefix, not a substring
  test.** Author strings like `(Approved Lists 1980)` and `(=
  migration tests)` contain the marker shape, but live mid-name.
  A `startswith` check is the cheapest correct rule; a regex
  would open the door to over-matching.

- **Pre-procesado del COL TextTree es estable y reproducible.**
  Inyectar `{ID=<line_number>}` da un SHA256 fijo del archivo
  pre-procesado y un contenido binariamente idéntico cada vez.
  Eso convierte al import COL en una pipeline con hash
  reproducibilidad, útil para auditorías y para reproducibilidad
  académica.

## Follow-up opportunities (out of scope for this PR)

- Replace the `DEFAULT_SOURCE` in `taxon/indented_import.py` so
  the CLI defaults to the pre-processed COL TextTree instead of
  the GBIF Backbone file. Today, operators must pass the source
  path explicitly; making COL the default requires a separate
  decision on whether the production deployment moves to
  `data/col.db` or stays on `data/taxon.db`.
- Add a CLB / COL source_id resolver so the importer emits the
  CLB canonical IDs (`CRLT8`, `CS5HF`, ...) instead of file
  line numbers. The two databases already match in coverage and
  flag counts; matching in source_id encoding closes the last
  reproducible gap.
- Extend the marker contract to include `?` (provisionally
  accepted) so the cascade UI can distinguish a first-class
  accepted taxon from one that is awaiting expert review.
