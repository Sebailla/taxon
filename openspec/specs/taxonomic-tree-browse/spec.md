# Capability: taxonomic-tree-browse

## Purpose

A CoL-style hierarchical tree replaces the 7-dropdown linear cascade. The tree lazy-loads children by parent id, indents by rank, renders `rank: Name Authorship • N spp.` rows, and exposes `Source` + `Extant only` filters. The explored path flows through the `cascadePath` Zustand store and a `path:change` CustomEvent so the App's breadcrumb-links panel keeps working.

## Requirements

### Requirement: Lazy Expand Caches by parent_id

The system SHALL fetch children of a parent taxon exactly once per `parent_id` and cache for the session.

#### Scenario: First expand fetches
- GIVEN a parent taxon has not been expanded
- WHEN the user clicks its caret
- THEN the system issues `GET /api/tree/children?parent_id={id}` and populates the row

#### Scenario: Re-expand reads cache
- GIVEN the parent has been expanded
- WHEN the user collapses and re-expands
- THEN no new request fires and cached children render immediately

### Requirement: Caret Renders Per has_children

The system SHALL render `▸`/`▾` on rows with `has_children=true` and no caret on leaf rows.

#### Scenario: Leaf has no caret
- GIVEN a taxon has `has_children=false`
- THEN no caret glyph appears and the row is not keyboard-activatable for expansion

### Requirement: Row Format rank: Name Authorship • N spp.

The system SHALL render every row as `rank: Name Authorship • N spp.` where `Name` is the canonical `name`, `Authorship` is the citation tail split from `display_name`, and `N spp.` is the derived descendant count.

#### Scenario: Authorship splits from display_name
- GIVEN `name="Eukaryota"` and `display_name="Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978"`
- THEN the row reads `domain: Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978 • 2.4M spp.`

### Requirement: Indent by Tree Depth

The system SHALL indent every row by hierarchy depth in the explored tree, computed from tree state (not `display_level`).

#### Scenario: Roots at depth zero
- GIVEN the tree boots
- THEN every root row sits at depth zero

#### Scenario: Expanded child indents one level
- GIVEN a root row is expanded
- THEN every direct child sits at depth one

### Requirement: Root Rows Are parent_id IS NULL

The system SHALL treat rows with `parent_id IS NULL` as tree roots and MUST NOT synthesize a `Biota` superdomain root.

#### Scenario: Five CoL roots
- GIVEN the dataset contains 5 rows with `parent_id IS NULL`
- THEN exactly 5 root rows render and no synthesized `Biota` root is present

### Requirement: Extant Only Filter

The system SHALL expose an `Extant only` checkbox that hides rows where `is_extinct=true` when checked. Default is unchecked.

#### Scenario: Filter off keeps extinct
- GIVEN the checkbox is unchecked
- THEN rows with `is_extinct=true` are visible

#### Scenario: Filter on hides extinct
- GIVEN the checkbox is checked
- THEN every rendered row has `is_extinct=false`

### Requirement: Source Filter (No-op First PR)

The system SHALL expose a `Source` checkbox as a no-op (always-on CoL). No `source` query param is sent.

#### Scenario: Checkbox renders
- GIVEN the header mounts
- THEN a `Source` checkbox is visible and checked by default

#### Scenario: Toggle is a no-op
- WHEN the user toggles the checkbox
- THEN the tree does not refetch

### Requirement: Path Dispatch on Every Expand

The system SHALL write the explored path to the `cascadePath` Zustand store and dispatch a `path:change` CustomEvent with `{path: string[]}` on every expand.

#### Scenario: Store and event fire
- GIVEN the user expands a row
- THEN `useCascadePath.getState().path` equals the explored segments
- AND `window.dispatchEvent` fires `path:change` with `{path: [...]}`

### Requirement: Empty State

The system SHALL render "No taxonomy loaded" when the tree has zero root rows.

#### Scenario: No roots
- GIVEN no rows have `parent_id IS NULL`
- THEN "No taxonomy loaded" renders

### Requirement: Error State with Retry

The system SHALL render a retry affordance on a caret row when its children fetch fails. Other rows MUST remain expanded.

#### Scenario: Retry on failure
- GIVEN a caret row's fetch returns 5xx or network error
- THEN the row shows a "Retry" button that reissues the same request on click

### Requirement: Keyboard Navigation and ARIA

The system SHALL make rows keyboard-navigable (Enter toggles caret, ArrowDown/Up move focus) and SHALL expose `aria-level` (indent depth) and `aria-expanded` (caret state).

#### Scenario: Enter toggles caret
- GIVEN a row has focus
- WHEN the user presses Enter
- THEN the caret toggles and `aria-expanded` reflects the new state

## Out of Scope

- `Source` filter backend wiring (no-op first PR; multi-source in follow-up).
- Cross-reload persistence of expanded tree state.

## Delta Applied

- `subtree.md` — adds the `next_tiers` subtree envelope to `GET /api/tree/children?parent_id={id}` (one `NextTier` per cascade bucket below the parent — phylum / class / order / family / genus / species — with per-tier recursive rows, per-tier cursor pagination, and cascade-rank ordering). Applied by PR A.1 of the `tree-deep-subtree` change (issue #76).
- The species list panel — the tree reaches a genus and delegates to the existing species fetch.