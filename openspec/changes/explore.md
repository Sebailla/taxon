## Exploration: taxon species search app

### Current State
`/Users/sebailla/Developer/taxon` is a greenfield scaffold containing only SDD/OpenSpec metadata; no application code or specs exist. The read-only WoRMS dump has exactly 1,394,847 UTF-8 lines, and the four pre-split files exist. Its tree uses exactly two spaces per depth (observed depths 0–40), but biological rank and depth are not equivalent: intermediate ranks such as subfamily and subgenus occur, and canonical ranks may be absent. The first 200 lines contain `[superdomain]`, `[kingdom]`, `[subkingdom]`, `[phylum]`, `[class]`, `[order]`, `[family]`, `[subfamily]`, `[genus]`, `[subgenus]`, `[species]`, and `[subspecies]`; the final 50 show branches ending at genus with no species. Across the file, canonical counts include 9 kingdoms, 142 phyla, 532 classes, 2,127 orders, 13,743 families, 117,896 genera, and 1,095,016 species, plus many intermediate/infraspecific ranks. Names precede the final rank token and metadata block, so author citations and parentheses are part of the display text. Prefixes encode status: `=` synonym (674,806 lines), `†` extinct (182,843), `?` uncertain/incertae sedis (757), and `[unassigned]` appears inside 11 names; combinations exist (`†?`). Quoted bacteria occur as `"Candidatus ..."`, not the unquoted form. These markers must be stored separately while preserving the verbatim display text and source ID.

The reference Google Sheet is the behavioral source for 12 labeled search links generated from a species query. Known templates are:
- Wikipedia — `http://es.Wikipedia.org/wiki/Special:Search?search={q}`
- Google — `http://Google.com/search?q={q}`
- BHL — `http://biodiversitylibrary.org/search?SearchTerm={q}`
- ResearchGate — `http://researchgate.net/search?q={q}`
- Plos — `http://journals.plos.org/plosone/search?filterJournals=PLoSONE&q={q}&page=1`
- Academia — `http://academia.edu/people/search?utf8=%E2%9C%93&q={q}`
- Scielo — `http://search.scielo.org/?q={q}`
- Scholar — `http://scholar.google.com/scholar?hl=es&as_sdt=0%2C5&q={q}&btnG=`
- Youtube — `http://youtube.com/results?search_query={q}`
- Zootaxa — `http://mapress.com/j/zt/search/search?query={q}`
- Photos — exact long Google Images formula is not present in observation 3566 and remains to be captured from the sheet
- Sci-hub — `http://sci-hub.se/` (constant; no species substitution)

### Affected Areas
- `/Users/sebailla/Developer/taxon/` — greenfield; this project will live here
- `/Users/sebailla/Developer/research/worm/dataset-2011.txt` — read-only source data
- `/Users/sebailla/Developer/research/worm/dataset-2011.part0{0..3}.txt` — pre-split parts (orchestrator already split them)

### Approaches
1. **SQLite adjacency-list `taxa` table** — one row per taxon with `id/source_id`, `parent_id`, `rank`, normalized canonical name, verbatim display name, and status flags; index `(parent_id, rank, name)` and `(rank, name)`.
   - Pros: faithfully models irregular depth and intermediate ranks; direct parent/children queries; avoids nullable per-rank duplication; SQLite easily handles 1.39M indexed read-mostly rows.
   - Cons: canonical cascade queries may require recursive ancestry or precomputed projections; genus names are not globally unique, so IDs—not `{name}`—must identify nodes.
   - Effort: Medium.

2. **Separate tables per canonical rank** — Kingdom through Species with foreign keys between levels.
   - Pros: simple canonical joins and strongly constrained cascade schema.
   - Cons: loses or awkwardly bypasses intermediate ranks, missing ranks, synonyms, and infraspecific taxa; forces cleanup assumptions the source does not support; migration/import logic multiplies across tables.
   - Effort: High.

3. **Flat species projection table/CSV** — one row per accepted species with nullable Kingdom/Phylum/Class/Order/Family/Genus columns, optionally beside a raw taxa table.
   - Pros: fastest and simplest cascade `DISTINCT` queries; CSV is auditable and portable; no recursive query in request paths.
   - Cons: duplicates ancestor text across ~1M rows; cannot faithfully represent the whole tree alone; ambiguous repeated names require IDs/path keys; synonym policy must be explicit.
   - Effort: Medium.

4. **Static JSON files served by FastAPI** — precompute one file per parent/path.
   - Pros: no database dependency and highly cacheable immutable reads.
   - Cons: very many files or very large payloads, weak ad-hoc querying, costly regeneration, deployment/package pressure, and application-level integrity/versioning.
   - Effort: Medium–High.

