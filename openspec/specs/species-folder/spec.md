# Spec: species-folder

## Purpose

The `species-folder` capability creates and persists a folder under an operator-controlled root (`AQUALIFE_ROOT`) that mirrors the resolved breadcrumb path of a `(genus, epithet)` species. The folder is created on demand, persisted in `species_folders`, and survives `taxa` re-imports via `(genus, epithet)` re-bind columns. Closes sub-feature B of issue #68.

## Requirements

### Requirement: Create Folder Resolves Breadcrumb and Persists Nested Path

The system MUST resolve a `(genus, epithet)` pair via `taxon.api.hierarchy.resolve_path_by_display_level`, join canonical `name` segments with `os.sep`, append to the resolved `AQUALIFE_ROOT`, create the nested directory with `Path.mkdir(parents=True, exist_ok=True)`, and upsert a `species_folders` row keyed by the `(genus, epithet)` pair (PRIMARY KEY `(genus, epithet)`, NO foreign key to `taxa.id`). The endpoint MUST return HTTP 201 with `{"path": "<absolute path>"}`.

#### Scenario: First create succeeds and returns absolute path

- GIVEN `Panthera tigris` exists in `taxa` chained to `Animalia`
- WHEN the client posts `POST /api/species-folder/Panthera/tigris`
- THEN the response is HTTP 201 with `{"path": "<AQUALIFE_ROOT>/Animalia/Chordata/.../Panthera/Panthera tigris"}`
- AND the folder exists on disk after the response
- AND a `species_folders` row exists with `genus="Panthera"`, `epithet="tigris"`, `path` matching the response

#### Scenario: Repeat create returns 409

- GIVEN a `species_folders` row exists for `Panthera tigris`
- WHEN the client posts `POST /api/species-folder/Panthera/tigris` again
- THEN the response is HTTP 409 with `{detail: str}`

### Requirement: `AQUALIFE_ROOT` Env Var Resolves Against Project Root

The system MUST read `AQUALIFE_ROOT` from the environment with default `./Proyecto-Aqualife/` and MUST resolve relative paths against the **project root**, not the current working directory. When the root is unset AND the resolved path is not writable, the endpoint MUST fail with HTTP 500 and an `ErrorResponse` body naming the failing path and the cwd.

#### Scenario: Default root resolves against project root, not cwd

- GIVEN the process starts from a subdirectory of the project root (worktree checkout)
- AND `AQUALIFE_ROOT` is unset
- WHEN the client resolves a species folder
- THEN the created folder lives at `<project_root>/Proyecto-Aqualife/...`, NOT `<cwd>/Proyecto-Aqualife/...`

#### Scenario: Unwritable root fails loudly

- GIVEN `AQUALIFE_ROOT` is set to a read-only path
- WHEN the client posts `POST /api/species-folder/{g}/{e}`
- THEN the response is HTTP 500 with `{detail: "...AQUALIFE_ROOT... not writable..."}`

### Requirement: Existence Check Returns Path or 404

The system MUST expose `GET /api/species-folder/{genus}/{epithet}` returning HTTP 200 with `{"path": str, "exists": true}` when a row exists, and HTTP 404 with `ErrorResponse` when it does not. The `path` MUST be the absolute path stored in the row.

#### Scenario: Existing row returns 200 with path

- GIVEN a `species_folders` row exists for `Panthera tigris`
- WHEN the client requests `GET /api/species-folder/Panthera/tigris`
- THEN the response is HTTP 200 with `{"path": "<absolute path>", "exists": true}`

#### Scenario: Missing row returns 404

- GIVEN no `species_folders` row exists for `Panthera tigris`
- WHEN the client requests `GET /api/species-folder/Panthera/tigris`
- THEN the response is HTTP 404 with `{detail: str}`

### Requirement: Schema Walked by `(genus, epithet)` Survives Re-Imports

The system MUST walk by `(genus, epithet)` on every read and write so re-imports that bump `taxa.id` do not orphan the folder row. The `species_folders` table MUST have `PRIMARY KEY (genus, epithet)` with NO `taxa.id` foreign key; the `(genus, epithet)` pair is the durable identity of the folder row. The endpoint resolves the species name via `resolve_path_by_display_level` and matches the row by the `(genus, epithet)` pair directly.

#### Scenario: Folder row survives manual `taxa.id` bump

- GIVEN a `species_folders` row exists for `(Panthera, tigris)`
- WHEN the test fixture mutates `taxa.id` for `Panthera tigris` (simulating re-import)
- AND the client requests `GET /api/species-folder/Panthera/tigris`
- THEN the system re-binds the row to the new `taxa.id` via `(genus, epithet)` lookup
- AND returns the row's `path` unchanged

### Requirement: Folder Path Rounds Clean for ASCII-Only Species

The system MUST produce folder paths whose segments are the canonical `name` values verbatim for ASCII species, joined by `os.sep`. The path MUST NOT introduce URL-encoded segments or quote characters.

#### Scenario: ASCII segments join verbatim

- GIVEN `Panthera tigris` resolves to `Animalia → Chordata → ... → Panthera tigris`
- WHEN the folder is created
- THEN the on-disk path is `<AQUALIFE_ROOT>/Animalia/Chordata/.../Panthera/Panthera tigris`
- AND no segment is lowercased, percent-encoded, or replaced with underscores

### Requirement: Standalone Migrate Script Applies Schema Without Booting API

The system MUST expose `python -m taxon.migrate {dry-run|apply}` that calls `Base.metadata.create_all(engine)` against `TAXON_DATABASE_URL` for the three new tables (`species_explored`, `species_folders`, `link_visited`). The script MUST print a one-line summary; `apply` MUST NOT drop or alter pre-existing tables.

#### Scenario: dry-run reports without mutating

- GIVEN the SQLite database is missing the three new tables
- WHEN the operator runs `python -m taxon.migrate dry-run`
- THEN the script prints a summary naming the three missing tables
- AND the database file is unchanged on disk

#### Scenario: apply creates the three new tables

- GIVEN the SQLite database is missing the three new tables
- WHEN the operator runs `python -m taxon.migrate apply`
- THEN the script creates `species_explored`, `species_folders`, `link_visited`
- AND the existing `taxa` and `species_paths` tables are untouched

### Requirement: FastAPI Lifespan Bootstraps Schema at Startup

The system MUST call `Base.metadata.create_all(engine)` for the three new tables inside the FastAPI `lifespan` context so a fresh DB picks up the schema on the first app boot. The lifespan MUST NOT attempt to create pre-existing tables (`taxa`, `species_paths`).

#### Scenario: Fresh DB serves the new endpoints after boot

- GIVEN a SQLite database with no `species_explored` / `species_folders` / `link_visited` tables
- WHEN the FastAPI app starts
- THEN `Base.metadata.create_all(engine)` creates the three new tables
- AND the first `POST /api/explored/{g}/{e}` request succeeds

## Out of Scope

- Cloud sync, multi-device, auth — single-user local SQLite per issue #68.
- Subspecies folder nesting — folder stops at the species bucket.
- A `taxa.is_explored` denormalised column — the explored flag is its own table (see `species-explored`).
- Alembic dependency — runtime `create_all` + standalone script is the migration mechanism.
- Path collisions inside `AQUALIFE_ROOT` (case-different segments) — ASCII-only species round-trip verbatim; non-ASCII normalisation is a separate slice.
- Cleanup of folders whose species row is deleted — the existence check is the only "is this alive" probe.
