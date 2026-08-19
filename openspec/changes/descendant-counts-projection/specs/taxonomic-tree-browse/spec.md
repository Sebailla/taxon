# Delta for taxonomic-tree-browse

## MODIFIED Requirements

### Requirement: Lazy Expand Caches by parent_id

The system SHALL fetch children of a parent taxon exactly once per `parent_id` and cache for the session. When the parent's `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD`, the system SHALL additionally consult `taxon_descendant_counts` (see `descendant-counts-projection`) before the threshold guard and the recursive CTE so `species_count` is served from the cache without invoking the CTE on subsequent reads.
(Previously: the threshold guard returned `species_count=None` for every parent whose `direct_children_count` exceeded the threshold; the recursive CTE was never invoked for those parents.)

#### Scenario: First request for a threshold-exceeding parent triggers rebuild

- GIVEN no cached row exists for the threshold-exceeding parent in `taxon_descendant_counts`
- WHEN the user expands that parent's row
- THEN the system issues `GET /api/tree/children?parent_id={id}` and runs the cache rebuild inline
- AND the response includes a numeric `species_count`
- AND a row exists in `taxon_descendant_counts` after the response

#### Scenario: Subsequent requests read the cached row

- GIVEN a cached row exists for the threshold-exceeding parent
- WHEN the user expands that parent's row
- THEN the system issues `GET /api/tree/children?parent_id={id}` and returns `species_count` from the cached row
- AND the recursive CTE is not invoked

#### Scenario: Re-expand reads cache

- GIVEN the parent has been expanded
- WHEN the user collapses and re-expands
- THEN no new request fires and cached children render immediately

## ADDED Requirements

### Requirement: Read Path Consults the Projection Before the Threshold Guard

The system SHALL consult `taxon_descendant_counts` for every parent whose `direct_children_count` exceeds `SPECIES_COUNT_LAZY_NULL_THRESHOLD` before invoking the threshold guard or the recursive CTE. On a cache hit, the system SHALL return `species_count` from the cached row without invoking the threshold guard or the CTE. On a cache miss, the system SHALL fall through to the existing threshold + CTE path; if the threshold branch fires, the system SHALL run the synchronous rebuild (see `descendant-counts-projection`) and write the row before returning.

#### Scenario: Cache hit short-circuits the threshold branch

- GIVEN a row exists in `taxon_descendant_counts` for the parent
- WHEN `_count_descendant_species` runs for that parent
- THEN the function returns the cached `species_count` directly
- AND the threshold guard is not consulted
- AND the recursive CTE is not invoked

#### Scenario: Cache miss falls through to the threshold + CTE path

- GIVEN no row exists in `taxon_descendant_counts` for the parent
- WHEN `_count_descendant_species` runs for that parent
- THEN the existing threshold + CTE path runs unchanged
- AND if the threshold branch fires, the rebuild writes the row before returning

### Requirement: Batch Read Pre-Loads Cached Rows

The system SHALL pre-load cached rows from `taxon_descendant_counts` in a single `IN`-list query for every batch the tree endpoint serves. The system SHALL merge the cached rows with the CTE-resolved rows so the response carries a numeric `species_count` for every cached parent and the CTE value for every other parent. The system MUST NOT invoke the recursive CTE for any parent whose cached row is present.

#### Scenario: Mixed batch returns cached and CTE counts

- GIVEN the batch contains one threshold-exceeding parent with a cached row and three sub-threshold parents
- WHEN `_batch_species_counts` resolves the batch
- THEN the response carries the cached `species_count` for the threshold-exceeding parent
- AND the response carries CTE-derived `species_count` for the three sub-threshold parents
- AND the recursive CTE is not invoked for the cached parent

#### Scenario: Cached stale row wins over CTE

- GIVEN a cached row exists for the parent
- WHEN `_batch_species_counts` resolves the parent
- THEN the response carries the cached `species_count`
- AND the CTE value (which may differ) is discarded

## REMOVED Requirements

### Requirement: Threshold Returns species_count=None Unconditionally

(Reason: the lazy-null behaviour for threshold-exceeding parents is replaced by the cache-aware read path; the threshold branch now only fires on a cache miss, and even then the rebuild short-circuits to a write when the cost stays under the SLO. Parents above the threshold may still see `species_count=None` if the rebuild exceeds the budget, but that is now a fall-back state, not the steady state.)
(Migration: clients that tolerate `species_count=None` keep working. Clients that need a guaranteed numeric value SHOULD pre-warm the cache via `python -m taxon.migrate apply-projection` after any non-`import_data` re-import.)