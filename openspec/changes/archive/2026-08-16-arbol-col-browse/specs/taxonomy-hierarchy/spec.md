# Delta for taxonomy-hierarchy

## MODIFIED Requirements

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