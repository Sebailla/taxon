# Backend del cascade path-aware (PR #27)

# Qué

Se añadió un nuevo endpoint `GET /api/path-children?path=A|B|C`
que recorre el path de nombres canónicos provisto por el
caller y devuelve los hijos directos del taxon más profundo que
resuelva, sin importar el nombre del rank. Es la mitad backend
del refactor de cascade path-aware que hace utilizable el
dataset de CoL con sus 40 ranks en la UI.

Los seis endpoints legacy de rank fijo
(`/api/Animalia/phyla`, `/api/Animalia/Chordata/classes`,
etc.) quedan disponibles y sin cambios para mantener
compatibilidad. Su deprecación y remoción es un PR follow-up.

# Por qué

Después del re-seed de CoL (PR #26) la UI del cascade se rompió
en el browser: `Chordata` tiene 0 hijos con rank `class` porque
sus hijos reales son subphyla (`Vertebrata`,
`Cephalochordata`, `Tunicata`). El resolver viejo imponía
`rank == 'class'` a esa profundidad y devolvía `[]`. Todo
path con ranks intermedios (subphylum, gigaclass, infraclass,
superorder, parvorder, ...) se rompe de la misma manera.

El endpoint nuevo no asume ningún orden de ranks. Recorre el
path case-insensitive, anclando en el parent en cada paso, y
devuelve los hijos que el taxon más profundo tenga realmente,
más un `next_rank_hint` (la moda del rank de los hijos) para
que el frontend pueda etiquetar el siguiente dropdown sin
hardcodear los seis ranks canónicos.

# Cómo

### Módulo: `taxon/api/path_children.py`

```python
def list_path_children(
    session: Session,
    segments: list[str],
) -> PathChildrenResponse | None:
    """Recorre segments hasta el taxon más profundo resuelto y
    devuelve sus hijos directos, sin importar el rank."""
```

El primer segmento se ancla en `rank == 'kingdom'` (así un
kingdom con el mismo nombre que otro taxon en otro lugar no
resuelve); los segmentos siguientes se anclan solo en
`parent_id == previous.id`. Devuelve `None` cuando algún
segmento falla — el router lo mapea a 404 con el segmento
fallido en el detail.

`PathChildrenResponse` carga:

- `parent`: el taxon más profundo resuelto (un `TaxonRow`).
- `children`: los hijos directos de `parent`, ordenados por
  name.
- `next_rank_hint`: la moda de los ranks de los hijos, así un
  set heterogéneo de hijos (algunos subphyla + varios
  microspecies unranked) recibe una etiqueta razonable.
  `None` cuando los hijos están vacíos (leaf node).

### Endpoint: `GET /api/path-children?path=A|B|C`

Cableado en `taxon/api/router.py` con un docstring que
documenta el contrato. Los pipes se URL-encodifican como `%7C`
en el frontend; FastAPI los decodifica automáticamente.

### Schema: `taxon/api/schemas.py` — `PathChildrenEnvelope`

El modelo de respuesta espeja `PathChildrenResponse` así el
schema de OpenAPI documenta el contrato.

# Dónde

- `taxon/api/path_children.py` — nuevo, 100 líneas.
- `taxon/api/router.py` — 45 líneas añadidas (el endpoint
  nuevo).
- `taxon/api/schemas.py` — 20 líneas añadidas
  (`PathChildrenEnvelope`).
- `taxon/tests/test_api_path_children.py` — nuevo, 339 líneas,
  13 tests RED-first.

Cero tests existentes modificados. Los seis endpoints legacy
de rank fijo y sus tests quedan sin cambios.

# Verificación

- `pytest taxon/tests/` → 118 passed (era 105; +13 nuevos).
- `ruff check` + `ruff format --check` clean.
- `mypy --strict taxon/` clean (30 archivos fuente).

Probe manual end-to-end contra el archivo CoL en vivo confirma
que el resolver path-aware encadena correctamente a través de
los ranks intermedios de CoL:

```
GET /api/path-children?path=Animalia|Chordata|Vertebrata|Gnathostomata|Osteichthyes|Actinopterygii
→ 200, 2 children, hint=superclass
   - Actinopteri (superclass)
   - Cladistia (superclass)
```

El chain `Animalia → Chordata → subphylum Vertebrata → infraphylum
Gnathostomata → parvphylum Osteichthyes → gigaclass
Actinopterygii → superclass Actinopteri → class Actinopteri →
...` funciona de extremo a extremo. El endpoint legacy
`/api/Animalia/Chordata/classes` devuelve `[]` porque impone
`rank == 'class'` a esa profundidad; el endpoint nuevo no.

# Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). Todos verdes. Cero workflows nuevos.
- **Revisiones** — 2 `work-unit-commits`:
  1. `f2ed7de test(api): add RED-first coverage for the path-aware /path-children endpoint` — falla primero contra el endpoint ausente.
  2. `ca4901d feat(api): add path-aware /path-children endpoint` — inserta el resolver + endpoint + schema, los tests van a GREEN.
- **Migración del frontend (PR #27b, follow-up)** — la UI del
  cascade se refactoriza de seis dropdowns fijos a N dropdowns
  dinámicos que consumen el endpoint nuevo. Cada dropdown
  emite el siguiente segmento del path cuando el usuario
  elige una opción; la siguiente llamada API pide los hijos
  del nuevo taxon más profundo.

# Aprendizajes

- **Path-aware le gana a rank-aware.** Los seis endpoints
  legacy de rank fijo eran un snapshot de los seis ranks
  canónicos del dataset WoRMS. CoL tiene 40+ ranks y usa
  intermedios libremente (subphylum, gigaclass, infraphylum,
  parvphylum, ...). El resolver path-aware no le importa
  cuántos ranks existen ni cómo se llaman; recorre lo que los
  datos le den. Es el único contrato que escala mientras el
  dataset evoluciona.

- **`next_rank_hint` es la moda, no un mapeo estático.** Un
  set heterogéneo de hijos (algunos subphyla + varios
  microspecies unranked) recibe el rank que más ocurre, no un
  "el siguiente rank es class" hardcodeado. El frontend usa
  el hint para etiquetar el dropdown pero el path conduce la
  llamada API real.

- **Endpoint aditivo en este PR.** Los endpoints legacy siguen
  disponibles; su deprecación y remoción es un PR aparte que
  incluye un plan de migración del frontend. Partir los dos
  mantiene cada PR chico y revisable.

- **Test contra el dataset en vivo, no solo contra fixtures
  a mano.** El chain de CoL `Chordata → Vertebrata → Gnathostomata
  → Osteichthyes → Actinopterygii → Actinopteri → ...` no está
  en el fixture de los tests (predata al re-seed de CoL). El
  paso de probe en vivo después del CI verde es lo que cazó
  la profundidad del chain y confirma que el resolver maneja
  6+ ranks intermedios sin sorpresas.

# PRs follow-up (no en este commit)

- **PR #27b** — refactor del cascade UI a N dropdowns dinámicos
  que consumen el endpoint nuevo. La máquina de estados en
  `Cascade.tsx` necesita manejar un número arbitrario de ranks
  en lugar de los seis hardcodeados.
- **PR #27c** — deprecar los seis endpoints legacy, agregar
  un warning de deprecación a la respuesta, removerlos después
  de un release. Después de que #27b embarque, ningún caller
  del frontend debería necesitar los endpoints legacy.

# Verificación con el archivo CoL en vivo

El endpoint se probó contra el archivo CoL en vivo
(`data/taxon.db`, 2.3 GB, 7.87M filas) con probes de curl. El
resolver path-aware encadena correctamente a través de los
ranks intermedios de CoL y emite valores `next_rank_hint`
razonables tanto para sets homogéneos como heterogéneos de
hijos.
