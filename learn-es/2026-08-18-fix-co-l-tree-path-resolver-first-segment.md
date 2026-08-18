# What

Fix puntual al resolver de path del cascade: `taxon/api/hierarchy.py::_candidate_bucket_indices(None)` ahora recorre todos los buckets del cascade (realm → kingdom → phylum → … → species) en lugar de anclarse solo al bucket kingdom. Cierra el issue #74 y se mergea como PR #75 con CI verde (backend 3.11/3.12, frontend, lighthouse) y 256 tests pasando (255 previos + 1 contrato nuevo end-to-end).

# How

- Una línea de cambio en `taxon/api/hierarchy.py` (la rama `if last_bucket_index is None`) — `return [_DISPLAY_LEVELS_IN_ORDER.index("kingdom")]` se convierte en `return list(range(len(_DISPLAY_LEVELS_IN_ORDER)))`. Docstring reescrito para reflejar el contrato nuevo.
- Renombrado `test_resolve_path_first_segment_kingdom_anchor` → `test_resolve_path_first_segment_accepts_any_top_bucket` en `taxon/tests/test_api_path_resolver_skip_tier.py`. La aserción cambió de `row_chordata_first is None` a `row_chordata_first.name == "Chordata"` (phylum como primer segmento ahora resuelve).
- Nuevo test `test_taxon_links_accepts_single_domain_segment` en `taxon/tests/test_api_router_tree.py` que arma la app con la fixture `app_five_roots` (5 raíces CoL-style: Archaea/Bacteria/Eukaryota/Viruses/incertae sedis) y verifica que `GET /api/Eukaryota/taxon-links` devuelve 200 con el envelope de 13 links.
- Conventional commit: `fix(api): accept any top-of-tree rank on the first path segment`.

# Where

- `taxon/api/hierarchy.py` — `_candidate_bucket_indices` (líneas 285-298 en el commit).
- `taxon/tests/test_api_path_resolver_skip_tier.py` — renombre + flip de aserción en `test_resolve_path_first_segment_accepts_any_top_bucket`.
- `taxon/tests/test_api_router_tree.py` — nuevo `test_taxon_links_accepts_single_domain_segment` al final del archivo.
- Branch efímero `fix/path-resolver-any-first-segment` (squash merge → `425d48b` en develop).

# Why

El árbol CoL-style (`arbol-col-browse`, PR #69) dispatcha `path:change` con la raíz clickeada como array de un solo segmento. Las raíces CoL (`Eukaryota`, `Archaea`, `Bacteria`, `Viruses`, `incertae sedis`) tienen rank `domain` o `unranked` que mapea al bucket `realm` (vía `taxonomy_display_level`), no `kingdom`. El resolver restringía el primer hop a kingdom, así que **toda** interacción del breadcrumb arriba del nivel kingdom 404'eaba, y el panel de links mostraba `Could not load links: taxon not found: 'Eukaryota'`. El bug rompió el contrato entre el frontend (que ahora dispatcha paths CoL-style) y el backend (que asumía cascade de 7 dropdowns con reino como primer segmento obligatorio).

# How it works

El fix es backwards-compatible para kingdom y phylum (siguen resolviendo como antes, solo que ahora también pasan por buckets adicionales que no tienen match en esos casos). Para dominio/realm, ahora hay match. El skip-tier walk para segmentos posteriores queda intacto: cada segmento después del primero sigue anclado en `parent_id = previous.id` y solo prueba el bucket inmediato inferior + el mismo bucket (para off-tuple intermediates como subphylum, superclass, suborder, etc.). El primer hop es el único que prueba todo el cascade.

Reproducción en producción:

1. Abrir `http://localhost:8000` en el browser.
2. Esperar a que el árbol hidrate. Las 5 raíces aparecen.
3. Click en Eukaryota (o cualquier raíz de dominio).
4. El breadcrumb muestra `Eukaryota` y el panel de "Search source dispatch" lista los 13 botones (Wikipedia, Google, BHL, ResearchGate, Plos, Academia, Scielo, Scholar, Youtube, Zootaxa, Photos, Sci-hub, Scribd).
5. `curl http://localhost:8000/api/Eukaryota/taxon-links` devuelve 200 con el JSON del envelope.

# Workflows

- **Branch**: el fix vive en `fix/path-resolver-any-first-segment` (squash merge a develop via PR #75). El worktree `../taxon-worktrees/fix-path-resolver-first-segment` se eliminó tras el merge — el branch local también.
- **CI**: backend (ruff check + format check + mypy strict + pytest), frontend (typecheck + vitest + eslint + build), lighthouse. Todo verde. La matriz python 3.11/3.12 detecta incompatibilidades de sintaxis o tipos que escapan al verify local.
- **PR body**: linkea `Closes #74` y aplica `bug` (no `type:bug` — ese label no existe en este repo; los labels son los nativos de GitHub: `bug`, `enhancement`, `documentation`, etc.).
- **Issue creation**: el skill `issue-creation` aplica un privacy scan antes de `gh issue create` (sin paths absolutos, sin usernames, sin credenciales) — el body del issue #74 menciona solo nombres de dominio públicos y rutas relativas.
- **Learn-es**: este archivo. Se escribe en el checkout principal (develop), no en el worktree, después del merge y antes del cleanup del worktree, según la regla 2 del `AGENTS.md` local.
