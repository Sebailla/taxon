# Diseño: cascade-checklistbank

## Enfoque técnico

Sustituir la API de Especies de GBIF en el backend de la cascada por
el dataset `COL2024` de ChecklistBank. El pivote corrige un fallo en
la prueba de humo en el que la backbone de GBIF sólo devolvía cuatro
phyla bajo `Animalia`; CLB expone 34 además de la raíz `Biota`
(previamente ausente) y del nivel `subphylum`. El alcance del cambio
es integral: nuevo cliente HTTP, nuevo resolvedor path-aware con
una tupla de nueve niveles (Biota + subphylum), router reconectado
y, por último, un slice de frontend que añade el dropdown de Biota y
la etiqueta de subphylum. El backend aterriza como tres PR encadenados
(cliente, resolvedor, swap del router + borrados), y luego el PR #4
añade la UI bajo la puerta de Pencil + `impeccable`.

## Decisiones de arquitectura

| Decisión | Elección | Tradeoff | Justificación |
| --- | --- | --- | --- |
| Nombre del módulo cliente | `taxon/checklistbank.py` (nuevo) + borrar `taxon/gbif.py` | Renombrar duplica el churn del diff pero elimina código muerto | El PR #3 ya es destructivo; renombrar aquí es el momento más barato. Las personas revisoras ven un solo renombrado en vez de tres. |
| Nombre del módulo resolvedor | `taxon/api/clb_path_children.py` (nuevo) + borrar `gbif_path_children.py` | Mismo trade-off que arriba | Coherente con el renombrado del cliente. |
| Estrategia del walk del resolvedor | `/tree/{id}/children` con match por nombre (sin `higherTaxonKey`) | Dos llamadas por segmento en vez de una de GBIF — más red | La búsqueda de CLB carece del filtro de anclaje por padre; el walk debe componer búsqueda por nombre + hijos por id. La caché por nivel es un follow-up. |
| Tupla de niveles | 9 niveles `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` | Subphylum añade un slot de nivel que la UI debe renderizar | Decisión fijada en la propuesta. El reducer agnóstico al path de la UI absorbe el nuevo nivel sin cambio de lógica. |
| Regla de colapso de subphylum | Cuando un phylum no tiene hijos subphylum, devolver clases directamente con `next_rank_hint="order"` | Slot de subphylum vacío en el dropdown | CLB tiene subphyla bajo Chordata (3) pero Arthropoda (0); el resolvedor debe saltar el nivel vacío sin un segundo round-trip. |
| Clave de dataset | Fijar `COL2024`; `3LR` documentado como comentario en el código | La clave fijada bloquea la cascada a una release anual | Reproducibilidad + ruta de upgrade de una línea. CoL libera una vez al año; el bump es una constante. |
| Swap del router | `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)`; borrar la dep antigua | Un renombrado, un borrado | Requerido por el renombrado del módulo. El override de la dependencia en los tests lo sigue. |
| División del PR #2 | Dividir en PR #2a (walk principal del resolvedor) + PR #2b (colapso de subphylum) | Más PR a revisar | Ambos superan por sí solos el presupuesto de 400 líneas. Dividir mantiene cada slice revisable. |
| Inferencia de etiquetas en el frontend | El backend transporta `next_rank_hint`; el frontend ya capitaliza | No se necesita tabla de etiquetas | El backend emite un string estable por nivel; la UI no ramifica por rango. Los nuevos rangos ("subphylum", "biota") se absorben por la ruta existente de capitalizar-y-renderizar. |

## Flujo de datos

```
    Navegador               Router FastAPI             ChecklistBankClient      api.checklistbank.org
    ---------               ---------------             -------------------      ----------------------
  fetchRoots() ───────────► GET /api/kingdoms       ──► GET /dataset/COL2024/tree ──►
                             (devuelve Biota+Viruses)     parse → TaxonResponse[]
  fetchPathChildren(path) ► GET /api/path-children ──► list_path_children ─────►
                                                         ├─ _resolve_deepest ────► GET /nameusage/search?q=&rank=
                                                         └─ _children_for ──────► GET /tree/{id}/children?rank=
                                                                                    (sondeo subphylum + sondeo class)
  fetchSpeciesList(path)  ► GET /api/species-list  ──► mismo resolvedor + rank="species"
```

