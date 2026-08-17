# taxonomy-hierarchy Specification

## Purpose
Defines how the taxonomy cascade (Kingdom → Phylum → Class → Order → Family → Genus) is exposed to clients. Identifiers are path-name URL-encoded names so that any link reflects the breadcrumb a user has walked. This capability is the spine that the other capabilities depend on.

## Requirements

### Requirement: Hierarchy Browse by Path

The system SHALL expose a path-name URL-encoded route per cascade level so a client can navigate from Kingdom down to Genus by appending one path segment per rank. The path-resolver endpoints (`/{path:path}/taxon-links` and `/api/path-children?path=…`) MUST stay verbatim so the breadcrumb-links panel and species dispatch keep working.
(Previously: the capability only exposed path-name endpoints; the tree adds parent-id addressing alongside them.)

#### Scenario: List children of a Kingdom
- GIVEN a Kingdom exists
- WHEN a client requests the Phyla for that Kingdom by path-name
- THEN the response is a JSON array of children sorted alphabetically by `name`
- AND each item includes `id`, `name`, `display_name`

#### Scenario: List children at any rank
- GIVEN a parent taxon exists at any canonical rank
- WHEN a client requests children at the next rank down
- THEN the response returns only direct children of that parent (empty when none)

#### Scenario: 404 when ancestor name is unknown
- GIVEN a path segment matches no taxon name
- WHEN a client requests a path containing that segment
- THEN the system returns HTTP 404 with a body that names the failing segment

### Requirement: Path-Name Identifier Semantics

The system SHALL match path-name segments case-insensitively against the canonical name of each taxon while preserving the verbatim `display_name` (including author citations and status markers) in responses.

#### Scenario: Case-insensitive segment match
- GIVEN a Kingdom named "Animalia" exists in the dataset
- WHEN a client requests the path with the segment `animalia`
- THEN the system resolves it to the same Kingdom as `Animalia`
- AND returns the same children

#### Scenario: Verbatim display preservation
- GIVEN a taxon whose canonical name has been normalized but whose source label retains author citations
- WHEN a client requests any descendant path of that taxon
- THEN the response field `display_name` MUST equal the source label exactly as captured

#### Scenario: Ambiguous path segment rejected
- GIVEN a path segment resolves to multiple distinct taxa with the same name under different parents
- WHEN a client requests a path using that bare segment
- THEN the system returns HTTP 409
- AND the response body lists the candidate breadcrumb paths so the client can disambiguate

### Requirement: Stable Response Shape and Ordering

The system SHALL return a stable JSON shape for every hierarchy endpoint and order children deterministically. The new tree endpoints extend `TaxonResponse` with `has_children`, `species_count`, and `authorship` and SHALL NOT mutate the canonical `TaxonResponse` shape.
(Previously: `TaxonResponse` carried `id`, `name`, `display_name`, `rank`, `parent_id`, marker flags. The tree endpoints add three derived fields.)

#### Scenario: Deterministic ordering
- GIVEN a parent has children A, B, C under the same rank
- WHEN the client issues the same request twice
- THEN both responses return children in the same alphabetical order by canonical `name`

#### Scenario: Schema stability
- GIVEN the hierarchy endpoint schema is published
- WHEN the client parses the response
- THEN every item contains exactly the keys `id`, `name`, `display_name`
- AND no unexpected keys appear without a documented version bump

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

### Requirement: Parent-id Children Endpoint

The system SHALL expose `GET /api/tree/children?parent_id={id}&limit={n}&cursor={c}` returning `{parent: TaxonResponse, children: list[TreeNodeResponse], next_cursor: str | None}`. `TreeNodeResponse` extends `TaxonResponse` with `has_children: bool`, `species_count: int | None`, and `authorship: str`.

#### Scenario: Children with derived fields
- GIVEN a parent taxon has direct children
- WHEN a client requests `/api/tree/children?parent_id=2`
- THEN the response is 200 with every child carrying `has_children`, `species_count`, `authorship`
- AND `next_cursor` is non-empty when `limit` is exceeded

#### Scenario: 404 on unknown parent
- GIVEN the supplied `parent_id` matches no taxon
- WHEN a client requests `/api/tree/children?parent_id=999999`
- THEN the system returns HTTP 404 with a body identifying the missing parent id

### Requirement: Tree Search Endpoint

The system SHALL expose `GET /api/tree/search?q={q}&limit=8` returning `{items: list[TreeNodeResponse]}` ranked exact match > prefix match > substring match. Ties SHALL break by `display_name` length ascending.

#### Scenario: Ranked results
- GIVEN the dataset has `Panthera` and `Panthera onca`
- WHEN the client requests `/api/tree/search?q=Panthera`
- THEN the response is 200 with `items[0].name === "Panthera"` and at most 8 entries

#### Scenario: Empty query returns empty list
- GIVEN `q` is empty or whitespace
- WHEN the client requests the endpoint
- THEN the response is 200 with `{"items": []}` and no SQL error

### Requirement: species_count Lazy Semantics

The system SHALL compute `species_count` as the descendant species count via a recursive CTE. For parents with more than 100,000 direct children, the system SHALL return `species_count: null` to keep the response under 100ms; the UI renders `—` in place of the count.

#### Scenario: Lazy null for huge nodes
- GIVEN a parent has more than 100,000 direct children
- WHEN the client requests the children
- THEN every child carries `species_count: null` and the request completes in under 100ms

#### Scenario: Aggregate fills for small nodes
- GIVEN a parent has fewer than 100,000 direct children
- WHEN the client requests the children
- THEN every child carries an integer `species_count` equal to the descendant count

### Requirement: Path-Resolver Endpoints Stay Verbatim

The system SHALL keep `/{path:path}/taxon-links` and `/api/path-children?path=…` unchanged so the breadcrumb-links panel and species dispatch flow keep working.

#### Scenario: Path-resolver returns 13 links
- GIVEN the user clicks a breadcrumb segment
- WHEN the App calls `/{path:path}/taxon-links`
- THEN the response is `TaxonLinksResponse{taxon, links}` with exactly 13 items substituted with the deepest taxon's canonical `name`

#### Scenario: Path-children returns next_tiers
- GIVEN the App needs cascade siblings at a path
- WHEN the path-children endpoint is called
- THEN the response is `PathChildrenEnvelope{parent, children, next_tiers}` with `next_tiers` grouping children by rank label