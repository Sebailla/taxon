# Delta: subtree-envelope

Pin the wire envelope for `GET /api/tree/children?parent_id={id}`: direct children + one `NextTier` per cascade bucket (realm → kingdom → phylum → class → order → family → genus → species), with per-tier recursive rows, per-tier cursor pagination, and cascade-rank ordering. Reuses the roll-up helpers in `taxon/api/sqlite_resolver.py` so the tree browse and the cascade share the same off-tuple visibility rules. (Previously: `TreeChildrenResponse` carried only direct children + top-level `next_cursor`; `next_tiers` is additive.)

## ADDED Requirements

### Requirement: TreeChildrenResponse Gains next_tiers

`GET /api/tree/children` SHALL return `{parent, children: list[TreeNodeResponse], next_tiers: list[TreeNodeTier] | None, next_cursor: str | None}`. `next_tiers` SHALL be `None` when the parent has no non-direct descendants. `TreeNodeTier` SHALL carry `{rank, label, examples, children: list[TreeNodeResponse], next_cursor: str | None}` where `rank` is the lower-cased cascade bucket, `label` is the human-readable tier name (e.g. `"Phyla"`), and `examples` is the first three canonical names. `children` (direct) stays the first positional field.

| Scenario | Given | When | Then |
|---|---|---|---|
| Animalia exposes four non-empty tiers | `parent_id=43342` (Animalia) | response parsed | `next_tiers.length >= 4`; phylum tier `children.length >= 30`; family `children.length >= 100`; genus + species tiers present |
| Leaf parent emits next_tiers: None | parent is a true leaf | client requests children | `next_tiers is None`; `children` is the direct descendant list |
| Empty tier is omitted | parent has direct children only at `phylum` | client requests children | exactly one `next_tiers` entry (`rank="phylum"`); no empty entries for other ranks |

### Requirement: Per-Tier Row Cap and Configurable Limit

Each `TreeNodeTier.children` SHALL be capped at `tier_limit` rows. Default `tier_limit` SHALL be `50`, max `200`. Clients SHALL control via `?tier_limit={n}`. The server SHALL clamp `tier_limit > 200` silently and reject negative values with HTTP 400.

| Scenario | Given | When | Then |
|---|---|---|---|
| Default cap is 50 | no `tier_limit` sent | server processes | every tier `children.length <= 50`; tiers exceeding 50 return `next_cursor` non-empty |
| Cap raised to 200 via param | `?tier_limit=200` | server processes | every tier `children.length <= 200`; SQL uses `LIMIT 200` per tier |
| Cap above 200 clamped | `?tier_limit=500` | server processes | silently clamped to `200`; no HTTP 400 |
| Negative tier_limit rejected | `?tier_limit=-1` | server processes | HTTP 400 with body identifying the invalid value |

### Requirement: Per-Tier Cursor Pagination Keyed (name, id)

Each tier SHALL paginate independently. Clients SHALL request the next page with `?tier={rank}&cursor={cursor}`. The cursor SHALL be opaque base64 of `f"{name}\x00{id}"`. The server SHALL skip rows whose `id` no longer matches the cursor's id (stale-id tolerance for re-imports).

| Scenario | Given | When | Then |
|---|---|---|---|
| Cursor round-trips the next page | family tier first page returns `next_cursor="X"`, `children.length == 50` | client requests `?tier=family&cursor=X` | next 50 rows returned; ordered strictly after cursor's `(name, id)` by lower-cased `name`, ties by `id` |
| Cursor returns None at the last page | family tier has 75 rows, `tier_limit=50` | client requests second page | `children.length == 25`; `next_cursor is None` |
| Cursor tolerates renumbered id | row's `name` unchanged but `id` renumbered | client presents stale cursor | server skips by `id` mismatch; resumes from cursor's `name` against new id sequence; no error |
| Tier pagination keeps other tiers intact | genus tier returns cursor | client requests `?tier=genus&cursor=…` | family tier rows unchanged; only genus advances |

