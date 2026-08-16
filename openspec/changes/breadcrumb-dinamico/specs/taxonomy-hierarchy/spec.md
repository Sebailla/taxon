# Delta for taxonomy-hierarchy

## ADDED Requirements

### Requirement: Permanent Breadcrumb Exposes the Cascade Path

The system SHALL expose the cascade path as a permanent breadcrumb whenever the user has picked at least one segment, regardless of whether a species has been resolved. The breadcrumb SHALL render one segment per picked rank from Biota (or the chosen superdomain) down to the deepest picked rank, in the order the user picked them. Each segment SHALL be visually distinguishable as a clickable element.

#### Scenario: Breadcrumb renders mid-cascade without a species

- GIVEN the user has picked `Biota` and `Animalia` from the cascade
- WHEN no species has been resolved
- THEN the breadcrumb renders two segments
- AND each segment is a clickable element

#### Scenario: Breadcrumb reflects the deepest picked segment

- GIVEN the user has picked a path of three segments ending in `Chordata`
- WHEN the breadcrumb renders
- THEN the breadcrumb shows three segments in order
- AND the last segment is `Chordata`

#### Scenario: Breadcrumb updates as picks change

- GIVEN the user changes a parent pick after building a path
- WHEN the breadcrumb re-renders
- THEN the breadcrumb reflects the new path
- AND stale segments from the old path do NOT appear

### Requirement: Clickable Breadcrumb Segment Fetches Per-Taxon Dispatch

The system SHALL treat each breadcrumb segment as a clickable control that, when activated, fetches the per-taxon dispatch endpoint for that segment's path and renders the resulting 13-link substitution in the existing links panel. Activation SHALL NOT clear or replace a previously-rendered species-links grid unless that grid was superseded by a new species resolution.

#### Scenario: Clicking a segment opens the per-taxon grid

- GIVEN the breadcrumb shows a path of three segments
- WHEN the user clicks the second segment
- THEN the system fetches the per-taxon dispatch endpoint for that segment's path
- AND the links panel renders the 13 substituted URLs for that taxon's name

#### Scenario: Per-taxon grid uses the clicked taxon's name

- GIVEN the user clicks the segment `Chordata`
- WHEN the per-taxon dispatch endpoint responds
- THEN every substituted `{q}` equals `Chordata` URL-encoded
- AND the species-links panel does NOT show a species name

#### Scenario: Species-links grid survives breadcrumb click

- GIVEN a species-links grid is already rendered for a resolved species
- WHEN the user clicks any breadcrumb segment
- THEN the per-taxon grid renders alongside the species-links grid
- AND the last-clicked panel wins as the primary visible grid

#### Scenario: Each segment is keyboard-activatable

- GIVEN the breadcrumb is rendered
- WHEN the user tabs to a segment and presses Enter or Space
- THEN the per-taxon dispatch endpoint fetches for that segment's path
- AND the links panel renders the resulting 13 substituted URLs