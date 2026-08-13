# Path-aware cascade backend (PR #27)

## What

Added a new endpoint `GET /api/path-children?path=A|B|C` that walks the caller-supplied path of canonical names and returns the direct children of the deepest resolved taxon, regardless of rank name. This is the backend half of the path-aware cascade refactor that makes CoL's 40-rank dataset usable in the UI.

The legacy six fixed-rank endpoints (`/api/Animalia/phyla`, `/api/Animalia/Chordata/classes`, etc.) remain available and unchanged for backward compatibility. Their deprecation and removal is a follow-up PR.

## Why

After the CoL re-seed (PR #26) the cascade UI broke in the browser: `Chordata` has 0 class children because its actual children are subphyla (`Vertebrata`, `Cephalochordata`, `Tunicata`). The old resolver enforced `rank == 'class'` at that depth and returned `[]`. Every path with intermediate ranks (subphylum, gigaclass, infraclass, superorder, parvorder, ...) breaks the same way.

The new endpoint does not assume any rank order. It walks the path case-insensitively, anchored on the parent at each step, and returns whatever children the deepest taxon actually has, plus a `next_rank_hint` (the mode of the children ranks) so the frontend can label the next dropdown without hardcoding the six canonical ranks.

## How

### Module: `taxon/api/path_children.py`

```python
def list_path_children(
    session: Session,
    segments: list[str],
) -> PathChildrenResponse | None:
    """Walk segments to the deepest resolved taxon and return its
    direct children, regardless of rank."""
```

The first segment is anchored on `rank == 'kingdom'` (so a kingdom named after an unrelated parent does not resolve); subsequent segments are anchored only on `parent_id == previous.id`. Returns `None` when any segment fails to resolve — the router maps that to a 404 with the failing segment in the detail.

`PathChildrenResponse` carries:

- `parent`: the deepest resolved taxon (a `TaxonRow`).
- `children`: the direct children of `parent`, sorted by name.
- `next_rank_hint`: the mode of the children ranks, so a heterogeneous child set (a few subphyla + a handful of unranked microspecies) still gets a sensible label. `None` when the children are empty (leaf node).

### Endpoint: `GET /api/path-children?path=A|B|C`

Wired in `taxon/api/router.py` with a docstring that documents the contract. Pipes are URL-encoded as `%7C` by the frontend; FastAPI decodes them automatically.

### Schema: `taxon/api/schemas.py` — `PathChildrenEnvelope`

The response model mirrors `PathChildrenResponse` so the OpenAPI schema documents the contract.

## Where

- `taxon/api/path_children.py` — new, 100 lines.
- `taxon/api/router.py` — 45 lines added (the new endpoint).
- `taxon/api/schemas.py` — 20 lines added (`PathChildrenEnvelope`).
- `taxon/tests/test_api_path_children.py` — new, 339 lines, 13 RED-first tests.

No existing tests modified. The legacy six fixed-rank endpoints and their tests are unchanged.

## Verification

- `pytest taxon/tests/` → 118 passed (was 105; +13 new tests).
- `ruff check` + `ruff format --check` clean.
- `mypy --strict taxon/` clean (30 source files).

End-to-end manual probe against the live CoL archive confirms the path-aware resolver chains through CoL's intermediate ranks:

```
GET /api/path-children?path=Animalia|Chordata|Vertebrata|Gnathostomata|Osteichthyes|Actinopterygii
→ 200, 2 children, hint=superclass
   - Actinopteri (superclass)
   - Cladistia (superclass)
```

The chain `Animalia → Chordata → subphylum Vertebrata → infraphylum Gnathostomata → parvphylum Osteichthyes → gigaclass Actinopterygii → superclass Actinopteri → class Actinopteri → ...` works end-to-end. The legacy endpoint `/api/Animalia/Chordata/classes` returns `[]` because it enforces `rank == 'class'` at that depth; the new endpoint does not.

## Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend, lighthouse). All green. No new workflows.
- **Reviews** — 2 `work-unit-commits`:
  1. `f2ed7de test(api): add RED-first coverage for the path-aware /path-children endpoint` — fails first against the missing endpoint.
  2. `ca4901d feat(api): add path-aware /path-children endpoint` — drops in the resolver + endpoint + schema, tests go GREEN.
- **Frontend migration (PR #27b, follow-up)** — the cascade UI gets refactored from six fixed-rank dropdowns to N dynamic dropdowns that consume the new endpoint. Each dropdown emits the next path segment when the user picks an option; the next API call asks for the children of the new deepest taxon.

## Lessons learned

- **Path-aware beats rank-aware.** The old six fixed-rank endpoints were a snapshot of the WoRMS source dataset's canonical six ranks. CoL has 40+ ranks and uses intermediates freely (subphylum, gigaclass, infraphylum, parvphylum, ...). The path-aware resolver does not care how many ranks exist or what they are called; it walks whatever the data gives it. This is the only contract that scales as the dataset evolves.

- **`next_rank_hint` is the mode, not a static mapping.** A heterogeneous child set (a few subphyla + a handful of unranked microspecies) gets the rank that occurs most often, not a hardcoded "the next rank is class". The frontend uses the hint to label the dropdown but the path drives the actual API call.

- **Endpoint stays additive in this PR.** The legacy endpoints remain available; their deprecation and removal is a separate PR that includes a frontend migration plan. Splitting the two keeps each PR small and reviewable.

- **Test against the live dataset, not just a hand-crafted fixture.** The CoL chain `Chordata → Vertebrata → Gnathostomata → Osteichthyes → Actinopterygii → Actinopteri → ...` is not in the test fixture (it predates the CoL re-seed). The live-probe step after CI green is what caught the chain depth and confirms the resolver handles 6+ intermediate ranks without surprises.

## Follow-up PRs (not in this commit)

- **PR #27b** — refactor the cascade UI to N dynamic dropdowns that consume the new endpoint. The state machine in `Cascade.tsx` needs to handle an arbitrary number of ranks instead of the hardcoded six.
- **PR #27c** — deprecate the six legacy rank-named endpoints, add a deprecation warning to the response, remove them after one release. After #27b ships, no frontend caller should still need the legacy endpoints.

## Verification with the live CoL archive

The endpoint was tested against the live CoL archive (`data/taxon.db`, 2.3 GB, 7.87M rows) with curl probes. The path-aware resolver chains correctly through CoL's intermediate ranks and emits sensible `next_rank_hint` values for both homogeneous and heterogeneous child sets.
