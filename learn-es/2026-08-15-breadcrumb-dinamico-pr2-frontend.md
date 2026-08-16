# Breadcrumb dinámico — frontend slice (PR #66)

## Qué

Frontend para que los segmentos del breadcrumb sean botones clickeables que abren la grilla 4×3 de 13 enlaces de búsqueda de cualquier taxón intermedio (no solo de la especie final). Acompaña a PR #65 (backend slice) como segundo eslabón del change SDD `breadcrumb-dinamico`.

## Cómo

- Store zustand `cascadePath` reexporta `useCascadePath` desde `zustand` (paquete raíz, no `zustand/vanilla`) para que sirva como hook selector (`useCascadePath((s) => s.path)`) Y como store vanilla (`useCascadePath.getState().setPath(...)`). El flag `arraysEqual` evita reemplazar el array cuando el contenido es idéntico, así un `setPath` redundante no refire subscribers.
- `Cascade.tsx` despacha `window.dispatchEvent(new CustomEvent("path:change", { detail: { path: state.path } }))` cada vez que `state.path` cambia. Implementado en un `useEffect` que depende de `state.path`. Cero impacto en la lógica del reducer.
- `Breadcrumb.tsx` cambia de `<span>` a `<button type="button">` por segmento, manteniendo chevron + `font-mono` + `bg-surface`. El segmento más profundo lleva `aria-current="page"`. Nueva prop opcional `onSelect?: (path: string[]) => void`. El default es no-op para no romper consumidores existentes.
- `App.tsx` mantiene un `breadcrumbLinks` (discriminated union: idle | loading | ok | error | not-found). Un `useEffect` keyed por `cascadePath.join("|")` llama `fetchTaxonLinks(cascadePath, { signal: ctrl.signal })` con un `AbortController` por panel, y `abort()` en el cleanup. Cuando llega `taxon:select`, se limpia el panel para que el `SpeciesLinks` ocupe su lugar (last-clicked wins).
- `fetchTaxonLinks` (en `frontend/src/api.ts`) usa el mismo `ApiResult<T>` discriminated union que el resto del cliente. URL pattern: `/api/{path}/taxon-links` con segmentos separados por `%7C` y los caracteres reservados de RFC 3986 (`!'()*`) post-encodeados.

## Dónde

- `frontend/src/store/cascadePath.ts` — store zustand `create<CascadePathState>((set) => ({...}))`.
- `frontend/src/api.ts` — interface `TaxonLinksResponse` y función `fetchTaxonLinks(pathSegments, init?)`.
- `frontend/src/components/Breadcrumb.tsx` — segmentos como `<button>`, `onSelect`, `aria-current`.
- `frontend/src/components/Cascade.tsx` — `useEffect` que despacha el CustomEvent `path:change`.
- `frontend/src/App.tsx` — `breadcrumbLinks` state, `useEffect` con `AbortController`, panel rendering.
- `frontend/package.json` — `"zustand": "^5.0.0"` agregado.
- `frontend/tests/Breadcrumb.dynamic.test.tsx` — 4 tests (click en profundo, click en primero, sin handler, aria-current).
- `frontend/tests/store.cascadePath.test.ts` — 4 tests (default, setPath, subscribe, no-op replace).
- `frontend/tests/api.taxonLinks.test.ts` — 4 tests (200 ok, 404 not-found, %7C encoding, 5xx error).
- `frontend/tests/App.taxonLinks.test.tsx` — 2 tests (panel renders 13 links, AbortController race).
- `frontend/tests/cascadeDynamicTiers.test.tsx` — agregados 2 tests para el path:change dispatch.

## Por qué

El backend slice (PR #65) ya emite `TaxonLinksResponse{taxon, links}` para cualquier segmento del cascade, pero sin consumidor de UI el cambio era invisible. Este PR le da al usuario el affordance: clickear cada eslabón del breadcrumb para abrir los 13 enlaces referidos al nombre de ese taxón. Es la mitad visible del feature; la otra mitad (filesystem + explorer embebido + switches por link) queda para `species-folder-explorer` en un change separado.

## Cómo funciona en producción

1. El usuario abre la app y hace click en la primera dropdown del cascade. `Cascade.tsx` cambia `state.path` y dispara un `path:change` con `detail.path = ["Biota", "Animalia"]`.
2. `App.tsx` recibe el evento, actualiza el slice de zustand y su `useEffect` arranca: `fetchTaxonLinks(["Biota", "Animalia"], { signal })` → `/api/Biota%7CAnimalia/taxon-links`.
3. La respuesta se traduce por `apiGet` a `ApiResult.ok({taxon: Animalia, links: 13 items})`, y el `<aside>` re-renderiza el `<SpeciesLinks links={data.links}>` reutilizando el componente existente (cero cambios en `SpeciesLinks`).
4. Mientras el fetch está vivo, si el usuario cambia otra dropdown, `Cascade.tsx` despacha otro `path:change` con path distinto, el `useEffect` cleanup corre `ctrl.abort()` sobre el fetch previo y arranca el nuevo. Solo sobrevive un fetch en vuelo.
5. Click en un segmento del breadcrumb invoca `onSelect(trail.slice(0, idx+1))`. El Cascade reducer ya tiene el path actualizado por el click; `onSelect` queda cableado para futuros puntos de instrumentación.
6. Cuando el usuario resuelve una especie vía `taxonSelect`, `setResolved` limpia el panel breadcrumb-links y monta el panel de enlaces de especie encima.

## Workflows

- **Stacked PR**: rebased contra `develop` después del merge de PR #65. Conflicto trivial en `openspec/changes/breadcrumb-dinamico/tasks.md` resuelto combinando las marcas `[x]` de Phase 1+2 (PR #65) y Phase 3+4 (PR #66) en un solo archivo.
- **Force-push**: sí, post-rebase. Permitido por AGENTS.md §4 (worktree keep-alive pattern).
- **CI fix-loop**: el primer push rompió el typecheck (`resolveSecond()` con 0 args). Se corrigió en un fix-up commit `cae8ef8` (tipado a `(value?: Response) => void`).
- **Tests verde**: 86/86 vitest (69 baseline + 17 nuevos). Typecheck + lint limpios. Build producción OK.
- **Cleanup post-merge**: borrar `../taxon-worktrees/breadcrumb-dinamico-pr2/`.
