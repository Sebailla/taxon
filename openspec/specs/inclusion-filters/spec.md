# inclusion-filters Specification

## Purpose
Defines the toggle filters that the UI exposes for extinct, synonyms, uncertain, and unassigned taxa, and the rule that the default behavior returns accepted taxa only. The data store retains every taxon, so toggling filters only changes what the response includes — it does not change the persisted state of the data.

## Requirements

### Requirement: Toggle Filters per Inclusion Class

The system SHALL expose one toggle per inclusion class — `extinct`, `synonyms`, `uncertain`, `unassigned` — so the user can independently decide whether to include each class in the species list.

#### Scenario: Four toggles are exposed
- GIVEN the filter panel is rendered
- WHEN the panel is displayed
- THEN exactly four toggles appear: `extinct`, `synonyms`, `uncertain`, `unassigned`
- AND each toggle defaults to off

#### Scenario: Toggle widens result set
- GIVEN the default state is accepted-only
- WHEN a user enables the `extinct` toggle and re-queries
- THEN extinct species are added to the response
- AND accepted species remain present

#### Scenario: Toggle narrows result set
- GIVEN the `synonyms` toggle is enabled
- WHEN the user disables it and re-queries
- THEN synonym species are removed from the response
- AND the response reverts to accepted-only

### Requirement: Default State is Accepted-Only

The system SHALL default every toggle to off so that an unspecified request returns only accepted taxa. The default applies when the request carries no `include` parameter or an empty value.

#### Scenario: No include parameter
- GIVEN the client sends a request without an `include` parameter
- WHEN the species list is computed
- THEN only accepted species are returned
- AND no extinct, synonym, uncertain, or unassigned taxa are returned

#### Scenario: Empty include parameter
- GIVEN the client sends `include=` (empty value)
- WHEN the species list is computed
- THEN only accepted species are returned
- AND the response is identical to the no-parameter request

#### Scenario: Default applies on every endpoint
- GIVEN the `species-list-by-genus` and `species-lookup` endpoints both consume the filter
- WHEN either endpoint is called without an explicit `include`
- THEN both return accepted-only results

### Requirement: Filters Compose with OR Semantics

The system SHALL treat multiple enabled toggles as a union: enabling `extinct` and `synonyms` returns both extinct taxa and synonyms, alongside accepted taxa. The combination logic MUST be OR, never AND.

#### Scenario: Two toggles union
- GIVEN the `extinct` and `synonyms` toggles are both enabled
- WHEN the species list is computed
- THEN the response contains accepted, extinct, and synonym species
- AND it does NOT contain only the intersection

#### Scenario: All four toggles enabled
- GIVEN every toggle is enabled
- WHEN the species list is computed
- THEN the response contains every taxon attached to the Genus regardless of class
- AND no taxon is silently excluded due to filter logic

#### Scenario: Filter state does not mutate data
- GIVEN a request enables the `extinct` toggle
- WHEN the response is returned
- THEN the persisted dataset is unchanged
- AND subsequent requests without the toggle see the same accepted-only behavior

### Requirement: Filters Are Read-Only

The system SHALL treat inclusion filters as a read-only projection over the persisted data. There SHALL be no write endpoint that mutates a taxon's class for the purpose of filtering.

#### Scenario: No write path exists
- GIVEN the API is fully described
- WHEN the client lists available operations
- THEN no endpoint accepts a payload that toggles a taxon's extinct, synonym, uncertain, or unassigned state
- AND no endpoint mutates the canonical name used for lookups

#### Scenario: Filter toggles are per-request
- GIVEN one client toggles `extinct` on
- WHEN another client queries without the toggle
- THEN the second client still sees accepted-only
- AND the first client's state has not leaked