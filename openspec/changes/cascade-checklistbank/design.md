# Design: cascade-checklistbank

## Technical Approach

Replace the GBIF Species API in the cascade backend with ChecklistBank's
`COL2024` dataset. The pivot fixes a smoke-test failure where GBIF's
backbone only returned four phyla under `Animalia`; CLB exposes 34
plus the previously-missing `Biota` root and `subphylum` tier. The
shape of the change is end-to-end: new HTTP client, new path-aware
resolver with a 9-tier tuple (Biota + subphylum), router re-wired,
then a frontend slice that adds the Biota dropdown and the subphylum
label. Backend lands as three chained PRs (client, resolver, router
swap + deletions), then PR #4 adds the UI under the Pencil +
`impeccable` gate.

## Architecture Decisions

| Decision | Choice | Tradeoff | Decision rationale |
| --- | --- | --- | --- |
| Client module name | `taxon/checklistbank.py` (new) + delete `taxon/gbif.py` | Renaming doubles diff churn but removes dead code | PR #3 is already destructive; renaming here is the cheapest moment to do it. Reviewers see one rename rather than three. |
| Resolver module name | `taxon/api/clb_path_children.py` (new) + delete `gbif_path_children.py` | Same trade-off as above | Consistent with the client rename. |
| Resolver walk strategy | `/tree/{id}/children` with name match (no `higherTaxonKey`) | Two calls per segment instead of GBIF's one — more network | CLB search lacks the parent-anchor filter; the walk must compose search-by-name + children-by-id. Per-tier cache is a follow-up. |
| Tier tuple | 9 tiers `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` | Subphylum adds a tier slot the UI must render | Locked decision in the proposal. The UI's path-agnostic reducer absorbs the new tier with no logic change. |
| Subphylum collapse rule | When a phylum has zero subphylum children, return classes directly with `next_rank_hint="order"` | Empty subphylum slot in the dropdown | CLB has subphyla under Chordata (3) but Arthropoda (0); the resolver must skip the empty tier without a second round-trip. |
| Dataset key | Pin `COL2024`; `3LR` documented as a code comment | Pinned key locks the cascade to one annual release | Reproducibility + one-line upgrade path. CoL releases annually; bump is a constant. |
| Router swap | `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)`; delete the old dep | One rename, one deletion | Required by the module rename. The dependency override in tests follows. |
| PR #2 split | Split into PR #2a (resolver core walk) + PR #2b (subphylum collapse) | More PRs to review | Both exceed the 400-line budget on their own. Splitting keeps each slice reviewable. |
| Frontend label inference | Backend carries `next_rank_hint`; frontend already capitalizes | No label table needed | Backend emits a stable string per tier; UI does not branch on rank. New ranks ("subphylum", "biota") are absorbed by the existing capitalize-and-render path. |

## Data Flow

```
    Browser                  FastAPI router             ChecklistBankClient        api.checklistbank.org
    --------                 --------------             -------------------         ----------------------
  fetchRoots() ───────────►  GET /api/kingdoms       ──►  GET /dataset/COL2024/tree ────►
                              (returns Biota+Viruses)      parse → TaxonResponse[]
  fetchPathChildren(path) ─► GET /api/path-children ──►  list_path_children ─────►
                                                          ├─ _resolve_deepest ────►  GET /nameusage/search?q=&rank=
                                                          └─ _children_for ──────►  GET /tree/{id}/children?rank=
                                                                                       (subphylum probe + class probe)
  fetchSpeciesList(path)  ─► GET /api/species-list  ──►  same resolver + rank="species"
```

`_resolve_deepest` walks `segments` by alternating search (to bind a
name to an id) and `/tree/{id}/children` (to find that id's parent id
for the next segment). `_children_for` implements the subphylum
collapse: it probes `/tree/{id}/children` with `rank=subphylum`, and
when the response is empty it re-probes with `rank=class` and emits
`next_rank_hint="order"`.

