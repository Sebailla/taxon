# Delta for taxonomy-hierarchy

## ADDED Requirements

### Requirement: Biota as root tier

The system SHALL expose a root tier above Kingdom consisting of exactly two options: `Biota` (id `"5T6MX"`) and `Viruses` (id `"V"`). Picking `Biota` reveals the seven kingdoms under it in the next dropdown; picking `Viruses` reveals the virus realms. The root endpoint SHALL return rows with `rank="root"` (or `rank="biota"`) and `next_rank_hint` of `"kingdom"` for `Biota` or `"viruses"` for `Viruses`.

#### Scenario: Root dropdown shows Biota and Viruses

- GIVEN a client requests `GET /api/kingdoms` (or `GET /api/roots`)
- WHEN the resolver queries ChecklistBank `COL2024`
- THEN the response contains exactly two items: `{id:"5T6MX", name:"Biota", display_name:"Biota"}` and `{id:"V", name:"Viruses", display_name:"Viruses"}`
- AND each item carries `rank="root"` and the appropriate `next_rank_hint`

#### Scenario: Picking Biota reveals the seven kingdoms

- GIVEN a client picks `Biota` in the cascade UI
- WHEN the next call asks for children at the kingdom tier
- THEN the resolver walks `/dataset/COL2024/tree/5T6MX/children` and returns the seven kingdoms (Animalia, Archaea, Bacteria, Chromista, Fungi, Plantae, Protozoa)

### Requirement: Subphylum tier visibility rule

The system SHALL render a `subphylum` tier only when the parent Phylum has subphylum children. When a Phylum has zero subphylum children (e.g. Arthropoda), the resolver MUST collapse the tier and return the Class children directly with `next_rank_hint="order"`. When a Phylum has subphylum children (e.g. Chordata), the resolver MUST return them at `rank="subphylum"` and `next_rank_hint="class"`.

#### Scenario: Chordata exposes its three subphyla

- GIVEN the parent path resolves to `Chordata` (id `"CH2"`)
- WHEN the cascade UI requests the next tier
- THEN the resolver queries `/dataset/COL2024/tree/CH2/children` and returns three subphyla: Cephalochordata, Tunicata, Vertebrata
- AND each item carries `rank="subphylum"` and `next_rank_hint="class"`

#### Scenario: Arthropoda skips subphylum and returns classes directly

- GIVEN the parent path resolves to `Arthropoda`
- WHEN the cascade UI requests the next tier
- THEN the resolver detects zero subphylum children and queries `/dataset/COL2024/tree/{arthropoda_id}/children?rank=class` directly
- AND the response contains Insecta, Crustacea, Arachnida (and other classes) with `rank="class"` and `next_rank_hint="order"`
- AND no subphylum row is emitted (the tier is collapsed)

### Requirement: Dataset key pinning

The system SHALL pin the ChecklistBank dataset to key `"COL2024"` for every request. The client SHALL accept a `dataset_key` parameter that defaults to `"COL2024"`. Pinning `COL2024` produces deterministic, reproducible taxon IDs. The `3LR` magic key SHALL NOT be used in v1; it SHALL be documented in code comments only as the future upgrade path.

#### Scenario: Default dataset key is COL2024

- GIVEN a client omits the `dataset_key` parameter
- WHEN the resolver issues a request to ChecklistBank
- THEN every URL targets `/dataset/COL2024/...` and the response IDs are stable across runs

#### Scenario: 3LR is documented but not used

- GIVEN a reviewer reads `taxon/checklistbank.py`
- WHEN they search for `3LR`
- THEN the literal appears only inside a code comment near `DATASET_KEY = "COL2024"`
- AND no request URL contains `3LR`

### Requirement: Compound taxon identifier

The system SHALL identify every taxon in the cascade with a compound key consisting of `taxon_id` (the opaque ChecklistBank string ID, e.g. `"N"`, `"CH2"`, `"RT"`) and `dataset_key` (always `"COL2024"` in v1). The previous GBIF integer `nub_key` SHALL NOT appear in the public contract.

