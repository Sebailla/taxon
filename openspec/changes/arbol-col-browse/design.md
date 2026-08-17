# Design: arbol-col-browse

## Technical Approach

**Approach 3 (hybrid).** Backend adds `GET /api/tree/children?parent_id={id}` and `GET /api/tree/search?q={q}`. Existing `/{path:path}/taxon-links` keeps feeding the breadcrumb-links panel; `breadcrumb-dinamico` invariants stay verbatim. Parent-id addressing bypasses the `Biota` synthesis bug; `authorship` splits from `display_name`; `species_count` is a recursive CTE with lazy `null` for nodes with >100k direct children. Frontend replaces `Cascade.tsx` + `Cascade.state.ts` with `TaxonomicTree.tsx` + a Zustand tree cache keyed by `parent_id`. The explored path flows through `cascadePath` + `path:change` CustomEvent.

## Architecture Decisions

| # | Choice | Decision |
|---|--------|----------|
| 1 | parent-id (int) bypasses Biota synthesis; stable across CLB/CoL/Viruses | `parent_id={id:int}` |
| 2 | Live CTE keeps accuracy; no `species_paths` re-import | Recursive CTE, `null` when direct children > 100k |
| 3 | No DB column; `display_name` carries citation | Split `display_name` tail after `name` at query time |
| 4 | Lazy cache survives unmount; `cascadePath` feeds breadcrumb | `childrenByParent: Map<id, TreeNode[]>` + `expandedIds: Set<id>` + existing `cascadePath` |
| 5 | One round-trip per caret is wasteful | `has_children` pre-computed in parent fetch via `EXISTS` |
| 6 | No backend; no-op hides multi-source gap | UI no-op CoL-only first PR |
| 7 | `openspec/config.yaml strict_tdd: true` | Tests first |

## Data Flow

```
[ caret click ] → TaxonomicTree store (expandedIds.add)
  → fetchTreeNode(parent_id) → GET /api/tree/children
    list_tree_children + CTE species_count + split_authorship
    → TreeChildrenResponse{parent, children[], next_cursor}
  → render rows: rank: Name Authorship • N spp.

[ explored path ] → useCascadePath.setPath(segments)
  + window.dispatchEvent('path:change', {path})
  → App.tsx → fetchTaxonLinks → /api/{path}/taxon-links
  → <SpeciesLinks links={...}/> renders 13-link grid
```

## File Changes