## File Changes

| File | Action | Description |
| --- | --- | --- |
| `taxon/checklistbank.py` | Create | CLB client (`ChecklistBankClient`) + `ChecklistBankTaxon` dataclass. Methods: `get_taxon`, `get_children`, `search`, `_request`. Mirrors the GBIF client's shape so reviewers familiar with `taxon/gbif.py` can diff side-by-side. ~200 LOC. |
| `taxon/api/clb_path_children.py` | Create | 9-tier resolver with Biota root + subphylum collapse. Mirrors `taxon/api/gbif_path_children.py` shape: `list_path_children` + `PathChildrenResponse` + `_resolve_deepest` + `_children_for` + `_to_taxon_row`. ~280 LOC. |
| `taxon/api/router.py` | Modify | `/api/kingdoms`, `/api/path-children`, `/api/species-list` rebind `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)`; bodies call the CLB resolver. Add `_get_checklistbank_client` dependency. |
| `taxon/gbif.py` | Delete | Replaced by `taxon/checklistbank.py` in PR #3. |
| `taxon/api/gbif_path_children.py` | Delete | Replaced by `taxon/api/clb_path_children.py` in PR #3. |
| `taxon/tests/test_checklistbank.py` | Create | `_StubClient` mocks `/dataset/COL2024/tree/{id}/children` + `/dataset/COL2024/nameusage/search`. RED-first: 9–10 tests. ~250 LOC. PR #1. |
| `taxon/tests/test_clb_path_children.py` | Create | Resolver tests: Biota root, subphylum bucket (Chordata 3, Arthropoda 0), full Mammalia chain, dedup by opaque id. RED-first: 11–12 tests. ~350 LOC. PR #2. |
| `taxon/tests/test_api_clb_router.py` | Create | Router integration: root returns Biota+Viruses; path-children walks the 9-tier tuple. ~200 LOC. PR #3. |
| `taxon/tests/test_gbif.py`, `test_gbif_path_children.py`, `test_api_gbif_router.py` | Delete | Replaced by the CLB tests in PR #3. |
| `frontend/src/api.ts` | Modify | `fetchKingdoms` → `fetchRoots` (returns Biota + Viruses). PR #4. |
| `frontend/src/components/Cascade.tsx` | Modify | Label inference for `"subphylum"` and `"biota"` (capitalize + render). No reducer change. PR #4. |
| `frontend/tests/api.test.ts`, `Cascade.pathAware.test.tsx`, `Cascade.ui.test.tsx` | Modify | Mock paths add Biota; expect subphylum slot. PR #4. |
| `taxon.pen` | Modify | One extra dropdown slot for Biota + subphylum label. Pencil MCP only; `impeccable` review before code lands. PR #4. |
| `openspec/changes/cascade-checklistbank/design.md` | Create | This document. |
| `documents-es/openspec/changes/cascade-checklistbank/design-es.md` | Create | Spanish mirror (faithful translation, neutral/professional). |

## Interfaces / Contracts

