# Taxon Breadcrumb Links Specification

## Purpose

Per-taxon dispatch envelope used by the cascade breadcrumb. Clicking any breadcrumb segment mid-cascade or after resolution fetches the same 13-link substitution the species row produces, but for that taxon's name. The endpoint walks a path of 1–7 canonical names against the local hierarchy, returns the deepest resolved taxon plus the 13 substituted URLs, and the UI reuses `SpeciesLinks` to render the result.

## Requirements

### Requirement: Resolve Path With One to Seven Segments

The system SHALL accept any path of 1–7 canonical names (no epithet, no trailing `/links`) and resolve the deepest segment via `resolve_path_by_display_level`. The response SHALL be `TaxonLinksResponse` with `taxon` (deepest resolved row) and `links` (the 13 substituted URLs). The deepest segment MAY sit at any rank from kingdom through genus; an eighth or later segment SHALL yield 404.

#### Scenario: Two-segment path resolves phylum

- GIVEN the path `["Animalia","Chordata"]`
- WHEN the client requests `GET /api/Animalia%7CChordata/taxon-links`
- THEN `taxon.name` equals `"Chordata"` and `taxon.rank` equals `"phylum"`
- AND `links` has exactly 13 items

#### Scenario: Seven-segment path resolves genus

- GIVEN a 7-segment path ending in `Panthera`
- WHEN the client requests that path's `taxon-links`
- THEN `taxon.name` equals `"Panthera"` and `taxon.rank` equals `"genus"`
- AND `links` has exactly 13 items

#### Scenario: One-segment path resolves kingdom

- GIVEN the path `["Animalia"]`
- WHEN the client requests the kingdom's `taxon-links`
- THEN `taxon.name` equals `"Animalia"` and `taxon.rank` equals `"kingdom"`
- AND `links` has exactly 13 items

### Requirement: Substitute the Deepest Taxon's Name

The system SHALL substitute `{q}` in every template with `urllib.parse.quote_plus(taxon.name, safe='')` so spaces become `+` and special characters are percent-encoded. The substitution target SHALL be the deepest resolved taxon's canonical `name`, never `display_name` nor the path string. The substitution SHALL reuse `build_search_links` exactly as the species-links endpoint does.

#### Scenario: Phylum name substitutes URLs

- GIVEN the path resolves to the phylum `Chordata`
- WHEN the client requests the `taxon-links`
- THEN every substituted `{q}` equals `Chordata` URL-encoded
- AND the fixed portions of each template appear verbatim vs `docs/sources/templates.md`

#### Scenario: Genus name substitutes URLs

- GIVEN the path resolves to the genus `Panthera`
- WHEN the client requests the `taxon-links`
- THEN every substituted `{q}` equals `Panthera` URL-encoded
- AND no link is exempt from substitution

### Requirement: Emit Exactly Thirteen Links Per Taxon

The system SHALL emit exactly 13 links per taxon in the order defined in `docs/sources/templates.md`, and SHALL NOT add, remove, or reorder links between requests. Each item SHALL contain exactly `source`, `label`, `url` mirroring `SearchLinkItem`. `source` SHALL be one of the 13 template names; `url` SHALL be a non-empty string with substitution applied.

#### Scenario: Twelve ordered links for a kingdom

- GIVEN the path resolves to `Animalia`
- WHEN the client requests the kingdom's `taxon-links`
- THEN `links` has exactly 13 items
- AND the order matches the row order in `docs/sources/templates.md`

#### Scenario: Stable order across requests

- GIVEN the same path is requested twice
- WHEN the two responses are compared
- THEN both `links` arrays are equal element by element
- AND no link is dropped, duplicated, or reordered

### Requirement: 404 on Unresolvable or Oversized Path

The system SHALL return HTTP 404 when any segment fails to resolve or the path exceeds seven segments. The 404 detail SHALL name the failing segment or the cap violation. A 404 on `taxon-links` SHALL NOT affect the species `/links` endpoint.

#### Scenario: Unknown kingdom returns 404

- GIVEN `"Atlantis"` does not exist
- WHEN the client requests `GET /api/Atlantis/taxon-links`
- THEN the system returns HTTP 404
- AND the response body names `"Atlantis"`

#### Scenario: Valid prefix, bad last segment

- GIVEN `Animalia` exists but `BadPhylum` does not
- WHEN the client requests `GET /api/Animalia%7CBadPhylum/taxon-links`
- THEN the system returns HTTP 404
- AND the response body names `"BadPhylum"`

#### Scenario: Eight or more segments rejected

- GIVEN a path with eight or more non-empty segments
- WHEN the client requests the `taxon-links`
- THEN the system returns HTTP 404
- AND the response body explains the seven-segment cap