#### Scenario: Each taxon row carries taxon_id and dataset_key

- GIVEN a parent path resolves to a clade in `COL2024`
- WHEN the cascade UI receives the children list
- THEN each item exposes `id` equal to the opaque CLB string ID (e.g. `"N"` for Animalia, `"CH2"` for Chordata)
- AND the response envelope exposes `dataset_key: "COL2024"`
- AND the response does NOT contain any integer `nub_key` or `key` field

## MODIFIED Requirements

### Requirement: Hierarchy Browse by Path

The system SHALL expose a path-name URL-encoded route per cascade level so that a client can navigate the taxonomy from the `Biota` root tier down to a Genus, with optional `subphylum` as an intermediate tier. The full effective tier set is `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` (nine tiers). The `subphylum` tier appears only when the parent Phylum has subphylum children; otherwise the path skips it.
(Previously: tier set was `(kingdom, phylum, class, order, family, genus, species)` (seven tiers) with no root or subphylum tier.)

#### Scenario: Animalia resolves to its 34 phyla

- GIVEN the parent path resolves to `Animalia`
- WHEN the cascade UI picks Animalia
- THEN the next dropdown shows Chordata, Arthropoda, Cnidaria, … (all 34 phyla)
- AND each item carries `rank="phylum"` and `next_rank_hint` reflecting subphylum presence

#### Scenario: Felidae reveals Panthera as a genus

- GIVEN the path `Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae`
- WHEN the cascade UI picks Felidae
- THEN Panthera appears as a genus
- AND the response carries `next_rank_hint="species"`

#### Scenario: Subphylum is optional on the path

- GIVEN the parent path resolves to `Arthropoda`
- WHEN the cascade UI requests the next tier
- THEN the response carries `next_rank_hint="class"` (subphylum tier collapsed)
- AND the next request at `Animalia|Arthropoda|Insecta` returns the orders under Insecta

### Requirement: Path-Name Identifier Semantics

The system SHALL match path-name segments case-insensitively against the canonical name of each taxon while preserving the verbatim `display_name` (including author citations and status markers) in responses. The path MAY contain 6 or 7 segments depending on whether the lineage crosses a subphylum (e.g. `Chordata|Vertebrata|Mammalia` is three segments including subphylum; `Arthropoda|Insecta|Lepidoptera` is three segments skipping subphylum).
(Previously: paths were always exactly seven segments, one per rank from Kingdom to Species.)

#### Scenario: Chordata lineage uses 7 segments to reach Panthera

- GIVEN the path `Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera` (7 segments including subphylum)
- WHEN the cascade UI resolves it
- THEN the resolver walks Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera via `/dataset/COL2024/tree/{id}/children`
- AND returns the 12 Panthera species at the leaf

#### Scenario: Arthropoda lineage uses 6 segments to reach Bombyx

- GIVEN the path `Animalia|Arthropoda|Insecta|Lepidoptera|Bombycidae|Bombyx` (6 segments, subphylum skipped)
- WHEN the cascade UI resolves it
- THEN the resolver walks Arthropoda → Insecta → Lepidoptera → Bombycidae → Bombyx and returns the species
- AND the resolver never inserted a subphylum segment for Arthropoda

#### Scenario: Missing path parameter returns 400

- GIVEN a request omits the `path` query parameter
- WHEN the client calls `GET /api/path-children`
- THEN the response is HTTP 400
- AND the response body contains a `missing path` error explaining the required parameter

## REMOVED Requirements

### Requirement: GBIF Eight-Kingdom Root

(Reason: the cascade no longer sources from the GBIF Species API; the previous behavior where `/api/kingdoms` returned eight kingdoms directly is replaced by the Biota + Viruses root dropdown from ChecklistBank `COL2024`. The GBIF integer `nub_key` field is also removed from the public contract.)
(Migration: clients consuming `/api/kingdoms` SHOULD treat the response as the root tier (Biota + Viruses) and request the next dropdown to discover kingdoms. Any client that hard-codes eight kingdoms or expects a `nub_key` MUST be updated to use the compound `taxon_id` + `dataset_key` identifier instead.)