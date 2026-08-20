# Explore: WoRMS → Catalogue of Life DwC-A migration

> **Note**: This `explore.md` was produced directly by the orchestrator in a SDD-latched session (the prior `sdd-apply` task in this conversation returned `sdd_task_result_empty` and the SDD pipeline stays latched until a new session is started). The content below documents the discovery that a formal `sdd-explore` sub-agent would have produced. **It must be re-produced by a fresh `sdd-explore` invocation in the next session before the proposal phase begins.** The next session's latched SDD cannot be re-armed here.

## Intent

The repo today imports WoRMS (World Register of Marine Species), a custom indentation-based text dump. The user wants to migrate to the Catalogue of Life (CoL), which distributes its data as a Darwin Core Archive (DwC-A) — a standard biodiversity format. Migration is full replacement (no WoRMS fallback), covers backend + frontend, and the real DwC-A is downloaded during the apply phase.

Captured product decisions (see Engram `sdd/col-dwc-a-importer/context`):

1. **Source**: DwC-A (Darwin Core Archive). Recommended over the Annual Checklist Archive (annual snapshot) and the COL API (operationally heavier, rate-limited).
2. **Scope**: Backend + frontend. CoL-specific fields (e.g. `nameAccordingTo`, `taxonomicStatus`) surface in the UI only if the design phase decides to.
3. **Compatibility**: WoRMS is fully replaced. `python -m taxon.import_data` only understands DwC-A after the migration.
4. **Dataset**: Real DwC-A is downloaded during the apply phase.

## Scope of this exploration

Three production files would change. Everything else stays.

### What stays

