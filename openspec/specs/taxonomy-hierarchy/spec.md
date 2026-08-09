# taxonomy-hierarchy Specification

## Purpose
Defines how the taxonomy cascade (Kingdom → Phylum → Class → Order → Family → Genus) is exposed to clients. Identifiers are path-name URL-encoded names so that any link reflects the breadcrumb a user has walked. This capability is the spine that the other capabilities depend on.

## Requirements

### Requirement: Hierarchy Browse by Path

The system SHALL expose a path-name URL-encoded route per cascade level so that a client can navigate the taxonomy from a Kingdom all the way down to a Genus by appending one path segment per rank.

#### Scenario: List children of a Kingdom
- GIVEN a Kingdom exists in the dataset
- WHEN a client requests the Phyla for that Kingdom by path-name
- THEN the response is a JSON array of children
- AND each item includes `id`, `name`, `display_name`
- AND items are sorted alphabetically by `name`

#### Scenario: List children at any rank
- GIVEN a parent taxon exists at any canonical rank
- WHEN a client requests the children at the next rank down
- THEN the response returns only direct children of that parent
- AND the result is empty when the parent has no children at that rank

#### Scenario: 404 when ancestor name is unknown
- GIVEN a segment in the path does not match any taxon name in the dataset
- WHEN a client requests a path containing that segment
- THEN the system returns HTTP 404
- AND the response body explains which segment was not found

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

The system SHALL return a stable JSON shape for every hierarchy endpoint and SHALL order children deterministically so that two equivalent requests always produce the same response bytes.

#### Scenario: Deterministic ordering
- GIVEN a parent taxon has children A, B, C under the same rank
- WHEN the client issues the same request twice
- THEN both responses return children in the same order
- AND the order is alphabetical by canonical `name`

#### Scenario: Schema stability
- GIVEN the hierarchy endpoint schema is published
- WHEN the client parses the response
- THEN every item contains exactly the keys `id`, `name`, `display_name`
- AND no unexpected keys are introduced between releases without a documented version bump