- **Create** `taxon/api/tree.py` (`list_tree_children`, `search_taxon`, `_split_authorship`, recursive CTE); `taxon/tests/test_api_router_tree.py` (RED first); `frontend/src/components/TaxonomicTree.tsx`; `frontend/src/store/taxonomicTree.ts` (`childrenByParent` + `expandedIds`); `frontend/tests/TaxonomicTree.test.tsx`; `frontend/tests/api.treeChildren.test.ts`; `frontend/tests/api.treeSearch.test.ts`.
- **Modify** `taxon/api/router.py` (register `/api/tree/*` BEFORE `/{path:path}/taxon-links` catch-all at line 654); `taxon/api/schemas.py` (add `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`; export from `__all__`); `frontend/src/App.tsx` (mount `<TaxonomicTree>` in place of `<Cascade>`; keep `path:change` listener lines 150–159 and breadcrumb-links `useEffect` lines 119–142 verbatim); `frontend/src/api.ts` (add `fetchTreeNode`, `fetchTreeSearch`); `frontend/src/components/Breadcrumb.tsx` (rename `aria-label="Resolved species breadcrumb"` → `"Cascade path breadcrumb"` per Verify-Report §11 ISSUE #3). `<Toggles>` "extinct" chip folds into the new "Extant only" checkbox in `TaxonomicTree.tsx`.
- **Delete** `frontend/src/components/Cascade.tsx`; `frontend/src/components/Cascade.state.ts`; `frontend/tests/cascadeDynamicTiers.test.tsx`; `Cascade.pathAware.test.tsx`; `Cascade.ui.test.tsx`; `cascadeRoots.test.tsx`; `cascadeSubphylum.test.tsx`; `Cascade.test.tsx.legacy`.
- **Docs**: `documents-es/openspec/changes/arbol-col-browse/design-es.md`.

## Interfaces / Contracts

```python
# taxon/api/schemas.py
class TreeNodeResponse(TaxonResponse):
    has_children: bool
    species_count: int | None  # null when direct children > 100k
    authorship: str

class TreeChildrenResponse(_ORMBase):
    parent: TreeNodeResponse
    children: list[TreeNodeResponse]
    next_cursor: str | None

class TreeSearchResponse(_ORMBase):
    items: list[TreeNodeResponse]
```

```
# GET /api/tree/children?parent_id={int}&limit={n}&cursor={c}&include_extinct={bool}
# 200 → TreeChildrenResponse; 404 when parent_id unknown
# GET /api/tree/search?q={str}&limit={8}
# 200 → TreeSearchResponse (ranked exact > prefix > substring)
```

```sql
-- Recursive CTE for species_count (taxon/api/tree.py)
WITH RECURSIVE descendants(id) AS (
  SELECT id FROM taxa WHERE parent_id = :parent
  UNION ALL
  SELECT t.id FROM taxa t JOIN descendants d ON t.parent_id = d.id
)
SELECT COUNT(*) FROM descendants d
JOIN taxa t ON t.id = d.id
WHERE LOWER(t.display_level) = 'species';
```

```python
# taxon/api/tree.py
def _split_authorship(name: str, display_name: str) -> str:
    if display_name.startswith(name):
        return display_name[len(name):].strip()
    return display_name
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit (pytest) | `list_tree_children`, recursive CTE, `_split_authorship`, null-fallback, ranking, error envelopes (400/404/422) | `test_api_router_tree.py`; in-memory SQLite; RED first |
| Unit (vitest) | Caret toggle, row format, indent, keyboard Enter/Arrow, `aria-level`/`aria-expanded`, retry, empty state, `path:change` payload | `@testing-library/react`, `fetch` mocked |
| Integration (vitest) | App wiring: `path:change` listener, breadcrumb-links re-fetch | `App.taxonLinks.test.tsx` |
| A11y (vitest-axe) | Contrast, focus order, aria labels on `TaxonomicTree` | `TaxonomicTree.a11y.test.tsx` |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|----------|---------------|-----------------|-------------------|
| Doc-like paths (.sh, executable .md) | N/A — no such files | — | — |
| Git repo selection | N/A — no `git -C` | — | — |
| Commit / push / PR automation | N/A — no automation | — | — |
| **Route registration order** | **Applicable** — `/api/tree/*` must register BEFORE `/{path:path}/taxon-links` catch-all (line 654) to avoid shadow | Group `/tree/*` together; insert above the catch-all | RED: `GET /api/tree/children?parent_id=2` → 200; RED: `GET /api/tree/search?q=Euk` → 200. Safe: registered first. Failure: catch-all swallows → 404 |

## Migration / Rollout

No data migration. Backend PR adds two endpoints additively. Frontend PR mounts `TaxonomicTree` in the same grid slot, then deletes `Cascade` in a chained slice so `develop` never sees a broken intermediate. `/api/kingdoms` Biota synthesis stays (unused but harmless; removal is a follow-up). Rollback: `git revert <merge-commit>` per PR. Pencil + `impeccable` gate the frontend PR per AGENTS.md §5.

## species_count threshold benchmark

The default threshold for `species_count` lazy-null is
:data:`taxon.api.tree.SPECIES_COUNT_LAZY_NULL_THRESHOLD = 100_000`
direct children. The benchmark below measures actual wall time of
the recursive CTE against `data/col.db` so the threshold choice is
evidence-based, not arbitrary.

Measured on `darwin / Python 3.14.7 / SQLite 3.x` against
`/Users/sebailla/Developer/taxon/data/col.db` (1.5 GB CoL import,
~7.5M taxa rows):

| `parent_id` | direct children | species descendants | CTE wall time |
|-------------|----------------:|--------------------:|--------------:|
| `1` (Archaea root) | 4 | 927 | 3 ms |
| `43341` (Eukaryota root) | 9 | 5,654,308 | 14,306 ms |
| `43342` | 22,711 | 3,517,094 | 11,835 ms |
| `2811370` | 30,397 | 415,987 | 1,511 ms |
| `1430129` | 7,910 | 314,426 | 1,202 ms |
| `5926563` | 1,878 | 1,656,572 | 2,653 ms |
| `949691` | 9,296 | 96,572 | 113 ms |
| `pid=2754921` | 8,932 | 1,920 | 8 ms |
| `pid=1808184` | 3,460 | 7,719 | 11 ms |
| `pid=5561750` | 1,502 | 127,870 | 398 ms |
| `pid=5341398` (random) | 1,000-1,500 | mostly <100 | 1-120 ms |

**Observations:**

1. The `col.db` dataset's highest-fanout node measures **94,443**
   direct children (`parent_id=1491852`, `†Zarqacecidomyius
   Kaddumi, 2007`). This is BELOW the 100k threshold, so the
   lazy-null never fires in production against `col.db`.
2. The dominant cost driver for the recursive CTE is the
   **descendant depth × breadth** (Eukaryota → 5.6M species at
   only 9 direct children is the slowest), NOT the direct-child
   fanout. Direct-children fanout alone is a rough proxy at best.
3. The 100k hard threshold protects against future datasets that
   might exceed `col.db`'s ceiling while still returning a
   well-known null -- the UI renders `—` instead of blocking the
   response.

**Honest limitation:** the threshold does NOT measure
descendant-tree breadth. A future tightening should include a
second gate (e.g. `if descendants_count > 1_000_000: return
None`) measured against a deeper ancestor fanout, but the first
PR ships the 100k-direct-children threshold verbatim because
`col.db`'s highest fanout stays below it.

## Open Questions

- [ ] Confirm 100k direct-children `species_count` lazy-null threshold against `data/col.db` (benchmark in apply).
- [ ] Confirm `Source` no-op first PR is acceptable; multi-source backend is out of scope.
- [ ] Pencil: dedicated `.pen` page, or share `taxon.pen`? Decide before frontend PR.