### Requirement: Cascade-Rank Ordering and Off-Tuple Roll-up

`next_tiers` SHALL be ordered by `_DISPLAY_LEVELS_IN_ORDER` (`realm, kingdom, phylum, class, order, family, genus, species`). Off-tuple intermediates (subphylum, infraphylum, parvphylum, microphylum, megaclass → phylum bucket; subfamily, tribe, subtribe, infratribe → family bucket) SHALL collapse into their parent bucket via `_phylum_rollup` and `_family_rollup`. Rules SHALL match the cascade endpoint so `Archaea → Nanoarchaeota` surfaces at phylum and `Felidae → Pantherinae` at genus.

| Scenario | Given | When | Then |
|---|---|---|---|
| Tiers ordered by cascade rank | parent has descendants at phylum, class, order, family, genus, species | client requests children | `next_tiers[0].rank == "phylum"`; ranks in cascade order; realm tier only when parent is above kingdom |
| Phylum roll-up collapses intermediates | Chordata has children at `subphylum` and `class` | resolver applies `_phylum_rollup` | subphylum descended to `class`; class tier includes direct + rolled-up; no separate subphylum tier |
| Family roll-up collapses intermediates | Felidae has children at `subfamily`, `tribe`, `genus` | resolver applies `_family_rollup` | subfamily/tribe descended to `genus`; genus tier includes direct + rolled-up; no separate subfamily/tribe tiers |
| Archaea surfaces Nanoarchaeota at phylum tier | Archaea has direct child Nanoarchaeota at `phylum` | client requests children | phylum tier includes Nanoarchaeota; no separate kingdom tier |

### Requirement: Per-Tier Recursive CTE max_depth=8

Each tier SHALL be fetched via a recursive CTE scoped to that tier's rank bucket with `max_depth=8`:

```sql
WITH RECURSIVE descendants(id, depth) AS (
    SELECT child_id, 0 FROM taxa WHERE parent_id = :pid AND rank IN :tier_ranks
    UNION ALL
    SELECT t.id, d.depth + 1 FROM taxa t JOIN descendants d ON t.parent_id = d.id
    WHERE d.depth < :max_depth
)
SELECT … FROM taxa t JOIN descendants d ON t.id = d.id ORDER BY LOWER(t.name), t.name LIMIT :tier_limit;
```

`:tier_ranks` SHALL be the lower-cased rank set for the current bucket so the working set is bounded per cascade bucket. `:max_depth` SHALL be `8` on the first iteration.

| Scenario | Given | When | Then |
|---|---|---|---|
| Per-tier CTE bounds the working set | phylum-tier request against Animalia (~70 classes) | CTE runs | traverses at most 8 cascade hops; completes < 50ms p95 against `data/col.db` |
| rank IN filters the working set | class-tier request against a parent with subspecies/variety/form rows | CTE runs with `rank IN ("class",)` | does not enumerate subspecies/variety/form; returns only `class`-rank rows |
| Depth cap protects against pathological hierarchies | descendants form a chain deeper than 8 cascade hops | CTE runs with `max_depth=8` | terminates at depth 8; `WARNING` logged server-side; wire envelope does not surface the banner |

### Requirement: Tier Children Carry TreeNodeResponse Fields

Each `TreeNodeTier.children` row SHALL be a full `TreeNodeResponse` (`has_children`, `species_count`, `authorship` plus inherited `TaxonResponse` fields). The `species_count` lazy-null threshold (100,000 direct children) from `taxonomic-tree-browse` SHALL apply to tier rows. `authorship` SHALL be split from `display_name` as in direct-children payload.

| Scenario | Given | When | Then |
|---|---|---|---|
| Tier row carries derived fields | tier row for `Felidae` with `display_name="Felidae Waldheim, 1817"` | client parses tier payload | row carries `has_children`, `species_count` (int or null), `authorship`; `display_name` matches source label verbatim |
| Lazy null applies to tier rows | tier parent has > 100,000 direct descendants | tier query runs | every row carries `species_count: null`; response renders within existing 100ms budget per tier |