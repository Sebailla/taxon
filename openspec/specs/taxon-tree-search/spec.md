# Capability: taxon-tree-search

## Purpose

A "Find taxon" autocomplete in the tree header lets the user jump to any taxon by name. The search hits `GET /api/tree/search?q={q}` with a 200ms debounce and a hard cap of 8 results. Ranking is exact match > prefix match > substring match so the most relevant hit sits at the top.

## Requirements

### Requirement: Search Input in Tree Header

The system SHALL expose a single text input labelled `Find taxon` in the tree header.

#### Scenario: Input renders
- GIVEN the tree header mounts
- THEN an `<input>` with `aria-label="Find taxon"` renders
- AND no other search input exists in the tree view

### Requirement: Debounce Keystrokes at 200ms

The system SHALL debounce every input change at 200ms; rapid keystrokes collapse into a single request.

#### Scenario: Rapid keystrokes collapse
- GIVEN the user types `E`, `u`, `k` within 100ms each
- WHEN the 200ms window closes after the last keystroke
- THEN exactly one `GET /api/tree/search?q=Euk` request fires

#### Scenario: Pause triggers separate requests
- GIVEN the user types `E`, pauses 300ms, then types `u`
- THEN two requests fire: `q=E` and `q=Eu`

### Requirement: Backend Contract

The system SHALL call `GET /api/tree/search?q={q}&limit=8` and decode the response as `{items: TreeNodeResponse[]}`.

#### Scenario: Decoded response
- GIVEN the backend returns `{"items": [{"id": 1, "name": "Eukaryota", ...}]}`
- THEN `items.length === 1`
- AND each item has `id`, `name`, `display_name`, `rank`, `parent_id`

### Requirement: Ranked Relevance

The system SHALL rank results exact match > prefix match > substring match. Ties SHALL break by `display_name` length ascending.

#### Scenario: Exact match wins
- GIVEN the dataset has `Panthera` (genus) and `Panthera onca` (species)
- WHEN the user types `Panthera`
- THEN `Panthera` is the first item
- AND `Panthera onca` is the second

#### Scenario: Prefix beats substring
- GIVEN the dataset has `Eukarya` and `Pseudeukarya`
- WHEN the user types `Euk`
- THEN `Eukarya` is the first item
- AND `Pseudeukarya` is absent

### Requirement: Empty and No-Results State

The system SHALL show no dropdown when `q` is empty and SHALL show `No matches for "<q>"` when the response has zero items.

#### Scenario: Empty input hides dropdown
- GIVEN the input is cleared
- THEN no dropdown renders
- AND no request fires

#### Scenario: Zero-result dropdown
- GIVEN the user types `Zzzqxx`
- WHEN the response returns `{"items": []}`
- THEN the dropdown renders `No matches for "Zzzqxx"`

### Requirement: Performance Target

The system SHALL keep `GET /api/tree/search?q={q}` p95 latency under 200ms against `data/col.db`.

#### Scenario: Sub-200ms p95
- GIVEN 100 sequential searches with mixed queries
- WHEN p95 is computed
- THEN p95 ≤ 200ms

### Requirement: Selection Navigates to the Node

The system SHALL navigate to a result on click or Enter: expand the tree path to that node, scroll it into view, and move focus to it.

#### Scenario: Click selects and navigates
- GIVEN the dropdown shows results
- WHEN the user clicks the first
- THEN every ancestor expands
- AND the chosen row scrolls into view
- AND focus moves to the chosen row

#### Scenario: Enter key selects
- GIVEN the dropdown has focus
- WHEN the user presses Enter
- THEN the focused result is selected
- AND navigation matches the click scenario