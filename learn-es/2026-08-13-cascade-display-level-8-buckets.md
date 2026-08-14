# Cascade 8 display_level buckets (PR #31)

## What

The Cascade UI now renders up to 8 dropdowns (realm → kingdom → phylum → class → order → family → genus → species). CoL publishes 40+ ranks with intermediate tiers (subphylum, infraphylum, megaclass, subclass, superorder, parvorder, infraorder, ...) that the previous six-fixed-rank ladder skipped. The path-aware resolver handled them at the API level but the UI still showed heterogeneous label noise ("subphylum" vs "infraphylum" vs "megaclass" all collapse into the same logical bucket).

This change introduces a single source of truth — `taxon.taxonomy` — for the cascade buckets. The `Taxon` table gets a new `display_level` column populated at import time. The `/api/path-children` resolver filters children to the cascade whitelist and returns the modal bucket as the `next_rank_hint` so the dropdown label stays stable across the 40+ intermediate ranks.

## Why

After the smoke test of PR #29, the cascade UI for Chordata showed 22,711 children. The root cause: 22,688 of those were `unranked` rows CoL ships as direct children of Chordata without intermediate phylum ranks. The path-aware resolver returned them all because the filter was "every rank except the deprecated ones". The cascade dropdown was effectively frozen.

The fix is a single source of truth — `taxonomy.py` — that maps every rank CoL publishes to one of 8 visible buckets. The resolver filters to that whitelist, the frontend capitalises the bucket name for the dropdown label, and the cascade stays within the 8-bucket budget for every level.

## How

### `taxon/taxonomy.py` — the cascade contract

```python
DISPLAY_LEVELS = ("realm", "kingdom", "phylum", "class", "order", "family", "genus", "species")

RANK_TO_DISPLAY_LEVEL: Final[dict[str, str]] = {
    "domain": "realm",
    "superdomain": "realm",
    "subdomain": "realm",
    "kingdom": "kingdom",
    "subkingdom": "kingdom",
    "phylum": "phylum",
    "subphylum": "phylum",
    "infraphylum": "phylum",
    "parvphylum": "phylum",
    "microphylum": "phylum",
    "megaclass": "phylum",
    # ...etc — full mapping in the file...
}
```

The mapping collapses 40+ CoL ranks into the 8 buckets. Ranks not in the map (unranked, historical ranks like `proles`, `natio`, `lusus`, `aberration`, `mutatio`, `morph`, plus the year-numeric noise the .txtree parser accidentally emits) are excluded from the cascade. The whitelist is the source of truth.

### `taxon/schema.py` — `display_level` column

```python
class Taxon(MarkerColumns, Base):
    __tablename__ = "taxa"
    __table_args__ = (
        Index("ix_taxa_parent_name", "parent_id", "name"),
        Index("ix_taxa_rank", "rank"),
        Index("ix_taxa_display_level", "display_level"),
    )
    ...
    display_level: Mapped[str | None] = mapped_column(String, nullable=True)
```

The column is populated at import time so the resolver does not have to map rank → bucket at query time. The `ix_taxa_display_level` index lets us query "all phyla under Animalia" directly.

### `taxon/api/path_children.py` — filter + bucket hint

```python
cascade_ranks = list(RANK_TO_DISPLAY_LEVEL.keys())
children_stmt = (
    select(Taxon)
    .where(
        Taxon.parent_id == current.id,
        func.lower(Taxon.rank).in_([r.lower() for r in cascade_ranks]),
    )
    .order_by(func.lower(Taxon.name), Taxon.name)
)
```

The `next_rank_hint` is now the modal `display_level` bucket (not the raw rank), so the dropdown label stays stable across the 40+ intermediate ranks CoL publishes.

### `taxon/api/{col_import,import_data}.py` — populate at insert

```python
rows_with_bucket = [{**row, "display_level": display_level(row["rank"])} for row in rows]
```

Both import paths (CoL DwC-A and WoRMS) populate the column in the insert batch. The migration for the existing 7.87M rows in the live DB is one SQL: `ALTER TABLE taxa ADD COLUMN display_level TEXT; UPDATE taxa SET display_level = CASE rank WHEN ... END`.

### `frontend/src/components/Cascade.tsx` — capitalise the label

```tsx
dropdowns.push({
  key: `${deepestKey}-next`,
  label: deepestSnapshot.nextRankHint.charAt(0).toUpperCase() +
    deepestSnapshot.nextRankHint.slice(1),
  options: deepestSnapshot.children,
  value: null,
  loading: false,
});
```

The backend returns the bucket name (`"phylum"`, `"class"`, ...); the frontend capitalises for the dropdown header so the user reads "Phylum" / "Class" / "Order" / "Family" / "Genus" / "Species" regardless of whether the underlying rank is "subphylum" or "infraclass" or any other intermediate rank.

## Concrete UX impact

| Level | Before | After |
|---|---|---|
| Chordata (phylum) | 22,711 children — frozen dropdown | **23 children** — navigable |
| Mamalia (class) | 65 children — manageable | 65 children — same |
| Animalia (kingdom) | 22,711 children | 22,711 children — see below |

Animalia stays at 22,711 because **the dataset ships real species-rank and genus-rank rows as direct children of Animalia without intermediate phylum ranks**. The `.txtree` confirms this is the source-of-truth structure, not a CoL import bug. The display_level filter removes the 22,688 unranked rows from Chordata but cannot remove the 12,667 real species-row flat-rankd under Animalia — that would require reclassifying taxa, which is dataset curation, not code.