```python
# taxon/checklistbank.py

DATASET_KEY: str = "COL2024"            # Future upgrade: swap to "3LR" (latest release).
CLB_BASE_URL: str = "https://api.checklistbank.org"

@dataclass(frozen=True)
class ChecklistBankTaxon:
    id: str                            # Opaque CLB ID, e.g. "5T6MX", "CH2".
    name: str                           # Canonical name, e.g. "Chordata".
    label_html: str                     # Display label with HTML markup.
    parent_id: str | None               # Opaque parent ID.
    count: int | None                   # Total descendant count.
    child_count: int | None             # Direct child count.
    authorship: str | None              # Author citation (verbatim).
    rank: str | None                    # "biota", "kingdom", "phylum", "subphylum", ...
    status: str | None                  # "accepted", "synonym", ...

class ChecklistBankClient:
    def __init__(
        self,
        base_url: str = CLB_BASE_URL,
        dataset_key: str = DATASET_KEY,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None: ...

    def get_taxon(self, taxon_id: str, dataset_key: str = DATASET_KEY) -> ChecklistBankTaxon | None: ...
    def get_children(
        self,
        taxon_id: str,
        limit: int = 300,
        rank: str | None = None,
        dataset_key: str = DATASET_KEY,
    ) -> list[ChecklistBankTaxon]: ...
    def search(
        self,
        q: str,
        rank: str | None = None,
        limit: int = 20,
        dataset_key: str = DATASET_KEY,
    ) -> list[ChecklistBankTaxon]: ...

# taxon/api/clb_path_children.py

CASCADE_TIERS: tuple[str, ...] = (
    "biota", "kingdom", "phylum", "subphylum",
    "class", "order", "family", "genus", "species",
)

@dataclass(frozen=True)
class PathChildrenResponse:
    parent: TaxonRow
    children: list[TaxonRow]
    next_rank_hint: str | None

def list_path_children(
    segments: list[str],
    client: ChecklistBankClient | None = None,
) -> PathChildrenResponse | None: ...
```

Public response schema (`PathChildrenEnvelope`, `TaxonResponse`,
`SpeciesListItem`) is unchanged — only the field types shift from
`int` to `str` for `id` and `parent_id`. PR #3's frontend contract
change (the `id` type widening) is the only visible API shift; it is
typed in the React side via `TaxonResponse.id: number | string`.

## Resolver Walk Algorithm

```
_resolve_deepest(segments, client):
    parent_id = None
    current = None
    for depth, segment in enumerate(segments):
        # Step 1: bind the segment name to a CLB id.
        rank = _rank_for_depth(depth)        # biota, kingdom, phylum, ...
        hits = client.search(segment, rank=rank)
        hit = first(hits, name == segment)   # case-insensitive match
        if hit is None: return current
        current = hit
        parent_id = hit.id
    return current

_children_for(current, client):
    next_rank = _next_tier_for(current.rank)
    if next_rank == "subphylum":
        probe = client.get_children(current.id, rank="subphylum")
        if probe is empty:
            # Collapse: skip subphylum, return classes directly.
            classes = client.get_children(current.id, rank="class")
            return classes, "order"           # next_rank_hint = "order"
        return probe, "class"                 # next_rank_hint = "class"
    if next_rank is None:
        return [], None                       # leaf
    children = client.get_children(current.id, rank=next_rank)
    return children, next_rank.lower()        # next_rank_hint = next_rank

_next_tier_for(rank):
    "biota"     → "kingdom"
    "kingdom"   → "phylum"
    "phylum"    → "subphylum"  (collapsed to "class" at runtime when empty)
    "subphylum" → "class"
    "class"     → "order"
    "order"     → "family"
    "family"    → "genus"
    "genus"     → "species"
    "species"   → None
```

The subphylum collapse does **not** recurse: when a phylum has no
subphylum children and no class children (rare fossil clades), the
resolver returns an empty list with `next_rank_hint="order"`. The
frontend treats the empty list as a leaf.

## Subphylum Collapse Rule

| Phylum | Subphylum children | Resolver behaviour |
| --- | --- | --- |
| `Chordata` (`CH2`) | 3 (Cephalochordata, Tunicata, Vertebrata) | Returns subphyla, `next_rank_hint="class"` |
| `Arthropoda` | 0 | Collapses: returns classes directly, `next_rank_hint="order"` |
| Fossil phylum with no subphylum AND no class | 0 + 0 | Returns empty list, `next_rank_hint="order"` — the cascade stops, frontend renders an empty dropdown. The resolver does not loop. |

The collapse rule is a one-shot probe: the resolver queries
`/tree/{id}/children?rank=subphylum` once. If the result is empty,
it re-queries with `rank=class` and rewrites `next_rank_hint`. There
is no recursive descent; the tier tuple remains a 9-tuple in code.

## Testing Strategy

