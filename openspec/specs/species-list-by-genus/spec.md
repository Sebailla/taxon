# species-list-by-genus Specification

## Purpose
Defines the 6th list of the cascade: the species attached to a Genus. This capability is the fixed scrollable list that updates once a Genus is chosen, and it is the entry point for the species lookup and search-links flows.

## Requirements

### Requirement: List Species for a Genus

The system SHALL return all species attached to a given Genus, each with a stable identifier, a canonical searchable name, a verbatim display label, and marker flags that describe its status in the dataset.

#### Scenario: Default accepted-only listing
- GIVEN a Genus has both accepted species and synonyms
- WHEN a client requests the species list without filter parameters
- THEN only accepted species are returned
- AND synonyms are excluded

#### Scenario: Response shape per species
- GIVEN a species is returned in the list
- WHEN the client parses the response
- THEN the item contains `id`, `canonical_name`, `display_name`, and `markers`
- AND `markers` is an object with boolean keys `is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`

#### Scenario: Empty genus
- GIVEN a Genus exists but has no species attached
- WHEN a client requests the species list for that Genus
- THEN the response is an empty JSON array
- AND HTTP status is 200

### Requirement: Include Filters Widen the Result Set

The system SHALL accept an `include` query parameter whose values select additional inclusion classes; absent or empty `include` keeps the default accepted-only result.

#### Scenario: Include synonyms only
- GIVEN a Genus has accepted species and synonyms
- WHEN a client requests the species list with `include=synonyms`
- THEN accepted species are still returned
- AND synonyms are additionally returned

#### Scenario: Combine multiple include classes
- GIVEN a Genus has accepted, synonym, and extinct species
- WHEN a client requests the species list with `include=synonyms,extinct`
- THEN all three classes are returned
- AND unknown values in `include` are ignored without error

#### Scenario: Unknown include values are tolerated
- GIVEN a client supplies an `include` value that is not a recognized class
- WHEN the request is processed
- THEN the unrecognized value is ignored
- AND the response is still 200 with the default accepted-only set

### Requirement: Pagination Cap

The system SHALL cap any single species-list response to a maximum of 500 items so that no single request can return an unbounded payload.

#### Scenario: Under cap
- GIVEN a Genus has fewer than 500 species
- WHEN a client requests the list
- THEN all species are returned in a single response
- AND no pagination metadata is required

#### Scenario: Over cap
- GIVEN a Genus has more than 500 species
- WHEN a client requests the list
- THEN the response contains at most 500 items
- AND the response includes a `next_cursor` token when more results exist
- AND no item beyond the cap is included in the same response

#### Scenario: Cursor advances
- GIVEN a previous response returned a `next_cursor`
- WHEN a client requests the next page passing that cursor
- THEN the response returns the next batch of up to 500 items
- AND the order of items across pages is deterministic