## Where

- `taxon/taxonomy.py` — new, 125 lines. Pure module with the rank → bucket contract.
- `taxon/schema.py` — add `display_level` column + index, 5 lines.
- `taxon/col_import.py` — populate `display_level` at insert, 18 lines.
- `taxon/import_data.py` — same for WoRMS path, 8 lines.
- `taxon/api/path_children.py` — filter + bucket hint, 49 lines.
- `frontend/src/components/Cascade.tsx` — capitalise the bucket label, 30 lines.
- `taxon/tests/test_taxonomy.py` — 53 RED-first tests pinning the whitelist.
- `taxon/tests/test_col_import.py` — 2 new tests pinning the populated column.
- `taxon/tests/test_api_path_children.py` — 3 new tests pinning the filter behaviour.
- `frontend/tests/Cascade.pathAware.test.tsx` — update mocks to use bucket names.
- `frontend/tests/Cascade.ui.test.tsx` — same.

## Verification

- 53 RED-first tests in `test_taxonomy.py` cover the whitelist exhaustively: every rank in the dataset, every bucket, the year-numeric noise, and the case-insensitive lookup.
- 6 tests in `test_col_import.py` pin the populated `display_level` for the fixture rows.
- 16 tests in `test_api_path_children.py` pin the filter behaviour: unranked excluded, historical ranks excluded, `next_rank_hint` is the bucket.
- 176 backend tests pass.
- 55/55 vitest tests pass.
- `tsc --noEmit` clean.
- `eslint` clean.
- `ruff check` + `ruff format --check` clean.
- `mypy taxon` clean.
- Manual smoke test against the live dev server: the kingdom dropdown lists 24 kingdoms, selecting Chordata drops the children from 22,711 to 23, and the dropdown label reads as "Phylum" regardless of the underlying rank of the children Animalia, Chordata, etc. expose.

## Workflows

- **CI** — 4 jobs green: backend (3.11, 3.12), frontend (node 20), lighthouse.
- **Reviews** — two commits: the feature (`fec178a`) and a `ruff format` follow-up. The follow-up happened because the local `ruff format` step was missing — `ruff check` was clean but the formatter was not. CI caught it on the first push.

## Lessons learned

- **The dataset is the bottleneck, not the code.** The 22,711 children Animalia exposes are real CoL rows — confirmed by walking the `.txtree` directly. The display_level filter can remove unranked rows (22,688 of them at Chordata) but cannot remove real species-rank rows that CoL flattens under kingdom. Animalia's 22,711 is a data-structure problem, not a code problem. The fix is dataset curation (PR #27d autocomplete, or a search endpoint), not a different filter.

- **One source of truth for the cascade contract.** Before this PR, the bucket name appeared in three places: the backend's `next_rank_hint`, the frontend's `inferDropdownLabel`, and the test fixtures. Disagreement among them caused the brittle browser-test fragility that bit PR #29. Now `taxon.taxonomy.DISPLAY_LEVELS` is the only contract — the backend reads it, the frontend capitalises it, the tests assert against it. Adding a new bucket is one line in `taxonomy.py`.

- **Whitelist, not blacklist.** The previous filter was implicit ("any rank in the DB"). Bugs and edge cases appeared as new ranks CoL introduced or as ranks we forgot to filter. The whitelist makes the contract explicit: every rank in the dataset is either mapped to a bucket or excluded. Adding a new rank is a deliberate choice in the diff, not a silent miss.

- **The year-numeric noise is real.** The `.txtree` parser emits ~3,500 strings like `1956 [15] [species]` where the `[15]` is not a rank — it leaks in because the regex matchea cualquier `[xxx]`. The whitelist ignores them. The import pipeline catches them at insert time via `display_level(rank) is None`, so they live in the DB but never in the cascade.

- **`ruff format --check` is part of CI.** Local `ruff check` was clean but the formatter was not. The CI gate `ruff format --check` caught the un-formatted code on the first push. Adding `ruff format taxon` to the pre-commit hook (or running it in CI) is the lesson: linting without formatting lets minor whitespace accumulate.

- **`size:exception` is honest when the work unit is cohesive.** 538 insertions and 42 deletions for a single PR is above the 400-line threshold. Splitting into chained PRs would require stubbing the resolver to call the not-yet-written taxonomy module, which would not be reviewable in isolation. The taxonomy → schema → import → resolver → frontend is a single reviewable contract.

## Follow-up PRs (not in this commit)

- **PR #27c** — deprecate the legacy rank-named endpoints (`/api/{kingdom}/phyla`, etc.). The cascade UI now uses the path-aware endpoint exclusively.
- **PR #27d** — autocomplete picker for Animalia's 22,711 children. The display_level filter cannot remove the real species-rank rows that CoL ships as direct children of Animalia. The autocomplete is the standard solution GBIF and COL use.
- **Search endpoint** — for the 1.5M unranked rows excluded from the cascade. The data is in the DB (searchable, in the import order); the cascade UI just hides them. A `/api/search?q=...` would surface unranked taxa on demand.
- **Pre-commit hook** — add `ruff format --check` to the local pre-commit flow so formatting drift is caught before CI, not after.
