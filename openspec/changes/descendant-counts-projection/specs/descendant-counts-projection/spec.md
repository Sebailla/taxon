# Spec: descendant-counts-projection

## Purpose

The `descendant-counts-projection` capability persists a `taxon_descendant_counts` table that caches `(species_count, total_count)` for every parent taxon whose `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. The cache lets `/api/tree/children` serve `species_count` in O(1) for these parents (currently `Animalia`, `Eukaryota`, and `Methanobacteriota`) instead of returning `None` because the recursive CTE is too expensive to walk on demand. Rows are populated synchronously on the first read for each projected parent, cached for the lifetime of the database, and rebuilt by `import_data` after a CoL re-import. A standalone `python -m taxon.migrate apply-projection` subcommand re-runs the projection on demand.

## Requirements

### Requirement: Schema Holds One Row Per Projected Parent

The system MUST persist a `taxon_descendant_counts` table with one row per taxon whose `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. The row MUST carry `taxon_id` (PRIMARY KEY, FK to `taxa.id`), `species_count` (INT, descendants whose `rank='species'`), `total_count` (INT, every descendant node), and `computed_at` (TIMESTAMP, wall-clock at rebuild). The table MUST be created by `taxon.migrate apply` via `Base.metadata.create_all` and MUST NOT require Alembic.

#### Scenario: Fresh DB gains the table on apply

- GIVEN a SQLite database with no `taxon_descendant_counts` table
- WHEN the operator runs `python -m taxon.migrate apply`
- THEN the table exists with the four columns above
- AND the existing `taxa` and `species_paths` tables are unchanged

#### Scenario: Existing pre-existing rows survive apply

- GIVEN a SQLite database with `taxa` populated
- WHEN the operator runs `python -m taxon.migrate apply`
- THEN the table is created if missing
- AND pre-existing `taxa` rows are not dropped, altered, or duplicated

### Requirement: First Read Materialises the Row Synchronously

The system MUST consult `taxon_descendant_counts` before the threshold guard and the recursive CTE for every parent whose `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. On a cache miss, the system MUST run a synchronous rebuild for that parent inside the same request, write the resulting row, and return the rebuilt `species_count`. On a cache hit, the system MUST return the cached `species_count` without invoking the threshold guard or the recursive CTE.

#### Scenario: First request for Animalia materialises the row

- GIVEN no `taxon_descendant_counts` row exists for `Animalia`
- WHEN the tree endpoint serves children for `Animalia`
- THEN the response includes `species_count` equal to the rebuilt count
- AND a row exists in `taxon_descendant_counts` with that `taxon_id` afterwards
- AND `computed_at` is set to the rebuild wall-clock

#### Scenario: Subsequent reads return the cached row

- GIVEN a `taxon_descendant_counts` row exists for `Animalia`
- WHEN the tree endpoint serves children for `Animalia`
- THEN the response includes `species_count` from the cached row
- AND the recursive CTE is not invoked
- AND `computed_at` is not modified

### Requirement: Population Rule Is One Row Per Threshold-Exceeding Parent

The system MUST populate a row for every taxon whose `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. Parents below the threshold MUST NOT receive a row. The decision MUST read the same `SPECIES_COUNT_LAZY_NULL_THRESHOLD` constant the threshold guard reads, so the two paths never disagree.

#### Scenario: Threshold-exceeding parents gain rows

- GIVEN three parents exceed the threshold (`Animalia`, `Eukaryota`, `Methanobacteriota`)
- WHEN the operator runs `python -m taxon.migrate apply-projection`
- THEN the table contains exactly three rows after the run
- AND each row's `taxon_id` matches one of the three parents

#### Scenario: Parents below the threshold gain no row

- GIVEN a parent has fewer direct children than the threshold
- WHEN the operator runs `python -m taxon.migrate apply-projection`
- THEN the table does NOT contain a row for that parent
- AND a later tree request for it falls through to the existing threshold + CTE path

### Requirement: Rebuild Bounded by the Per-Request SLO

The system MUST bound the synchronous rebuild so the tree endpoint meets its per-request SLO (1 s for `/api/tree/children`). If the predicted or measured rebuild cost exceeds the budget, the system MUST fall back to the existing batched CTE path, skip the write, and let the caller observe `species_count=None` on the first request — the same behaviour the pre-change code returns.

