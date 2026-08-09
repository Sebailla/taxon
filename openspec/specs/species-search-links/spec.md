# species-search-links Specification

## Purpose
Defines the dispatch URLs emitted for each species so that a user can fan out to the same 12 search sources that the legacy spreadsheet encoded. The URLs MUST match the templates captured in `docs/sources/templates.md` verbatim to preserve sheet parity. Sci-hub dispatches to `https://sci-hub.ru/match/{q}` and substitutes the species like every other source.

## Requirements

### Requirement: Emit Exactly Twelve Links per Species

The system SHALL emit exactly 12 links per species, in the order defined in `docs/sources/templates.md`, and SHALL NOT add, remove, or reorder links between requests.

#### Scenario: Twelve ordered links
- GIVEN a species has been resolved unambiguously
- WHEN the client requests the species dispatch URLs
- THEN the response body contains a `links` array of exactly 12 items
- AND the order matches the row order in `docs/sources/templates.md`

#### Scenario: Stable order across requests
- GIVEN the same species is requested twice
- WHEN the two responses are compared
- THEN both `links` arrays are equal element by element
- AND no link is dropped, duplicated, or reordered

#### Scenario: Each link is fully populated
- GIVEN a link item is returned
- WHEN the client parses the item
- THEN the item contains exactly the keys `source`, `label`, and `url`
- AND `source` is one of the 12 names from the templates file
- AND `url` is a non-empty string

### Requirement: URL Substitution from Captured Templates

The system SHALL substitute `{q}` in every template with the URL-encoded species query using `urllib.parse.quote_plus(species, safe='')` so spaces become `+` and special characters are percent-encoded. The fixed portions of every template MUST appear verbatim.

#### Scenario: Substitution is URL-encoded
- GIVEN a species name contains a space such as `Genus species`
- WHEN the client requests the species dispatch URLs
- THEN every substituted `{q}` uses `+` in place of the space
- AND every other fixed query parameter in each template is preserved byte-for-byte

#### Scenario: Special characters are percent-encoded
- GIVEN a species name contains a non-alphanumeric character such as `(`, `)`, or `&`
- WHEN the client requests the species dispatch URLs
- THEN the special character is percent-encoded in every substituted `{q}`
- AND the surrounding template structure is unchanged

#### Scenario: Photos URL keeps tracking parameters
- GIVEN the Photos template contains fixed tracking parameters from cell M9
- WHEN the client requests the species dispatch URLs
- THEN the Photos URL includes every fixed parameter verbatim
- AND only the `{q}` segment is substituted

### Requirement: Sci-hub Substitutes the Species

The system SHALL emit the Sci-hub link using the template `https://sci-hub.ru/match/{q}` where `{q}` is substituted with the URL-encoded species query using `urllib.parse.quote_plus(species, safe='')` so spaces become `+` and special characters are percent-encoded. The host SHALL be `sci-hub.ru` and the path SHALL begin with `/match/`.

#### Scenario: Sci-hub URL substitutes the species
- GIVEN a species such as `Girardinichthys multiradiatus` has been resolved
- WHEN the client requests the dispatch URLs
- THEN the Sci-hub `url` equals `https://sci-hub.ru/match/Girardinichthys+multiradiatus`
- AND the species appears exactly once in the URL

#### Scenario: Sci-hub URL differs per species
- GIVEN two different species are resolved
- WHEN the client requests the dispatch URLs for each
- THEN the Sci-hub `url` values differ from each other
- AND each contains that species' URL-encoded name

#### Scenario: All twelve links substitute the species
- GIVEN a species has been resolved
- WHEN the client requests the dispatch URLs
- THEN all twelve links contain a substituted `{q}` segment
- AND no link is exempt from substitution