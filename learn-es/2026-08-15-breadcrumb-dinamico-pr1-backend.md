# Breadcrumb dinámico por taxón (PRs #65 + #66)

## Qué

El breadcrumb de la cascada pasa a renderizarse en cualquier momento en que el usuario haya elegido al menos un eslabón del cascade (no solo cuando ya hay una especie resuelta), y cada segmento es un botón que abre el mismo grid 4×3 de 13 enlaces de búsqueda que produce la fila de especie, pero referido al nombre de ese taxón.

## Cómo

- Nuevo endpoint backend `GET /api/{path}/taxon-links` que acepta 1–7 segmentos canónicos (sin epíteto de especie), resuelve el más profundo vía `resolve_path_by_display_level`, y reutiliza `build_search_links(taxon.name, load_templates(...))` para producir los 13 enlaces. Sobre `TaxonLinksResponse{ taxon: TaxonResponse, links: list[SearchLinkItem] }`. Codifica el separador de segmentos como `%7C` para que el catch-all `{path:path}` de FastAPI no se confunda con slashes literales. Devuelve 404 con `detail` nombrando el segmento malo o la violación del límite de 7.
- Frontend reescrito alrededor de un store zustand `cascadePath` que comparte el path del cascade entre el `Cascade.tsx` reducer (escritor) y `App.tsx` panel (lector). `Cascade.tsx` despacha un `CustomEvent<{path: string[]}>("path:change")` en cada cambio real de `state.path`. `App.tsx` escucha y keyed-effect pide `fetchTaxonLinks(path, { signal })` con un `AbortController` por panel.
- `Breadcrumb.tsx` cambia: cada segmento es ahora `<button type="button">` con `aria-current="page"` en el más profundo. Nueva prop opcional `onSelect?: (path: string[]) => void`. Se conserva chevron, `font-mono`, `bg-surface`, `border-border`.
- 13 enlaces por taxón (no 12) — el primer spec decía "12" pero `templates.md` tiene 13 filas y `load_templates` exige `==13`. Se corrigió el wording en spec, proposal, design y mirrors.

## Dónde

- `taxon/api/schemas.py` — `TaxonLinksResponse` agregado a `schemas.py` y exportado en `__all__`.
- `taxon/api/router.py` — ruta `taxon_links()` registrada entre `/path-children` y `/species-links`.
- `taxon/tests/test_api_router_taxon_links.py` — 11 tests: shape, sustitución, canonical name, 404 unknown, 404 invalid last segment, 404 cap, regresión.
- `frontend/src/store/cascadePath.ts` — store zustand `create<CascadePathState>` (react flavour, no vanilla), con guard `arraysEqual` para no-op replaces.
- `frontend/src/api.ts` — `fetchTaxonLinks(pathSegments, init?)` + `TaxonLinksResponse` interface.
- `frontend/src/components/Breadcrumb.tsx` — segmentos como `<button>`, `aria-current`, `onSelect` opcional.
- `frontend/src/components/Cascade.tsx` — `useEffect` que despacha el CustomEvent `path:change` cuando `state.path` cambia.
- `frontend/src/App.tsx` — nuevo state `breadcrumbLinks` con `useEffect` keyed por `cascadePath`, `AbortController` por panel, "last-clicked wins"; eliminado el gate `resolved !== null`.
- `frontend/tests/{Breadcrumb.dynamic,store.cascadePath,api.taxonLinks,App.taxonLinks,cascadeDynamicTiers}.test.tsx` — 17 tests nuevos sobre 86 totales (antes 69).
- `frontend/package.json` — `"zustand": "^5.0.0"`.

## Por qué

El cascade lineal Biota → Reino → Filo → … → Género era capaz de resolver cualquier especie pero descartaba los rangos intermedios (subphylum, megaclass, superorder, etc.) y rompía la navegación cuando el árbol real tenía jerarquías no triviales. El breadcrumb además solo aparecía al final con la especie resuelta, así que el usuario no podía consultar información sobre un phylum o familia mientras construía la cadena. Replicar la fila de 13 enlaces (pero al nombre del taxón en lugar del nombre de la especie) le da al usuario puntos de consulta tempranos: cuando llega a Phylum Arthropoda ya puede abrir la grilla con enlaces a Wikipedia, Google, BHL, GBIF-ResearchGate, Plos, Academia, Scielo, Scholar, Youtube, Zootaxa, Photos, Sci-hub y Scribd referidos a "Arthropoda" en lugar de tener que descender hasta una especie para recién empezar a navegar.

## Cómo funciona en producción

1. El usuario hace click en la primera dropdown del cascade (`Biota` → `Animalia`). El `Cascade.tsx` cambia `state.path = ["Biota", "Animalia"]` y despacha `path:change` en `window`.
2. `App.tsx` escucha `path:change`, su `useEffect` keyed por `cascadePath.join("|")` llama `fetchTaxonLinks(["Biota", "Animalia"], { signal })` al nuevo endpoint `/api/Biota%7CAnimalia/taxon-links`.
3. El backend resuelve `Animalia` como el taxón más profundo de esa ruta, llama `build_search_links("Animalia", templates)` y devuelve `TaxonLinksResponse{ taxon: Animalia, links: 13 SearchLinkItems }`.
4. Mientras el fetch está vivo, el `<Breadcrumb>` arriba del Cascade pinta dos botones (Animalia y "Animalia" ambos visibles); el más profundo lleva `aria-current="page"`. Si el usuario cambia la dropdown phylum de `Chordata` a `Mollusca` antes que el fetch resuelva, el `AbortController` mata esa petición y arranca otra nueva.
5. El panel a la derecha re-renderiza con los 13 enlaces. Click en cualquier botón abre `target="_blank" rel="noopener noreferrer"` como hoy.
6. Si el usuario después resuelve una especie (click en `Homo sapiens` dentro de la lista), el panel se limpia y se reemplaza por el grid de enlaces de especie.
7. Si el usuario después hace click en el segmento "Animalia" del breadcrumb, vuelve a renderizar el grid con los enlaces para Animalia (last-clicked wins).

## Workflows

- **CI**: backend (Python 3.11 + 3.12) + frontend (Node 20) + Lighthouse a11y. Todos verdes.
- **Branching**: 2 PRs encadenados contra `develop`, chain strategy `stacked-to-main`. PR #65 mergeado a `develop` antes que PR #66. PR #66 con rebase post-#65 (resolvió un conflicto trivial de `openspec/changes/breadcrumb-dinamico/tasks.md`).
- **Strict TDD**: 11 + 17 = 28 tests siguiendo RED → GREEN. Hay un fix-up commit post-rebase que corrigió un bug de integración del agente original (`zustand/vanilla` vs `zustand/react`).
- **Breaking fix en CI**: el primer push de PR #66 pasó vitest pero rompió `tsc -b` en el build (`resolveSecond()` con 0 argumentos vs tipo `(value: Response | PromiseLike<Response>) => void`). Se corrigió el tipado a `(value?: Response) => void` y CI pasó en el segundo intento.
- **Cleanup post-merge**: hay que borrar `../taxon-worktrees/breadcrumb-dinamico-pr1/` (PR #65) y `../taxon-worktrees/breadcrumb-dinamico-pr2/` (PR #66) ahora que ambos mergearon.
