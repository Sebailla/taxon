# Spec: link-visited

## Purpose

The `link-visited` capability lets the user mark individual search sources as visited for a given species and persists that state across sessions so the user can resume a research session without losing progress. The state is keyed on `(genus, epithet, source_label)` where `source_label` is the canonical name from `docs/sources/templates.md` (the 13-link dispatch). The state is stored in a separate table so switches survive `taxa` re-imports via the same `(genus, epithet)` re-bind discipline used by sibling specs. Closes sub-feature C of issue #68.

## Requirements

### Requirement: Mark a Source Visited Is Idempotent

The system MUST expose `POST /api/link-visited/{genus}/{epithet}/{source}` that upserts a `(species_id, source_label)` row in `link_visited` and returns HTTP 204. The endpoint MUST be idempotent — re-posting the same triple MUST NOT raise and MUST refresh `visited_at` to the current timestamp.

#### Scenario: First POST returns 204 and persists

- GIVEN `Panthera tigris` resolves to a species and `Wikipedia` is in the templates list
- WHEN the client posts `POST /api/link-visited/Panthera/tigris/Wikipedia`
- THEN the response is HTTP 204
- AND a `link_visited` row exists with `species_id` bound to `Panthera tigris` and `source_label="Wikipedia"`

#### Scenario: Repeat POST refreshes visited_at

- GIVEN a `link_visited` row exists for `Panthera tigris / Wikipedia`
- WHEN the client posts `POST /api/link-visited/Panthera/tigris/Wikipedia` again
- THEN the response is HTTP 204 (no 409)
- AND the row's `visited_at` is updated to the new timestamp

### Requirement: Unmark a Source Visited Removes the Row

The system MUST expose `DELETE /api/link-visited/{genus}/{epithet}/{source}` that removes the `(species_id, source_label)` row and returns HTTP 204. The endpoint MUST be idempotent — deleting a non-existent row MUST return 204 (not 404).

#### Scenario: Existing row deletion returns 204

- GIVEN a `link_visited` row exists for `Panthera tigris / Wikipedia`
- WHEN the client deletes `DELETE /api/link-visited/Panthera/tigris/Wikipedia`
- THEN the response is HTTP 204
- AND the row no longer exists

#### Scenario: Missing row deletion is a no-op

- GIVEN no `link_visited` row exists for `Panthera tigris / Wikipedia`
- WHEN the client deletes `DELETE /api/link-visited/Panthera/tigris/Wikipedia`
- THEN the response is HTTP 204 (no 404)

### Requirement: Hydrate Visited Set per Species

The system MUST expose `GET /api/link-visited/{genus}/{epithet}` that returns the visited set as `{"sources": [{"source": str, "visited_at": str}, ...]}` with HTTP 200. The list MUST be empty (not 404) when no rows exist.

#### Scenario: Existing rows return list

- GIVEN `link_visited` has rows for `Panthera tigris` with sources `Wikipedia`, `Google`
- WHEN the client requests `GET /api/link-visited/Panthera/tigris`
- THEN the body contains `{"sources": [{"source": "Wikipedia", ...}, {"source": "Google", ...}]}`

#### Scenario: No rows returns empty list

- GIVEN no `link_visited` rows exist for `Panthera tigris`
- WHEN the client requests `GET /api/link-visited/Panthera/tigris`
- THEN the response is HTTP 200 with `{"sources": []}` (empty array, not 404)

### Requirement: `(genus, epithet)` Walk Survives Re-Imports

The system MUST walk by `(genus, epithet)` on every read and write so re-imports that bump `taxa.id` leave the visited set intact. The `link_visited` table MUST have `PRIMARY KEY (genus, epithet, source_label)` with NO `taxa.id` foreign key; the `(genus, epithet, source_label)` triple is the durable identity. The endpoint resolves the species name via `resolve_path_by_display_level` and matches the row directly by the triple.

#### Scenario: Visited set survives manual `taxa.id` bump

- GIVEN `link_visited` rows exist for `(Panthera, tigris, Wikipedia)` and `(Panthera, tigris, Google)`
- WHEN the test fixture mutates `taxa.id` for `Panthera tigris` (simulating re-import)
- AND the client requests `GET /api/link-visited/Panthera/tigris`
- THEN the response still contains `Wikipedia` and `Google`
- AND no row is orphaned (no FK to re-bind — the row keys on `(genus, epithet, source_label)` directly)

### Requirement: Source Label Is the Template Canonical Name

The system MUST key the visited set on the `source` string from `docs/sources/templates.md` (one of the 13 canonical names: Wikipedia, Google, BHL, ResearchGate, Plos, Academia, Scielo, Scholar, Youtube, Zootaxa, Photos, Sci-hub, Scribd). The endpoint MUST NOT key on the substituted `url` (URLs change per species query).

#### Scenario: URL changes but source stays

- GIVEN the user marks `Wikipedia` visited for `Panthera tigris`
- WHEN the same user opens a different species (`Panthera leo`) and inspects the visited set
- THEN the `Wikipedia` row for `Panthera leo` is independent (no cross-species leak)
- AND the visited set is keyed by `(species_id, source)`, not by URL

## Out of Scope

- Cloud sync, multi-device, auth — single-user local SQLite per issue #68.
- Per-source visit timestamps surfaced in the UI — only the toggle state is shown; `visited_at` is metadata for audit.
- Auto-marking a source visited when the user clicks the embedded link inside `<ExplorerPanel>` — the click handler explicitly calls the toggle endpoint; auto-detect is a separate slice.
- Multi-user isolation — single-user workspace.
- Auto-expiry of visited state — entries persist indefinitely until the user deletes them.