`_resolve_deepest` recorre `segments` alternando búsqueda (para
vincular un nombre a un id) y `/tree/{id}/children` (para encontrar
el id padre de ese id para el siguiente segmento). `_children_for`
implementa el colapso de subphylum: sondea `/tree/{id}/children` con
`rank=subphylum`, y cuando la respuesta está vacía re-sondea con
`rank=class` y emite `next_rank_hint="order"`.

## Cambios de archivos

| Archivo | Acción | Descripción |
| --- | --- | --- |
| `taxon/checklistbank.py` | Crear | Cliente CLB (`ChecklistBankClient`) + dataclass `ChecklistBankTaxon`. Métodos: `get_taxon`, `get_children`, `search`, `_request`. Refleja la forma del cliente GBIF para que las personas revisoras familiarizadas con `taxon/gbif.py` puedan diffear lado a lado. ~200 LOC. |
| `taxon/api/clb_path_children.py` | Crear | Resolvedor de 9 niveles con raíz Biota + colapso de subphylum. Refleja la forma de `taxon/api/gbif_path_children.py`: `list_path_children` + `PathChildrenResponse` + `_resolve_deepest` + `_children_for` + `_to_taxon_row`. ~280 LOC. |
| `taxon/api/router.py` | Modificar | `/api/kingdoms`, `/api/path-children`, `/api/species-list` rebindean `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)`; los bodies llaman al resolvedor CLB. Añadir la dependencia `_get_checklistbank_client`. |
| `taxon/gbif.py` | Borrar | Sustituido por `taxon/checklistbank.py` en el PR #3. |
| `taxon/api/gbif_path_children.py` | Borrar | Sustituido por `taxon/api/clb_path_children.py` en el PR #3. |
| `taxon/tests/test_checklistbank.py` | Crear | `_StubClient` mockea `/dataset/COL2024/tree/{id}/children` + `/dataset/COL2024/nameusage/search`. RED-first: 9–10 tests. ~250 LOC. PR #1. |
| `taxon/tests/test_clb_path_children.py` | Crear | Tests del resolvedor: raíz Biota, bucket subphylum (Chordata 3, Arthropoda 0), cadena completa de Mammalia, dedup por id opaco. RED-first: 11–12 tests. ~350 LOC. PR #2. |
| `taxon/tests/test_api_clb_router.py` | Crear | Integración del router: root devuelve Biota+Viruses; path-children recorre la tupla de 9 niveles. ~200 LOC. PR #3. |
| `taxon/tests/test_gbif.py`, `test_gbif_path_children.py`, `test_api_gbif_router.py` | Borrar | Sustituidos por los tests CLB en el PR #3. |
| `frontend/src/api.ts` | Modificar | `fetchKingdoms` → `fetchRoots` (devuelve Biota + Viruses). PR #4. |
| `frontend/src/components/Cascade.tsx` | Modificar | Inferencia de etiqueta para `"subphylum"` y `"biota"` (capitalizar + renderizar). Sin cambio en el reducer. PR #4. |
| `frontend/tests/api.test.ts`, `Cascade.pathAware.test.tsx`, `Cascade.ui.test.tsx` | Modificar | Los mocks de paths añaden Biota; esperan el slot subphylum. PR #4. |
| `taxon.pen` | Modificar | Un slot extra de dropdown para Biota + etiqueta subphylum. Sólo Pencil MCP; revisión `impeccable` antes de que aterrice el código. PR #4. |
| `openspec/changes/cascade-checklistbank/design.md` | Crear | Este documento. |
| `documents-es/openspec/changes/cascade-checklistbank/design-es.md` | Crear | Espejo en español (traducción fiel, neutra/profesional). |

## Interfaces / Contratos