### Recommendation
Use Python 3.11, FastAPI, SQLAlchemy, and SQLite with the adjacency-list `taxa` table as the source of truth, plus a materialized/indexed canonical `species_paths` projection for the UI cascade and CSV export. This combines source fidelity with cheap request-time queries. Persist marker flags (`is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`), source LSID, rank, raw/verbatim label, and a separately derived searchable scientific name. Default the cascade to accepted species (`=` excluded) while retaining synonyms for future lookup; make extinct inclusion a product decision.

Parse as a streaming, single-pass stack algorithm: count leading spaces, require an even count, pop stack entries at or below the incoming depth, parse the final rank token before `{...}`, parse metadata independently, attach to the current parent, and push the node. Maintain the latest canonical ancestor IDs/labels; on an accepted `[species]`, emit its canonical path projection immediately. This is O(n) time and O(d) parser memory (observed maximum depth 20 nodes), with batched SQLite inserts/CSV writes rather than loading 1.39M lines. Do not parse authors by splitting on spaces, and do not concatenate part files independently without carrying stack state across boundaries; preferably stream the original file, or preserve parser state between ordered parts. Test malformed rank brackets seen in the corpus, odd indentation, missing canonical ancestors, species beneath subgenera, synonym species nested beneath accepted species, `†?`, `[unassigned]`, Unicode, and quoted `"Candidatus ..."` names.

Use ID-based cascade routes because names are not guaranteed globally unique:
- `GET /api/kingdoms` → `[{"id": 2, "name": "Animalia", "display_name": "Animalia"}]`
- `GET /api/taxa/{kingdom_id}/phyla`
- `GET /api/taxa/{phylum_id}/classes`
- `GET /api/taxa/{class_id}/orders`
- `GET /api/taxa/{order_id}/families`
- `GET /api/taxa/{family_id}/genera`
- `GET /api/genera/{genus_id}/species` → species summaries with IDs, display names, and marker flags
- `GET /api/species/{species_id}/links` → `{"species": {...}, "links": [{"source": "Wikipedia", "url": "..."}, ...]}`
If compatibility requires the proposed name paths, treat them as URL-encoded lookup aliases that can return ambiguity errors, not primary identifiers. Add immutable-data cache headers (`ETag`/`Last-Modified`, long `max-age`) and a small in-process LRU for child lists; do not add Redis initially. Query parameters must be built with UTF-8 percent-encoding using standard URL construction while preserving each template's fixed encoded parameters. Preserve the sheet's exact HTTP templates in a compatibility mode; a separate secure mode may upgrade only hosts verified to support HTTPS without redirects or changed behavior. Sci-hub should remain a constant link and be flagged as such. The exact Photos URL must be obtained before specification if formula parity is mandatory.

Frontend state is a deterministic dependency chain: `kingdomId → phylumId → classId → orderId → familyId → genusId → speciesId`. Selecting a level clears every descendant selection and cached/error state, then fetches only the next level; disabled/loading/error/empty states are per level and stale responses must be ignored or aborted. The species list renders after genus selection; selecting a species fetches `/links` and renders the 12 source buttons beside/below that species, with external-link safety attributes. The prompt calls these “5 levels,” but there are six dependent taxonomy selects after Kingdom (Phylum, Class, Order, Family, Genus) plus selected species.

Strict TDD should start with parser fixtures for every marker/shape, import integration tests and count/integrity assertions, indexed API query tests, exact URL-template/encoding tests, then React cascade reset/race/loading/error tests before implementation.

### Risks
- Exact Google Images/Photos formula is unavailable in the retrieved initialization observation; sheet-parity cannot be proven until it is captured verbatim.
- Product policy is undecided for synonyms, extinct taxa, uncertain taxa, infraspecific ranks, and species missing one or more canonical ancestors.
- Splitting by line count can place a part boundary mid-branch; independent parsing would lose ancestry.
- A scientific name cannot be safely derived by naive author stripping; display labels, canonical searchable names, and source IDs need explicit rules.
- Genus names may repeat under different parents; name-based endpoint paths are ambiguous and potentially huge unfiltered genus lists must never be sent to the client.
- SQLite should handle 1.39M read-mostly rows with correct indexes and batched imports, but import duration, database size, cascade query plans, and worst-case children counts need measured acceptance benchmarks.
- Legacy HTTP destinations create mixed-content/privacy/security concerns; blind HTTPS rewriting would violate exact sheet mirroring and may break endpoints.
- The dataset filename suggests 2011, but sampled records include publication years through 2025; provenance/version semantics must be clarified rather than inferred from the filename.

### Ready for Proposal
Yes, after the proposal records three explicit decisions: use ID-based routes with adjacency-list plus projection; define the accepted/synonym/extinct/infraspecific inclusion policy; and obtain or intentionally defer the exact Photos formula. The next phase can propose the app and an import benchmark spike, but exact 12-link parity remains blocked only for Photos.
