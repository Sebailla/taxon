# Spec: species-explored

## Purpose

The `species-explored` capability lets the user mark a species as explored, persists that flag across sessions, and survives the project's known re-import churn by keeping the explored state in a separate table rather than as a column on `taxa`. The flag is surfaced as a checkbox in the trailing column of each `SpeciesList` row, alongside the folder badge/button from the `species-folder` spec. Closes sub-feature A of issue #68.

## Requirements

### Requirement: Set Explored Flag Is Idempotent

The system MUST expose `POST /api/explored/{genus}/{epithet}` that upserts a row in `species_explored` and returns HTTP 200 with the resolved species row (same shape as `species-lookup`). The endpoint MUST be idempotent — re-posting the same `(genus, epithet)` MUST NOT raise and MUST refresh `explored_at` to the current timestamp.

#### Scenario: First POST returns 200 with species row

- GIVEN `Panthera tigris` resolves to a species
- WHEN the client posts `POST /api/explored/Panthera/tigris`
- THEN the response is HTTP 200
- AND the body contains the species `id`, `canonical_name`, `display_name`, `markers`, and `breadcrumb`
- AND a `species_explored` row exists with `genus="Panthera"`, `epithet="tigris"`

#### Scenario: Repeat POST refreshes explored_at

- GIVEN a `species_explored` row exists for `Panthera tigris`
- WHEN the client posts `POST /api/explored/Panthera/tigris` again
- THEN the response is HTTP 200 (no 409)
- AND the row's `explored_at` is updated to the new timestamp

### Requirement: Unset Explored Flag Removes the Row

The system MUST expose `DELETE /api/explored/{genus}/{epithet}` that removes the `species_explored` row and returns HTTP 204. The endpoint MUST be idempotent — deleting a non-existent row MUST return 204 (not 404).

#### Scenario: Existing row deletion returns 204

- GIVEN a `species_explored` row exists for `Panthera tigris`
- WHEN the client deletes `DELETE /api/explored/Panthera/tigris`
- THEN the response is HTTP 204
- AND the row no longer exists

#### Scenario: Missing row deletion is a no-op

- GIVEN no `species_explored` row exists for `Panthera tigris`
- WHEN the client deletes `DELETE /api/explored/Panthera/tigris`
- THEN the response is HTTP 204 (no 404)

### Requirement: Schema Walked by `(genus, epithet)` Survives Re-Imports

The system MUST walk by `(genus, epithet)` on every read and write so re-imports that bump `taxa.id` leave the explored flag intact. The `species_explored` table MUST have `PRIMARY KEY (genus, epithet)` with NO `taxa.id` foreign key; the `(genus, epithet)` pair is the durable identity of the workspace row. The endpoint resolves the species name via `resolve_path_by_display_level` and matches the row by the `(genus, epithet)` pair directly.

#### Scenario: Re-import preserves explored flag without FK re-bind

- GIVEN a `species_explored` row exists for `(Panthera, tigris)`
- WHEN the test fixture mutates `taxa.id` for `Panthera tigris` (simulating re-import)
- AND the client requests `GET /api/explored/list` or otherwise inspects the row
- THEN `Panthera tigris` still reports as explored
- AND no re-bind operation is required (the row keys on `(genus, epithet)`, not on `taxa.id`)

### Requirement: GET List Endpoint Hydrates the Workspace

The system MUST expose `GET /api/explored/list` that returns the full explored set as `{"species": [{"genus": str, "epithet": str, "explored_at": str}, ...]}` with HTTP 200. The list MUST be empty (not 404) when no rows exist. The frontend `hydrate` action calls this endpoint on App mount so the explored checkboxes reflect persisted state on first paint.

#### Scenario: Existing rows return list

- GIVEN `species_explored` has rows for `Panthera tigris` and `Panthera leo`
- WHEN the client requests `GET /api/explored/list`
- THEN the body contains both entries with `genus`, `epithet`, `explored_at`

#### Scenario: No rows returns empty list

- GIVEN no `species_explored` rows exist
- WHEN the client requests `GET /api/explored/list`
- THEN the response is HTTP 200 with `{"species": []}` (empty array, not 404)

### Requirement: Cross-Reload Survival

The system MUST persist the explored flag to the SQLite database so that a frontend reload (browser refresh) restores the same checkbox state. The hydrate endpoint MUST be the single source of truth for the frontend's `workspaceStore.exploredBySpeciesId` map; the store SHALL NOT keep an unauthenticated local-only flag.

#### Scenario: Reload restores explored state

- GIVEN the user marks `Panthera tigris` as explored on the SPA
- AND the user refreshes the browser
- WHEN the SPA remounts and the `workspaceStore.hydrate()` action runs
- THEN `useWorkspace.getState().exploredBySpeciesId` contains the entry for `Panthera tigris`
- AND the `SpeciesList` row renders the checkbox as checked

## Out of Scope

- A `taxa.is_explored` denormalised column — explicitly avoided to survive re-import churn.
- Cloud sync, multi-device, auth — single-user local SQLite per issue #68.
- Bulk operations (mark all species in a genus as explored) — single-species toggle only.
- Time-window or session-based "explored" semantics — the flag is binary and persists indefinitely.
- Workspace-level "explored" filters (e.g. show only unexplored species) — the flag is persisted but no UI filter is in this scope.