| Layer | What to test | Approach |
| --- | --- | --- |
| Unit (PR #1) | `ChecklistBankClient` request shapes, parse, 404 → None | `httpx.MockTransport` + `_StubClient`; 9–10 RED-first tests |
| Unit (PR #2) | `_resolve_deepest`, `_children_for`, subphylum collapse | Stub client returns canned `/tree/{id}/children` and `/nameusage/search`; 11–12 tests |
| Integration (PR #3) | `/api/kingdoms` returns Biota+Viruses, `/api/path-children` walks the 9-tier tuple | `TestClient` with `app.dependency_overrides[_get_checklistbank_client]`; 4 tests |
| Frontend (PR #4) | `fetchRoots` shape, Cascade renders N+1 dropdowns incl. subphylum | Vitest + jsdom; mock fetches return the new envelope |
| Pencil review | Hierarchy, accessibility, motion, anti-patterns | `impeccable` skill on `taxon.pen` before any frontend code lands |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation,
executable-file classification, or process-integration boundary.
The HTTP client wraps a read-only public API; no subprocesses, no
shell-out, no file-mode classification. CI is the existing pytest +
Vitest pipeline.

## Migration / Rollout

- **Dataset key**: pinned `COL2024`. Annual bump is a one-line
  constant change; `3LR` is documented in the code comment near
  `DATASET_KEY` as the upgrade path.
- **Dead GBIF code**: deleted in PR #3. `grep -r "gbif\|Gbif\|GBIF"
  taxon/ frontend/src/ --include="*.py" --include="*.ts"
  --include="*.tsx"` must return zero hits after PR #3 merges.
- **Saved URLs**: a GBIF-shaped path (e.g.
  `path=Animalia|Chordata|Mammalia|Carnivora|Felidae|Panthera`)
  becomes a CLB-shaped path (`...|Vertebrata|Mammalia|...`). Old
  URLs hit 404 with a clear message; users re-share with the new
  segment.
- **PR #3 rollback** is destructive; the proposal documents a
  follow-up PR that reintroduces `taxon/gbif.py`, the three test
  files, and rewires `taxon/api/router.py`.
- **PR #4 frontend rollback** is non-destructive: revert merge,
  backend stays green.

## Open Questions

None. The three locked decisions (9-tier tuple, Biota+Viruses root,
COL2024 pin) are in the proposal; the subphylum collapse rule is
specified in the delta spec.

## Per-PR Workload Forecast

| PR | Title | Files | LOC | Budget (400) | Decision |
| --- | --- | --- | --- | --- | --- |
| #1 | `feat(checklistbank): add CLB client and taxon parser` | `taxon/checklistbank.py` (~200) + tests (~250) | ~450 | Over | Split: parser + client in one commit; tests in the next. `work-unit-commits` keeps each commit under the cap. |
| #2a | `feat(checklistbank): path resolver core walk` | `taxon/api/clb_path_children.py` (~280) + 5 tests (~140) | ~420 | Over (slightly) | Commit split per `work-unit-commits`: module + dataclass in one commit, walk + 5 tests in the next. |
| #2b | `feat(checklistbank): subphylum collapse rule` | collapse logic in resolver + 6 tests (~250) | ~250 | Under | Single commit; clean slice. |
| #3 | `feat(api): route cascade endpoints through CLB client` | `router.py` rewrite + 4 tests (~200) − 1,200 deletions | −700 net | Under | Destructive PR; reviewers confirm dead code is removed. |
| #4 | `feat(frontend): render Biota + subphylum in the cascade UI` | `api.ts` + `Cascade.tsx` (~150) + tests (~100) + Pencil design | ~250 + design | Under | Gated on `impeccable` review. |

Total: 5 PRs (one auto-chain split), 4 backend + 1 frontend.
Decision needed before apply: Yes (approve the #2a/#2b split).
Chained PRs recommended: Yes.
400-line budget risk: Low after the #2 split.
