# species-lookup Specification

## Purpose
Defines how a `(genus, epithet)` pair resolves to a single species. Genus names repeat across different parents in the WoRMS dataset, so ambiguity is a known case that the system MUST surface rather than guess. The 409 response is the contract that lets the UI show a picker for the user to disambiguate.

## Requirements

### Requirement: Resolve a Unique Species

The system SHALL resolve a `(genus, epithet)` pair to a single species when exactly one accepted match exists in the dataset, returning its full record.

#### Scenario: Unambiguous resolution
- GIVEN a `(genus, epithet)` pair matches exactly one species in the dataset
- WHEN a client requests the species by path-name
- THEN the system returns HTTP 200
- AND the body contains the species `id`, `canonical_name`, `display_name`, `markers`, and the resolved breadcrumb

#### Scenario: Case-insensitive resolution
- GIVEN a species exists whose canonical names match `Genus` and `epithet`
- WHEN a client requests the path with mixed casing such as `GENUS`/`Epithet`
- THEN the system resolves to the same species
- AND returns the same response shape

### Requirement: Ambiguity Returns 409 with Candidates

The system SHALL return HTTP 409 Conflict when a `(genus, epithet)` pair resolves to more than one species under different parents, and the body MUST contain a `candidates[]` array so the client can present a disambiguation picker.

#### Scenario: Two parents collide
- GIVEN a `(genus, epithet)` pair is shared by two species under distinct parent breadcrumbs
- WHEN a client requests the species by path-name
- THEN the system returns HTTP 409
- AND the response body has a `candidates[]` array
- AND each candidate carries the full breadcrumb from Kingdom down to Genus plus `id`, `canonical_name`, and `display_name`

#### Scenario: Candidate order is stable
- GIVEN an ambiguous lookup yields a set of candidates
- WHEN the same request is issued again
- THEN the `candidates[]` array returns the same items in the same order
- AND the order is alphabetical by Kingdom then Phylum then Class then Order then Family then Genus

#### Scenario: Resolving after disambiguation
- GIVEN a 409 response returned two candidates with distinct IDs
- WHEN the client requests the species by its specific breadcrumb path
- THEN the system returns HTTP 200 for that exact species
- AND no second 409 is raised for the now fully qualified path

### Requirement: Not Found Returns 404

The system SHALL return HTTP 404 when the supplied `(genus, epithet)` pair does not correspond to any species in the dataset.

#### Scenario: Unknown epithet
- GIVEN the Genus exists but no species under it has the requested epithet
- WHEN a client requests the species by path-name
- THEN the system returns HTTP 404
- AND the response body identifies the missing epithet

#### Scenario: Unknown genus
- GIVEN the requested Genus does not exist in the dataset
- WHEN a client requests the species by path-name
- THEN the system returns HTTP 404
- AND the response body identifies the missing genus

#### Scenario: Distinguish 404 from 409
- GIVEN a request yields zero matches
- WHEN the client receives the response
- THEN the status code is 404 (not 409)
- AND 409 is reserved exclusively for the ambiguity case with at least two candidates