```python
# taxon/checklistbank.py

DATASET_KEY: str = "COL2024"            # Upgrade futuro: cambiar a "3LR" (última release).
CLB_BASE_URL: str = "https://api.checklistbank.org"

@dataclass(frozen=True)
class ChecklistBankTaxon:
    id: str                            # ID opaco de CLB, p. ej. "5T6MX", "CH2".
    name: str                           # Nombre canónico, p. ej. "Chordata".
    label_html: str                     # Etiqueta visible con marcado HTML.
    parent_id: str | None               # ID opaco del padre.
    count: int | None                   # Conteo total de descendientes.
    child_count: int | None             # Conteo de hijos directos.
    authorship: str | None              # Citación de autoría (verbatim).
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

El esquema público de respuesta (`PathChildrenEnvelope`,
`TaxonResponse`, `SpeciesListItem`) no cambia — sólo cambian los
tipos de los campos `id` y `parent_id` de `int` a `str`. El cambio de
contrato del frontend en el PR #3 (ensanchamiento del tipo `id`) es
el único shift de API visible; se tipifica en el lado React vía
`TaxonResponse.id: number | string`.

## Algoritmo de walk del resolvedor

```
_resolve_deepest(segments, client):
    parent_id = None
    current = None
    for depth, segment in enumerate(segments):
        # Paso 1: vincular el nombre del segmento a un id de CLB.
        rank = _rank_for_depth(depth)        # biota, kingdom, phylum, ...
        hits = client.search(segment, rank=rank)
        hit = first(hits, name == segment)   # match case-insensitive
        if hit is None: return current
        current = hit
        parent_id = hit.id
    return current

_children_for(current, client):
    next_rank = _next_tier_for(current.rank)
    if next_rank == "subphylum":
        probe = client.get_children(current.id, rank="subphylum")
        if probe is empty:
            # Colapso: saltar subphylum, devolver clases directamente.
            classes = client.get_children(current.id, rank="class")
            return classes, "order"           # next_rank_hint = "order"
        return probe, "class"                 # next_rank_hint = "class"
    if next_rank is None:
        return [], None                       # hoja
    children = client.get_children(current.id, rank=next_rank)
    return children, next_rank.lower()        # next_rank_hint = next_rank

_next_tier_for(rank):
    "biota"     → "kingdom"
    "kingdom"   → "phylum"
    "phylum"    → "subphylum"  (colapsado a "class" en runtime cuando está vacío)
    "subphylum" → "class"
    "class"     → "order"
    "order"     → "family"
    "family"    → "genus"
    "genus"     → "species"
    "species"   → None