#### Scenario: Rebuild under budget writes the row

- GIVEN no cached row exists for `Animalia`
- AND the projected rebuild cost for `Animalia` is under the 1 s budget
- WHEN the tree endpoint serves children for `Animalia`
- THEN the response includes a numeric `species_count`
- AND a row exists in `taxon_descendant_counts` afterwards

#### Scenario: Rebuild over budget skips the write

- GIVEN no cached row exists for a parent whose projected rebuild exceeds the budget
- WHEN the tree endpoint serves children for that parent
- THEN the response includes `species_count=None`
- AND no row is written to `taxon_descendant_counts`
- AND the next request takes the same fall-back path until the row eventually appears

### Requirement: `import_data` Rebuilds Every Projected Parent After a CoL Re-Import

The system MUST rebuild every row in `taxon_descendant_counts` as the last step of a successful CoL re-import invoked through `python -m taxon.import_data`. The rebuild MUST upsert one row per threshold-exceeding parent and MUST be idempotent — running it twice on the same dataset MUST leave the table in the same state.

#### Scenario: CoL re-import leaves the table fresh

- GIVEN a CoL re-import completes successfully
- WHEN the import script returns
- THEN `taxon_descendant_counts` contains one row per threshold-exceeding parent in the new dataset
- AND each row's `computed_at` is later than the import start time

#### Scenario: Rebuild is idempotent on the same dataset

- GIVEN `taxon_descendant_counts` already reflects the current dataset
- WHEN the operator runs `python -m taxon.import_data` (or equivalent re-import) twice
- THEN the row count is unchanged after both runs
- AND the values for `species_count` and `total_count` do not change between runs

### Requirement: `apply-projection` Subcommand Re-Runs the Projection on Demand

The system MUST expose `python -m taxon.migrate apply-projection` as a manual escape hatch. The subcommand MUST scan every taxon whose `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`, upsert a row per parent, and exit zero on success. Running the subcommand MUST NOT require a full `import_data` run and MUST be safe to invoke on a database whose cached rows are stale (e.g. after a manual SQL change or restore-from-backup).

#### Scenario: Stale table recovers via apply-projection

- GIVEN `taxon_descendant_counts` is missing or stale (e.g. rows older than the most recent taxa mutation)
- WHEN the operator runs `python -m taxon.migrate apply-projection`
- THEN the table is repopulated with one row per current threshold-exceeding parent
- AND each row's `computed_at` is the wall-clock of the apply-projection run

#### Scenario: apply-projection is idempotent

- GIVEN `taxon_descendant_counts` already reflects the current dataset
- WHEN the operator runs `python -m taxon.migrate apply-projection`
- THEN the row count is unchanged
- AND `species_count` and `total_count` for every row match the previous values
- AND the script exits zero

### Requirement: Schema Adds Without Touching Legacy Databases

The system MUST treat the projection as purely additive: legacy `taxon.db` files that lack `taxon_descendant_counts` MUST keep working as if the change were absent. The `/api/tree/children` surface MUST NOT change (no new query params, no new response keys, no renames). On a database that lacks the table, the read path MUST detect the absence and fall through to the existing threshold + CTE path.

#### Scenario: Legacy DB serves the same responses as before

- GIVEN a `taxon.db` without `taxon_descendant_counts`
- WHEN the tree endpoint serves children for any parent
- THEN the response shape is identical to the pre-change behaviour
- AND for parents above the threshold, `species_count=None` (same as pre-change)

#### Scenario: Legacy DB becomes a cache-aware DB after apply

- GIVEN a `taxon.db` without `taxon_descendant_counts`
- WHEN the operator runs `python -m taxon.migrate apply`
- THEN the table exists
- AND the next request for a threshold-exceeding parent materialises a row

## Out of Scope

- A new public endpoint — the projection is internal; `/api/tree/children` is unchanged.
- A schema migration tool beyond `taxon.migrate apply` — Alembic remains out of scope.
- Non-SQLite backends — SQLite is the only target.
- A TTL on cached rows — `computed_at` is observability only; no row expires.
- A change to `SPECIES_COUNT_LAZY_NULL_THRESHOLD` — the projection adopts whatever value the threshold guard already uses.
- Frontend work — the UI keeps rendering `?` until the cache resolves; no client changes.
- A denormalised `species_count` column on `taxa` — the projection is its own table.