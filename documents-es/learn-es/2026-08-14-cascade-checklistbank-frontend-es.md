# El frontend del cascade se conecta a ChecklistBank (PR #42)

## What

El `Cascade` de React ahora consume el backend de ChecklistBank
`COL2024` a través del endpoint path-aware `/api/path-children` que
expuso la cadena `cascade-checklistbank`. El primer desplegable
muestra Biota + Viruses (los dos taxones del tier superior que CLB
publica), y cada selector siguiente avanza el path un nivel del
cascade con una etiqueta en mayúsculas inferida del `next_rank_hint`
que devuelve el backend.

El mismo PR corrige el bug del resolver que rompía todo path que
empezara con `["Biota"]`: el resolver ahora hace un atajo hacia el
tier raíz con `get_taxon("5T6MX")` / `get_taxon("V")` porque CLB
devuelve HTTP 400 cuando se filtra `/nameusage/search` con
`rank=biota`.

## Why

Los PRs #34 / #36 / #37 / #38 / #40 trajeron el cliente CLB, el
resolver path-aware con la regla de colapso del subphylum, y el swap
del router. El frontend era la última rebanada de la cadena y había
quedado bloqueado hasta que llegara el backend. Al revisar la
rebanada, el smoke test reveló que la cadena resuelta estaba rota en
la raíz: cualquier request `?path=Biota` explotaba con
`HTTPStatusError 400` porque el resolver buscaba CLB con
`rank=biota`, que CLB no soporta. El cascade entero estaba
muerto-al-llegar contra el backend nuevo.

Mergear primero la rama en vuelo `feat/cascade-checklistbank-router`
nos dio un backend estable (179/179 pytest) sobre el cual reproducir,
corregir y verificar el wiring.

## How

### Atajo del tier raíz en el backend (`taxon/api/clb_path_children.py`)

El walk empezaba siempre con `client.search(segment, rank="biota")`.
CLB rechaza eso con HTTP 400 porque el tier raíz no se puede buscar
por su cuenta. El nuevo `_resolve_deepest` resuelve el primer
segmento contra `_ROOT_TAXON_BY_NAME` (un dict de dos entradas que
mapea `"biota"` y `"viruses"` a los ids conocidos
`"5T6MX"` y `"V"`), llama a `client.get_taxon(root_id)` directo y
después avanza al search rank-anchored estándar para los segmentos
restantes.

```python
_ROOT_TAXON_BY_NAME: dict[str, str] = {
    "biota": "5T6MX",
    "viruses": "V",
}

if root_id := _ROOT_TAXON_BY_NAME.get(segments[0].lower()):
    current = client.get_taxon(root_id)
    ...
```

CLB publica el tier raíz con `rank="unranked"`, no `rank="biota"`.
El mapeador de tier siguiente `_next_tier_for` hacía un lookup
directo contra `CASCADE_TIERS`. Con el atajo devolviendo filas con
rank `unranked`, el lookup fallaba. La corrección:

```python
def _normalize_root_rank(rank: str) -> str:
    if rank.lower() == "unranked":
        return "biota"
    return rank
```

`_next_tier_for` lo llama antes del lookup para que un único espacio
de claves cubra todo el tuple.

### Tests del backend (`taxon/tests/test_clb_path_children.py`)

`test_root_path_returns_biota_children` se reescribió: en vez de
mockear `/nameusage/search?q=Biota&rank=biota` (que CLB rechazaría en
producción), el test ahora mockea `/nameusage/5T6MX` con un payload
de fila plana-luego-anidada y verifica que el resolver camina a
través de `get_taxon` hasta los siete reinos mediante
`/tree/5T6MX/children?rank=kingdom`.

`test_root_path_returns_viruses_children` es nuevo y refleja el test
de Biota contra la raíz Viruses. Ambos usan un helper nuevo
`_get_taxon_200` que emite la forma anidada
`name.scientificName + name.rank` que devuelve
`GET /nameusage/{id}` de CLB (la forma plana-luego-anidada es la
misma que maneja el parser).

### Wiring del frontend (`frontend/src/api.ts`, `frontend/src/components/Cascade.tsx`)