```

El colapso de subphylum **no** es recursivo: cuando un phylum no
tiene hijos subphylum y no tiene hijos class (clados fósiles raros),
el resolvedor devuelve una lista vacía con `next_rank_hint="order"`.
El frontend trata la lista vacía como una hoja.

## Regla de colapso de subphylum

| Phylum | Hijos subphylum | Comportamiento del resolvedor |
| --- | --- | --- |
| `Chordata` (`CH2`) | 3 (Cephalochordata, Tunicata, Vertebrata) | Devuelve subphyla, `next_rank_hint="class"` |
| `Arthropoda` | 0 | Colapsa: devuelve clases directamente, `next_rank_hint="order"` |
| Phylum fósil sin subphylum Y sin class | 0 + 0 | Devuelve lista vacía, `next_rank_hint="order"` — la cascada se detiene, el frontend renderiza un dropdown vacío. El resolvedor no entra en bucle. |

La regla de colapso es un sondeo único: el resolvedor consulta
`/tree/{id}/children?rank=subphylum` una vez. Si el resultado está
vacío, re-consulta con `rank=class` y reescribe `next_rank_hint`. No
hay descenso recursivo; la tupla de niveles sigue siendo una tupla de
9 en el código.

## Estrategia de testing

| Capa | Qué se prueba | Enfoque |
| --- | --- | --- |
| Unidad (PR #1) | Formas de request de `ChecklistBankClient`, parse, 404 → None | `httpx.MockTransport` + `_StubClient`; 9–10 tests RED-first |
| Unidad (PR #2) | `_resolve_deepest`, `_children_for`, colapso de subphylum | El cliente stub devuelve respuestas enlatadas de `/tree/{id}/children` y `/nameusage/search`; 11–12 tests |
| Integración (PR #3) | `/api/kingdoms` devuelve Biota+Viruses, `/api/path-children` recorre la tupla de 9 niveles | `TestClient` con `app.dependency_overrides[_get_checklistbank_client]`; 4 tests |
| Frontend (PR #4) | Forma de `fetchRoots`, Cascade renderiza N+1 dropdowns incluyendo subphylum | Vitest + jsdom; los mocks de fetch devuelven el nuevo envelope |
| Revisión Pencil | Jerarquía, accesibilidad, motion, anti-patrones | Skill `impeccable` sobre `taxon.pen` antes de que aterrice cualquier código de frontend |

## Matriz de amenazas

N/A — no hay frontera de routing, shell, subprocess, automatización
de VCS/PR, clasificación de archivos ejecutables ni integración de
procesos. El cliente HTTP envuelve una API pública de sólo lectura;
sin subprocesses, sin shell-out, sin clasificación de modo de
archivo. El CI es el pipeline pytest + Vitest existente.

## Migración / Rollout

- **Clave de dataset**: fijada `COL2024`. El bump anual es un cambio
  de una línea en la constante; `3LR` está documentado en el
  comentario del código cerca de `DATASET_KEY` como la ruta de
  upgrade.
- **Código GBIF muerto**: borrado en el PR #3.
  `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py"
  --include="*.ts" --include="*.tsx"` debe devolver cero hits tras
  el merge del PR #3.
- **URLs guardadas**: una ruta con forma GBIF (p. ej.
  `path=Animalia|Chordata|Mammalia|Carnivora|Felidae|Panthera`)
  pasa a ser una ruta con forma CLB (`...|Vertebrata|Mammalia|...`).
  Las URLs antiguas obtienen 404 con un mensaje claro; las personas
  usuarias vuelven a compartir con el nuevo segmento.
- **El rollback del PR #3** es destructivo; la propuesta documenta
  un PR de seguimiento que reintroduce `taxon/gbif.py`, los tres
  ficheros de tests y reconecta `taxon/api/router.py`.
- **El rollback del PR #4 de frontend** no es destructivo: revertir
  el merge; el backend se queda verde.

## Preguntas abiertas

Ninguna. Las tres decisiones fijadas (tupla de 9 niveles, raíz
Biota+Viruses, pin de COL2024) están en la propuesta; la regla de
colapso de subphylum está especificada en el delta del spec.

## Forecast de carga por PR

| PR | Título | Ficheros | LOC | Presupuesto (400) | Decisión |
| --- | --- | --- | --- | --- | --- |
| #1 | `feat(checklistbank): add CLB client and taxon parser` | `taxon/checklistbank.py` (~200) + tests (~250) | ~450 | Sobre | Dividir: parser + cliente en un commit; tests en el siguiente. `work-unit-commits` mantiene cada commit bajo el tope. |
| #2a | `feat(checklistbank): path resolver core walk` | `taxon/api/clb_path_children.py` (~280) + 5 tests (~140) | ~420 | Sobre (apenas) | División de commits vía `work-unit-commits`: módulo + dataclass en un commit, walk + 5 tests en el siguiente. |
| #2b | `feat(checklistbank): subphylum collapse rule` | lógica de colapso en el resolvedor + 6 tests (~250) | ~250 | Bajo | Commit único; slice limpio. |
| #3 | `feat(api): route cascade endpoints through CLB client` | rewrite de `router.py` + 4 tests (~200) − 1.200 borrados | −700 net | Bajo | PR destructivo; las personas revisoras confirman que el código muerto se elimina. |
| #4 | `feat(frontend): render Biota + subphylum in the cascade UI` | `api.ts` + `Cascade.tsx` (~150) + tests (~100) + diseño Pencil | ~250 + diseño | Bajo | Gateado por la revisión `impeccable`. |

Total: 5 PR (una división auto-chain), 4 backend + 1 frontend.
Decisión necesaria antes de apply: Sí (aprobar la división #2a/#2b).
PR encadenados recomendados: Sí.
Riesgo de presupuesto de 400 líneas: Bajo tras la división de #2.
