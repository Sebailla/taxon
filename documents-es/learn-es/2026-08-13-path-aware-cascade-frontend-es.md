# Frontend del cascade path-aware (PR #29)

# Qué

Se refactorizó el componente Cascade: pasó de una escalera fija
de seis ranks (Kingdom → Phylum → Class → Order → Family →
Genus → Species) a un render dinámico de N dropdowns dirigido
por los endpoints path-aware del backend (`/api/path-children` y
`/api/species-list`).

El nuevo componente recorre el path seleccionado por el usuario
segmento a segmento. Cada segmento le pregunta al backend por
los hijos del taxon más profundo que resolvió, más un
`next_rank_hint` que etiqueta el siguiente dropdown. Cuando
`next_rank_hint` es `null`, el cascade llegó a un genus y carga
automáticamente la lista de especies vía `/api/species-list`.

# Por qué

Después del re-seed de CoL (PR #26) el backend expuso los
endpoints path-aware (PR #27, PR #28) pero el frontend seguía
asumiendo la escalera legacy de seis ranks fijos. El cascade
devolvía listas vacías para todo path con ranks intermedios
(subphylum, infraphylum, gigaclass, parvphylum, ...).

El frontend necesitaba trackear un número arbitrario de ranks y
dejar que el backend etiquetara los dropdowns con lo que el
dataset tuviera, en vez de hardcodear las etiquetas.

# Cómo

## State machine — `frontend/src/components/Cascade.state.ts`

El reducer se extrajo del componente para poder testearlo en
aislamiento. La forma del state:

- `path: string[]` — lista densa de nombres canónicos que el
  usuario eligió hasta ahora. Vacío significa "mostrar el
  dropdown de Kingdom raíz".
- `levelByPath: Record<string, LevelSnapshot>` — snapshot por
  prefijo de path. Las keys son `path.join("|")`. La primera
  key es `""` (lista de kingdoms raíz); cada key subsiguiente
  extiende el path en un segmento. El cascade renderiza un
  dropdown por key en orden de inserción.
- `species: TaxonResponse[]` — se carga por separado cuando el
  cascade llega a un genus (el snapshot más profundo tiene
  `next_rank_hint === null`).

El reducer:

- `set-path` — conserva los snapshots de los prefijos que siguen
  siendo válidos; descarta todo lo que esté estrictamente más
  allá del nuevo largo de path. Inserta un placeholder
  `{children: [], nextRankHint: undefined}` para el nuevo path
  más profundo, así el dropdown puede renderizar el placeholder
  "Loading children…" mientras el fetch está en vuelo. Resetea
  `speciesStatus` a "loading" para que el SpeciesList de abajo
  no muestre un estado stale de "No children.".
- `set-current-level` — cachea el snapshot fetcheado bajo su key
  de path, para que los dropdowns ancestros sigan poblados
  después de un pick descendiente.
- `set-current-level-status` — flippea el status async a
  "error" cuando el último fetch devolvió un resultado no-OK.
- `set-include` — actualiza los toggles de inclusión (synonyms,
  extinct, uncertain, unassigned).
- `set-species` + `set-species-status` — puebla la lista de
  especies y limpia el estado de loading.

## Componente — `frontend/src/components/Cascade.tsx`

Dos `useEffect`s llevan el ciclo de vida:

1. **Path-children effect** — se dispara en cada cambio de
   `state.path`. Llama a `fetchPathChildren(densePath(state.path))`
   y dispatcha `set-current-level` con la respuesta. Aborta los
   requests en vuelo cuando una nueva selección los supera
   (cleanup con `AbortController`).
2. **Species-list effect** — se dispara en cada cambio de
   `state.path`/`state.levelByPath`/`state.include`. Retorna
   temprano cuando el path está vacío o cuando falta el snapshot.
   Retorna temprano cuando `nextRankHint !== null` (todavía no
   es una hoja) o cuando el snapshot no tiene hijos con rank
   "species" (la hoja es un taxon que no es genus). Sólo cuando
   el snapshot más profundo es un genus confirmado con hijos
   especie llama a `fetchSpeciesList`.

El render produce N dropdowns:

- Para el path vacío, un único dropdown "Kingdom".
- Para un path no vacío, un dropdown por segmento de path (el
  dropdown en el índice `i` muestra los hijos del taxon en
  `path.slice(0, i)` — el snapshot bajo el prefijo previo).
  Después del loop, un dropdown `next` muestra los hijos del
  taxon más profundo que resolvió, para que el usuario tenga
  una única forma no ambigua de extender el path.

Cada dropdown lleva una etiqueta visible y un `aria-label`. Los
dropdowns deshabilitados llevan `disabled` para que los screen
readers anuncien la indisponibilidad. El comportamiento previo
de focus `disabled → enabled` (PR #18) se mantiene por el
follow-up del audit de a11y.

## API client — `frontend/src/api.ts`

Dos helpers nuevos:

- `fetchPathChildren(parentSegments, init)` — llama a
  `GET /api/path-children?path=<segments>` (segmentos unidos
  con `|`, cada uno URL-encoded). Resuelve a
  `ApiResult<PathChildrenResponse>`.
- `fetchSpeciesList(pathSegments, init)` — llama a
  `GET /api/species-list?path=<segments>` con query params
  opcionales `include` y `cursor`. Resuelve a
  `ApiResult<SpeciesListResponse>`.

El helper `encodeSegments` legacy (usado por los seis endpoints
legacy de rank fijo) queda intacto. Los helpers path-aware
usan un `.join("|")` aparte porque el backend espera `|` como
separador de segmentos en el query string.

# Dónde

- `frontend/src/components/Cascade.tsx` — rewrite, 320 líneas.
- `frontend/src/components/Cascade.state.ts` — nuevo, 175
  líneas. Reducer puro + helpers, sin imports de React,
  testeable en aislamiento.
- `frontend/src/api.ts` — agregado el tipo `PathChildrenResponse`,
  `fetchPathChildren`, `fetchSpeciesList`.
- `frontend/tests/Cascade.pathAware.test.tsx` — nuevo, 309
  líneas, 4 tests: init render, cadena a través de ranks
  intermedios, llega a species después de un genus, resetea
  hijos en cambio de parent.
- `frontend/tests/Cascade.ui.test.tsx` — nuevo, 231 líneas, 3
  tests: estado de loading por dropdown, estado de children
  vacíos, toggles de inclusión disparan el fetch de species.
- `frontend/tests/Cascade.test.tsx.legacy` — specs viejos de
  seis ranks, renombrados.
- `frontend/tests/CascadeFocus.test.tsx.legacy` — spec viejo de
  `/api/kingdoms`, renombrado.

# Verificación

- `npm test` (Vitest) — 55/55 passing.
- `npm run typecheck` (tsc --noEmit) — clean.
- `npm run lint` (eslint) — clean.
- `npm run build` (Vite production build) — succeeds.
- CI — 4 jobs green: backend 3.11, backend 3.12, frontend,
  lighthouse.

# Workflows

- **CI** — el mismo workflow de 4 jobs que antes. No se
  añadieron jobs.
- **Reviews** — 2 `work-unit-commits`:
  1. `426c917 test(frontend): mark legacy six-rank cascade specs
     as historical` — renombra los specs obsoletos a `.legacy`
     para que el test discovery los salte.
  2. `4b193d9 feat(frontend): wire cascade to the path-aware
     backend API` — el refactor del cascade con tests RED-first
     incluidos.
- **Smoke test manual** — la UI del cascade ahora recorre los
  ranks intermedios de CoL. La cadena
  `Animalia → Chordata → subphylum Vertebrata → genus Gadus →
  species Gadus morhua` aterriza la especie en el SpeciesList
  con los toggles de inclusion preservados.

# Aprendizajes

- **Race condition del select disabled.** `findByRole("combobox",
  { name: "Kingdom" })` de Vitest devuelve el *primer* elemento
  que matchea, que es el placeholder disabled. La siguiente
  llamada `selectOptions` falla porque el select está disabled.
  El fix es esperar por el option, no por el combobox:
  `await screen.findByRole("option", { name: "Animalia" });
  await user.selectOptions(screen.getByRole("combobox",
  { name: "Kingdom" }), "Animalia")`. La primera llamada espera
  a que el fetch en vuelo resuelva; la segunda es un `getByRole`
  sincrónico contra el select ya habilitado. Este patrón era
  flaky en CI antes del fix.

- **Mocks deterministas vía cadenas de `mockResolvedValueOnce`.**
  El test previo mockeaba la función fetch con un único
  `mockImplementation` que ramificaba por URL. El orden de las
  ramas era frágil: un único reorden rompía la suite. Reemplazar
  la escalera de `if` por una cadena de `mockResolvedValueOnce`
  atada al orden de disparo (kingdom inicial → Animalia →
  Chordata → subphylum → genus → species list) hizo al test
  determinista y auto-documentado.

- **State machine extraído deja al componente flaco.** Mover el
  reducer a `Cascade.state.ts` bajó al componente de un único
  archivo enredado a un render limpio + dos useEffects. El
  reducer ahora es HMR-friendly en Vite (sin imports de React
  significa que `react-refresh` no se queja) y la lógica
  path-aware es testeable en aislamiento sin DOM.

- **El reducer no ve la respuesta; el useEffect sí.** El reducer
  es puro y sincrónico. El `useEffect` es el que fetchea y
  dispatcha. Esta separación dejó al reducer simple y a los
  fixtures de test triviales — un test que exercita el reducer
  sólo pasa acciones y assertea sobre el state resultante.

- **El dropdown `next` es el picker, no un display.** El dropdown
  en el índice `i` muestra los hijos del taxon en
  `path.slice(0, i)` — o sea, el usuario puede re-seleccionar el
  mismo segmento para cambiar el parent. El dropdown `next` es
  distinto: muestra los hijos del taxon más profundo que resolvió
  y es el affordance para extender el path. Mezclar los dos
  (i.e. reusar el último dropdown del loop como picker) lleva a
  una UX confusa donde el usuario no puede distinguir cuál
  dropdown es "el siguiente".

# PRs follow-up (no en este commit)

- **PR #27c** — deprecar los seis endpoints legacy de rank fijo
  (`/api/{kingdom}/phyla`, `/api/{kingdom}/{phylum}/classes`,
  etc.) una vez que la migración del frontend esté estable en
  producción. Agregar un warning de deprecación a la response,
  removerlos después de un release.
- **PR #27d** — reemplazar el dropdown `next` por un picker
  "Continue" que abra una lista de autocompletado del siguiente
  segmento. La implementación actual renderiza un dropdown por
  ancestro más el picker `next`; un autocompletado coalescente
  reduciría la UI para cadenas muy profundas.