| File | Reason |
|------|--------|
| `taxon/schema.py` | `Taxon` / `SpeciesPath` / `TaxonDescendantCount` ORM classes already carry `is_synonym`, `parent_id`, `rank`, `display_name`, `display_level`, marker columns — most of what DwC-A maps onto. No schema additions required for the first slice. |
| `taxon/taxonomy.py` | `RANK_TO_DISPLAY_LEVEL` whitelist already covers kingdom → family → species. **May need** additions for CoL ranks: `subtribe`, `infratribe`, `parvorder`, `superorder`, `infraorder`, `superfamily`, `variety`, `form`, `subform`, `forma_specialis`, `section`, `subsection`. TBD at design time. |
| `taxon/api/tree.py` | Read-path code (tree children endpoint). Unchanged. Already reads from `taxa` table the same way. |
| `taxon/api/_tree_tiers.py` | Tier walker (per-tier subtree envelope). Unchanged. |
| `taxon/api/projections.py` | `taxon_descendant_counts` projection + helpers (`materialize_for_parent`, `register_display_level`, etc.). Unchanged. The importer for CoL must still call `_rebuild_descendant_counts_projection` at the end of a successful import (wire it identically to PR #86). |
| `taxon/api/__init__.py` | FastAPI factory + lifespan. Unchanged. Already bootstraps `taxon_descendant_counts` (PR #89). |
| `taxon/api/database_url.py` | URL resolution with fallback. Unchanged. |
| `taxon/api/workspace.py` | Species-folder-explorer tables. Unchanged. |
| `taxon/migrate.py` | `apply` + `apply-projection` subcommands. Unchanged. |
| `taxon/api/router.py`, schemas, etc. | All API surface. Unchanged. |
| `openspec/changes/archive/2026-08-19-descendant-counts-projection/` | Archived SDD artifacts. Unaffected. |
| All `learn-es/*.md` entries | History. Unaffected. |

### What changes

| File | Action | Reason |
|------|--------|--------|
| `taxon/parser.py` | **Replace** with `taxon/dwc_parser.py` | The 178-line WoRMS indentation regex is structurally incompatible with CoL's flat DwC-A TSV. Different file because the WoRMS parser may be useful historically; the new parser deserves its own module. |
| `taxon/import_data.py` | **Replace** with `taxon/col_importer.py` | New importer: zip download (optional), stream the unzipped `taxon.txt`, batch SQL inserts, hierarchy-level ordering for FK resolution, end-of-import call to `_rebuild_descendant_counts_projection`. |
| `taxon/tests/test_parser.py` | **Replace** with `taxon/tests/test_dwc_parser.py` | Tests for the new DwC parser. |
| `taxon/tests/test_import.py` | **Replace** with `taxon/tests/test_col_importer.py` | Tests for the new importer. |
| Docstrings referencing WoRMS | **Edit** | Multiple files (e.g. `import_data.py:1`, `parser.py:1`) call out WoRMS — update to call out CoL DwC-A. |
| `DEFAULT_SOURCE` constant | **Change** | From `/Users/sebailla/Developer/research/worm/dataset-2011.txt` to a CoL DwC-A URL (TBD at design time — likely `https://www.checklistbank.org/dataset/3/export/dwca` or a downloadable mirror). |

### What stays but needs new investigation at proposal/design time

- The exact column names in `taxon.txt` for the CoL DwC-A (see "Schema reference" below).
- Whether the CoL DwC-A carries `taxonRank` values that map cleanly onto `RANK_TO_DISPLAY_LEVEL` or require additions.
- The mapping of `taxonomicStatus` to `is_synonym` (and the absence of a flag for "invalid" — should they be excluded from the tree?).
- Whether to record the authorship citation in `display_name` (current behavior: WoRMS strips via the regex; DwC-A has it as a separate column `scientificNameAuthorship`).
- The pre-import behavior: drop-all or upsert? The existing WoRMS importer drops and recreates (idempotent). DwC-A should do the same.

## Schema reference (Darwin Core Taxon class)

The relevant DwC terms for `taxon.txt` (extracted from `https://dwc.tdwg.org/terms/`):

| DwC term | Maps to `Taxon` column | Notes |
|----------|------------------------|-------|
| `taxonID` | `source_id` | The WoRMS importer uses `{namespace}:{id}` (e.g. `worms:123`); DwC-A typically uses `COL:123` or just a numeric/UUID. |
| `parentNameUsageID` | resolves to `parent_id` | FK to `taxa.id` after resolving the source_id. NULL for kingdom-tier or virtual roots. |
| `acceptedNameUsageID` | context-dependent | NULL → this row IS the accepted taxon. Non-NULL → this row is a synonym; `parent_id` should point at the *accepted* taxon's parent, and `is_synonym = True`. |
| `scientificName` | `display_name` | Includes the authorship citation, e.g. `Animalia Linnaeus, 1758`. |
| `scientificNameAuthorship` | (extract from scientificName) | Separate column in DwC-A — the WoRMS parser extracted this from a trailing parenthetical. |
| `taxonRank` | `rank` | Literal string, e.g. `kingdom`, `phylum`. |
| `taxonomicStatus` | `is_synonym` | Values: `accepted`, `synonym`, `invalid`, `misapplied`, `doubtful`. Filter `accepted` rows as the primary tree; row `synonym` rows with `is_synonym = True` but `parent_id` pointing at the accepted taxon (or its parent). |
| `nameAccordingTo` | (new optional column) | Bibliographic source of the taxonomic decision. Could land in a future `Taxon.source` column or be dropped in the first slice. |
| `acceptedNameUsage` | (no mapping) | Verbose name of the accepted taxon. Same content as `scientificName` if the row IS the accepted one. |
| `taxonRemarks`, `taxonConceptID`, `namePublishedIn` | not in first slice | Defer to follow-up proposal. |

## Mapping challenges (preliminary)

1. **`parent_id` FK resolution**: `taxa.parent_id` is currently `INTEGER` referencing `taxa.id`. DwC-A gives `parentNameUsageID` as a string (the source ID of the parent). The importer needs to either:
   - (a) Two-pass: insert accepted taxa first (resolving `source_id → id` in a dict), then a second pass for synonyms.
   - (b) Sort by hierarchy depth before insert (root taxa at the front, leaves at the back).
   - Option (a) is more robust and matches the lazy acceptance pattern.

2. **Synonyms need special handling**: A synonym row has its own `sourceID`, its own `scientificName`, and an `acceptedNameUsageID` pointing at the accepted taxon's source_id. The `parent_id` for the synonym should be **the same parent as the accepted taxon** (in the tree UI, a synonym is a sibling of the accepted taxon, not a child of it). The DwC spec is ambiguous here; the WoRMS importer marked synonyms as children of their accepted name. **This is a behavior change**: synonyms under CoL should mirror the accepted taxon's parent, not the accepted taxon itself.

3. **`display_level` resolution**: CoL DwC-A may carry a `verbatimTaxonRank` or similar that maps directly onto `display_level`. The WoRMS importer left `display_level` NULL and let the SQL function `taxonomy_display_level` resolve from `rank`. The CoL importer can do the same (no schema change) or precompute it at insert time for a small read-time speedup. Defer the decision to the design phase.

4. **Authorship extraction**: With WoRMS the authorship was a trailing parenthetical on the line. DwC-A's `scientificNameAuthorship` is a separate column — easier. But the canonical name (`Taxon.name` in the schema) is the *author-stripped* form. Need a helper to strip trailing authorship from `scientificName` (already exists in `taxonomy.py` as `display_level`; not quite the same — a new `strip_authorship(name, authorship)` helper).

## Risk hot spots

1. **7M-row dataset**. The WoRMS importer streams via stack-based parsing. The DwC-A importer must do the same (read line by line, batch SQL inserts every `BATCH_SIZE = 1_000` rows). Memory bounded by batch size.

2. **Foreign-key ordering**. DwC-A is flat — no indentation to guide parent-first inserts. The two-pass strategy (or topology sort) is mandatory. NOT a wait-but-fix-after-the-fact: every row with an unresolved parent_id crashes `INSERT`.

3. **Zip download for `apply-projection` and runtime**. The DwC-A archive is ~600MB compressed, ~2GB expanded. The CLI may want to default to an already-downloaded file (e.g. `/Users/sebailla/Developer/research/col/col-dwca.zip`) and accept a `--download` flag for first-run. Network failures during import should not corrupt the DB — wrap the whole transaction in one `Base.metadata.create_all` call.

4. **`meta.xml` schema drift**. The DwC-A schema is stable, but yearly CoL releases can rename or repurpose columns (e.g. `taxonRank` values). The parser should be tolerant: missing columns default to NULL/empty, unknown ranks land in `RANK_TO_DISPLAY_LEVEL` as `None` (excluded from cascade).

5. **The `_batch_species_counts` and `species_paths` projections**. Both currently run after `_populate_species_paths`. The CoL importer must call them in the same order — first paths, then projection rebuild — so the data lands before the projection reads it.

## Schema-level decision: do we extend `Taxon`?

**No, in the first slice.** The existing `Taxon` schema can carry CoL data with no migration. If the design phase decides to surface CoL-specific metadata (e.g. `source`, `taxonConceptID`), that's a follow-up.

However, the `_extract_markers` and citation-parsing logic from `taxon/parser.py` does NOT need to be ported. DwC-A's `taxonomicStatus` field is the source of `is_synonym` (no regex needed). `scientificNameAuthorship` is already separate. The new parser is mostly a TSV reader with column mapping.

## Out of scope (deferred to follow-ups)

- New public endpoints (e.g. search by author, distribution map).
- Frontend visualization of CoL-specific fields.
- Schema extensions (e.g. distribution, conservation status, taxonRemarks).
- Two-pass through the dataset for partial re-imports (insert all *new* taxa without rebuilding the entire DB).
- API/Annual formats — only DwC-A in this change.

## Open questions for the proposal phase

1. The exact URL of the DwC-A archive for the latest annual release (TBD; flag this for verification before apply).
2. The set of `taxonRank` values in CoL that need to be added to `RANK_TO_DISPLAY_LEVEL` (TBD — generate from a sample of the dataset).
3. Whether `scientificName` carries infrageneric markers (CoL sometimes appends `(Subgenus)` or `[unranked]` to the name). If yes, the importer strips them into the existing four boolean columns (`is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`) and into `display_name`.
4. The behavior of `taxonomicStatus = "invalid"` rows — drop them or keep with `is_invalid` flag (no current flag, would need a schema extension).

## Estimated scope (rough)

- `taxon/dwc_parser.py`: ~150 lines (column mapping + two-pass resolution + authorship strip + synonym handling).
- `taxon/col_importer.py`: ~150 lines (zip open + TSV stream + batch insert + projection call).
- `taxon/tests/test_dwc_parser.py`: ~300 lines (red-first for every column mapping edge case).
- `taxon/tests/test_col_importer.py`: ~250 lines (red-first for batch insert, hierarchy order, idempotency).
- Docs + Spanish mirrors + OpenSpec artifacts: ~250 lines.
- Total: ~1100 lines, comfortably under the 400-line budget if split per concern (parser, importer, tests, docs).

## Open decision needed before apply: chain strategy

Following the SDD preflight, the deliverability forecast will be `medium-high` because the schema changes are concentrated in two files (`parser.py` → `dwc_parser.py`, `import_data.py` → `col_importer.py`) but the test surface is broad. The user previously chose `size:exception` for PR #86 — the same may apply here.

TBD at the proposal phase: chain `stacked-to-main`, `feature-branch-chain`, or `size:exception`.

## Reference material

- DwC Quick Reference: <https://dwc.tdwg.org/terms/>
- CoL ChecklistBank API: <https://www.checklistbank.org>
- CoL DwC-A export endpoint: <https://www.checklistbank.org/dataset/3/export/dwca> (returns 403 in headless curl with anti-bot challenge; the dataset export is real and available to logged-in users via the GUI).