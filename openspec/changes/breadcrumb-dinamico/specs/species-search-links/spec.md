# Delta for species-search-links

## ADDED Requirements

### Requirement: Taxonomic Dispatch Endpoint Accepts Path Without Epithet

The system SHALL expose a dispatch endpoint that accepts a path of canonical names with no species epithet, resolves the deepest segment via the local hierarchy, and emits the same 13-link substitution as the species endpoint. The substitution target SHALL be the deepest resolved taxon's canonical `name`, never `display_name` nor the path string.

#### Scenario: Path of two segments yields 13 links for the deepest taxon

- GIVEN a path `["Animalia","Chordata"]` resolves to the phylum `Chordata`
- WHEN the client requests `GET /api/Animalia%7CChordata/taxon-links`
- THEN the response body contains a `links` array of exactly 13 items
- AND every substituted `{q}` equals `Chordata` URL-encoded
- AND the order matches the row order in `docs/sources/templates.md`

#### Scenario: Path of seven segments yields 13 links for the deepest genus

- GIVEN a path of seven segments ending in the genus `Panthera`
- WHEN the client requests the deepest genus's `taxon-links`
- THEN the response body contains a `links` array of exactly 13 items
- AND every substituted `{q}` equals `Panthera` URL-encoded

#### Scenario: Substitution uses canonical name, not display label

- GIVEN the deepest taxon has `name="Chordata"` and `display_name="Chordata Bateson, 1885"`
- WHEN the client requests the `taxon-links`
- THEN every substituted `{q}` equals `Chordata` URL-encoded
- AND the author citation from `display_name` does NOT appear in any `url`

#### Scenario: Substitution uses the deepest segment's name

- GIVEN the path is `["Animalia","Chordata","Vertebrata"]`
- WHEN the client requests the `taxon-links`
- THEN every substituted `{q}` equals `Vertebrata` URL-encoded
- AND `Animalia` and `Chordata` do NOT appear in any `url`

#### Scenario: Same shape as species-links endpoint

- GIVEN the species-links endpoint returns `LinksResponse{species,links}` with exactly 13 items
- WHEN the client requests the per-taxon dispatch endpoint
- THEN the response is `TaxonLinksResponse{taxon,links}` with exactly 13 items
- AND each item carries `source`, `label`, `url` mirroring `SearchLinkItem`