`api.ts` ahora expone `fetchRoots()` y mantiene `fetchKingdoms`
como alias deprecado. La URL del endpoint no cambió; el renombre
hace honesto el contrato ("CLB devuelve roots del cascade — el UI
del cascade hace el bucketing") y protege a quien llama de leer
`TaxonResponse[]` como filas con rank reino.

`Cascade.tsx` renderiza un desplegable por segmento del path en un
solo loop, más un slot final para el `next_rank_hint` más profundo.
El indexado del loop es `parentPrefix = state.path.slice(0, i)` y
el selector en el índice `i` muestra los hijos de
`state.levelByPath[parentKey]`. El tier raíz Biota se convierte en
"Biota" con las dos filas raíz de CLB; el slot final capitaliza
el `next_rank_hint` para que las etiquetas queden estables en todo
el tuple de 9 niveles (`"phylum" → "Phylum"`, `"subphylum" → "Subphylum"`).

### Tests del frontend

`cascadeRoots.test.tsx` y `cascadeSubphylum.test.tsx` son nuevos y
cubren las dos adiciones al contrato (render del tier raíz y el flujo
`next_rank_hint` → etiqueta capitalizada). `api.test.ts` ganó un test
del happy-path de `fetchRoots` más un test del alias deprecado.

Los archivos con sufijo `.legacy` del PR anterior se habían marcado
así para evitar que corrieran contra el nuevo contrato tras la
migración GBIF→CLB. Los dos que todavía tenían señal útil
(`Cascade.pathAware.test.tsx`, `Cascade.ui.test.tsx`) se
resucitaron con el tier raíz Biota y el tuple de 9 niveles.
`CascadeFocus.test.tsx.legacy` era bookkeeping puro y se eliminó.

## Where

- `taxon/api/clb_path_children.py` — atajo del tier raíz, `_normalize_root_rank`.
- `taxon/tests/test_clb_path_children.py` — test de Biota actualizado, test de Viruses nuevo, helper `_get_taxon_200` nuevo.
- `frontend/src/api.ts` — `fetchRoots` + alias `fetchKingdoms` + docstring de módulo documentando la cadena.
- `frontend/src/components/Cascade.tsx` — loop de render N+1 desplegables, helper `capitalize`.
- `frontend/tests/cascadeRoots.test.tsx` — nuevo.
- `frontend/tests/cascadeSubphylum.test.tsx` — nuevo.
- `frontend/tests/api.test.ts` — tests de `fetchRoots` + alias.
- `frontend/tests/Cascade.pathAware.test.tsx` — resucitado de `.legacy`, actualizado al tier raíz Biota.
- `frontend/tests/Cascade.ui.test.tsx` — resucitado de `.legacy`, actualizado al tier raíz Biota.

## Verification

- Backend `pytest taxon/tests/` — 179/179 verde.
- Frontend `vitest` — 61/61 verde.
- `tsc --noEmit` limpio.
- `eslint .` limpio.
- `npm run build` limpio.
- CI: 4/4 jobs verde en el PR (backend 3.11, backend 3.12, frontend node 20, lighthouse a11y).
- Smoke test manual con Playwright contra el dev server en vivo:
  - Biota → Animalia carga 34 phyla (vs 4 con GBIF).
  - Animalia → Chordata carga tres clases de Chordata
    (Cephalochordata, Tunicata, Vertebrata).

## Workflows

- **Branching**: PR #42 siguió a `develop` como base de integración según AGENTS.md §4. Path del worktree `../taxon-worktrees/cascade-checklistbank-frontend`.
- **Forma del commit**: un solo commit `feat(cascade): wire frontend to ChecklistBank cascade backend` (un merge commit + el merge de `feat/cascade-checklistbank-router` para traer el backend). Según `work-unit-commits`, la unidad de trabajo cubre una rebanada revisable: el fix del bug y el wiring viajan juntos porque el wiring no podría sobrevivir sin el fix.
- **TDD**: el fix del backend siguió TDD estricto — `test_root_path_returns_biota_children` fallando primero, impl en `_resolve_deepest`, verde. Misma forma para Viruses.

## Lecciones aprendidas

- **CLB no busca el tier raíz.** Cuando el tuple documentado del
  cascade tiene un rank que *de jure* es parte del dataset pero
  *de facto* está fuera del índice de búsqueda, el resolver debe
  conocer ese caso a través de un id hardcodeado y no del walk
  general por nombre. La generalización del walk ("buscar por
  nombre + rank-anchor") se rompe en la raíz porque CLB no le
  asignó al tier raíz un rank linneano; el cascade tuvo que
  modelar esa brecha de forma explícita.
- **Las etiquetas de rank que publica CLB no coinciden con el tuple del cascade.** El tier raíz se publica como `rank="unranked"`, no como `rank="biota"`. El resolver asumía igualdad entre ambos. Centralizar la normalización del rank en un solo helper (`_normalize_root_rank`) deja consistente el resto del espacio de claves del resolver — todos los demás ranks que devuelve CLB mapean limpiamente al tuple del cascade.
- **Siempre correr el smoke test contra el backend en vivo antes de abrir el PR.** Los tests unitarios de `test_root_path_returns_biota_children` habían estado verdes por meses aunque el path de producción `?path=Biota` era un 400. Los mocks para la forma equivocada (basada en `search`) escondían el bug. Los smoke tests manuales contra CLB real son la única forma de hacer aflorar este tipo de drift de contrato; la regla a futuro: cualquier cambio en el resolver necesita un smoke test manual en el browser, incluso cuando los tests unitarios estén verdes.
- **El renombre a `.legacy` fue una señal, no una eliminación.** Cuando se renombra un archivo de test a `.legacy` para evitar que sus aserciones corran contra un contrato nuevo, la carga de resucitarlo recae sobre quien toque el código legacy. Dos de los tres archivos legacy de este PR seguían siendo útiles y se actualizaron; el tercero era bookkeeping y se eliminó.

## Follow-ups (no incluidos en este commit)

- **Issue #43** — el tuple de 9 niveles del cascade no nombra
  `infraphylum` ni `parvphylum`, dos rangos que CoL publica entre
  subphylum y class. El cascade se muere en Chordata → Vertebrata →
  Agnatha / Gnathostomata. El issue lista tres enfoques; este PR
  corrige el blocker aguas arriba (400 del tier raíz) y aterriza el
  wiring del frontend, pero no toma posición sobre el problema del
  infraphylum.
- **Limpieza de artefactos en el checkout principal.** `pencil.pen`,
  `.playwright-mcp/`, `cascade-animalia-select.png`, y el
  `.atl/skill-registry.md` auto-regenerado quedaron sueltos al
  crear la rama del worktree. PR de limpieza aparte.
