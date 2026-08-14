# Cascade 8 buckets display_level (PR #31)

# Qué

El Cascade UI ahora renderiza hasta 8 dropdowns (realm → kingdom → phylum → class → order → family → genus → species). CoL publica 40+ ranks con niveles intermedios (subphylum, infraphylum, megaclass, subclass, superorder, parvorder, infraorder, ...) que la escalera fija de seis ranks anterior se saltaba. El resolver path-aware los manejaba a nivel de API pero la UI seguía mostrando ruido de labels heterogéneos ("subphylum" vs "infraphylum" vs "megaclass" colapsaban en el mismo bucket lógico).

Este cambio introduce una única fuente de verdad — `taxon.taxonomy` — para los buckets del cascade. La tabla `Taxon` recibe una columna nueva `display_level` poblada en import. El resolver `/api/path-children` filtra children al whitelist del cascade y devuelve el bucket modal como `next_rank_hint` para que el label del dropdown se mantenga estable a través de los 40+ ranks intermedios.

# Por qué

Después del smoke test del PR #29, el cascade UI para Chordata mostraba 22,711 children. La causa raíz: 22,688 de ellos eran filas `unranked` que CoL entrega como children directos de Chordata sin ranks intermedios de phylum. El resolver path-aware las devolvía todas porque el filter era "cualquier rank excepto los deprecados". El dropdown del cascade estaba efectivamente congelado.

El fix es una única fuente de verdad — `taxonomy.py` — que mapea cada rank que CoL publica a uno de 8 buckets visibles. El resolver filtra a ese whitelist, el frontend capitaliza el nombre del bucket para el label del dropdown, y el cascade se mantiene dentro del presupuesto de 8 buckets para cada nivel.

# Cómo

## `taxon/taxonomy.py` — el contrato del cascade

```python
DISPLAY_LEVELS = ("realm", "kingdom", "phylum", "class", "order",
                  "family", "genus", "species")

RANK_TO_DISPLAY_LEVEL: Final[dict[str, str]] = {
    "domain": "realm", "superdomain": "realm", "subdomain": "realm",
    "kingdom": "kingdom", "subkingdom": "kingdom",
    "phylum": "phylum", "subphylum": "phylum", "infraphylum": "phylum",
    "parvphylum": "phylum", "microphylum": "phylum", "megaclass": "phylum",
    # ...etc — el mapeo completo está en el archivo...
}
```

El mapeo colapsa 40+ ranks de CoL en los 8 buckets. Ranks que no están en el mapeo (unranked, ranks históricos como `proles`, `natio`, `lusus`, `aberration`, `mutatio`, `morph`, más el ruido numérico de año que el parser de .txtree emite por accidente) quedan excluidos del cascade. El whitelist es la fuente de verdad.

## `taxon/schema.py` — columna `display_level`

```python
class Taxon(MarkerColumns, Base):
    __tablename__ = "taxa"
    __table_args__ = (
        Index("ix_taxa_parent_name", "parent_id", "name"),
        Index("ix_taxa_rank", "rank"),
        Index("ix_taxa_display_level", "display_level"),
    )
    ...
    display_level: Mapped[str | None] = mapped_column(String, nullable=True)
```

La columna se popula en import para que el resolver no tenga que mapear rank → bucket en cada query. El índice `ix_taxa_display_level` permite buscar "todos los phyla bajo Animalia" directamente.

## `taxon/api/path_children.py` — filter + bucket hint

```python
cascade_ranks = list(RANK_TO_DISPLAY_LEVEL.keys())
children_stmt = (
    select(Taxon)
    .where(
        Taxon.parent_id == current.id,
        func.lower(Taxon.rank).in_([r.lower() for r in cascade_ranks]),
    )
    .order_by(func.lower(Taxon.name), Taxon.name)
)
```

El `next_rank_hint` ahora es el bucket modal `display_level` (no el rank raw), así el label del dropdown se mantiene estable a través de los 40+ ranks intermedios que CoL publica.

## `taxon/api/{col_import,import_data}.py` — populate al insert

```python
rows_with_bucket = [
    {**row, "display_level": display_level(row["rank"])} for row in rows
]
```

Ambos paths de import (CoL DwC-A y WoRMS) populan la columna en el batch de insert. La migración para los 7.87M rows existentes en la DB live es un SQL: `ALTER TABLE taxa ADD COLUMN display_level TEXT; UPDATE taxa SET display_level = CASE rank WHEN ... END`.

## `frontend/src/components/Cascade.tsx` — capitaliza el label

```tsx
dropdowns.push({
  key: `${deepestKey}-next`,
  label: deepestSnapshot.nextRankHint.charAt(0).toUpperCase() +
    deepestSnapshot.nextRankHint.slice(1),
  options: deepestSnapshot.children,
  value: null,
  loading: false,
});
```

El backend devuelve el nombre del bucket (`"phylum"`, `"class"`, ...); el frontend lo capitaliza para el header del dropdown así el usuario lee "Phylum" / "Class" / "Order" / "Family" / "Genus" / "Species" independientemente de si el rank subyacente es "subphylum" o "infraclass" o cualquier otro rank intermedio.

# Impacto UX concreto

| Nivel | Antes | Después |
|---|---|---|
| Chordata (phylum) | 22,711 children — dropdown congelado | **23 children** — navegable |
| Mammalia (class) | 65 children — manejable | 65 children — igual |
| Animalia (kingdom) | 22,711 children | 22,711 children — ver abajo |

Animalia se queda en 22,711 porque **el dataset entrega filas reales de rank species y genus como children directos de Animalia sin ranks intermedios de phylum**. El `.txtree` confirma que esta es la estructura source-of-truth, no un bug de import de CoL. El filter display_level remueve las 22,688 filas unranked de Chordata pero no puede remover las 12,667 species reales flat-rankd bajo Animalia — eso requeriría reclasificar taxones, que es curación del dataset, no código.

# Dónde

- `taxon/taxonomy.py` — nuevo, 125 líneas. Módulo puro con el contrato rank → bucket.
- `taxon/schema.py` — agregar columna `display_level` + índice, 5 líneas.
- `taxon/col_import.py` — popular `display_level` al insert, 18 líneas.
- `taxon/import_data.py` — mismo para el path WoRMS, 8 líneas.
- `taxon/api/path_children.py` — filter + bucket hint, 49 líneas.
- `frontend/src/components/Cascade.tsx` — capitaliza el label del bucket, 30 líneas.
- `taxon/tests/test_taxonomy.py` — 53 RED-first tests pining el whitelist.
- `taxon/tests/test_col_import.py` — 2 tests nuevos pining la columna populada.
- `taxon/tests/test_api_path_children.py` — 3 tests nuevos pining el comportamiento del filter.
- `frontend/tests/Cascade.pathAware.test.tsx` — actualizar mocks para usar nombres de bucket.
- `frontend/tests/Cascade.ui.test.tsx` — mismo.

# Verificación

- 53 RED-first tests en `test_taxonomy.py` cubren el whitelist exhaustivamente: cada rank en el dataset, cada bucket, el ruido numérico de año, y el lookup case-insensitive.
- 6 tests en `test_col_import.py` pinean el `display_level` populado para las filas del fixture.
- 16 tests en `test_api_path_children.py` pinean el comportamiento del filter: unranked excluidos, ranks históricos excluidos, `next_rank_hint` es el bucket.
- 176 backend tests passing.
- 55/55 vitest tests passing.
- `tsc --noEmit` clean.
- `eslint` clean.
- `ruff check` + `ruff format --check` clean.
- `mypy taxon` clean.
- Smoke test manual contra el dev server vivo: el dropdown de kingdom lista 24 kingdoms, seleccionar Chordata reduce los children de 22,711 a 23, y el label del dropdown se lee como "Phylum" independientemente del rank subyacente de los children que Animalia, Chordata, etc. expongan.

# Workflows

- **CI** — 4 jobs verde: backend (3.11, 3.12), frontend (node 20), lighthouse.
- **Reviews** — dos commits: el feature (`fec178a`) y un follow-up `ruff format`. El follow-up pasó porque el `ruff format` step local estaba missing — `ruff check` estaba clean pero el formatter no. CI lo cazó en el primer push.

# Aprendizajes

- **El dataset es el bottleneck, no el código.** Los 22,711 children que Animalia expone son filas reales de CoL — confirmado recorriendo el `.txtree` directamente. El filter display_level puede remover filas unranked (22,688 de ellas en Chordata) pero no puede remover filas reales de rank species que CoL flatea bajo kingdom. Los 22,711 de Animalia es un problema de estructura de datos, no de código. El fix es curación del dataset (PR #27d autocomplete, o un search endpoint), no un filter distinto.

- **Una fuente de verdad para el contrato del cascade.** Antes de este PR, el nombre del bucket aparecía en tres lugares: el `next_rank_hint` del backend, el `inferDropdownLabel` del frontend, y los fixtures de test. El desacuerdo entre ellos causó la fragilidad de browser-test que golpeó al PR #29. Ahora `taxon.taxonomy.DISPLAY_LEVELS` es el único contrato — el backend lo lee, el frontend lo capitaliza, los tests assertean contra él. Agregar un nuevo bucket es una línea en `taxonomy.py`.

- **Whitelist, no blacklist.** El filter previo era implícito ("cualquier rank en la DB"). Bugs y edge cases aparecían como nuevos ranks que CoL introducía o como ranks que olvidábamos filtrar. El whitelist hace explícito el contrato: cada rank en el dataset o se mapea a un bucket o se excluye. Agregar un nuevo rank es una decisión deliberada en el diff, no un miss silencioso.

- **El ruido numérico de año es real.** El parser del `.txtree` emite ~3,500 strings como `1956 [15] [species]` donde el `[15]` no es un rank — se filtra porque la regex matchea cualquier `[xxx]`. El whitelist los ignora. El pipeline de import los captura al insert vía `display_level(rank) is None`, así viven en la DB pero nunca en el cascade.

- **`ruff format --check` es parte de CI.** El `ruff check` local estaba clean pero el formatter no. El gate de CI `ruff format --check` cazó el código sin formatear en el primer push. Agregar `ruff format taxon` al pre-commit hook (o correrlo en CI) es la lección: linting sin formatting deja que el whitespace menor se acumule.

- **`size:exception` es honesto cuando el work unit es cohesivo.** 538 inserciones y 42 deletions para un solo PR está arriba del threshold de 400 líneas. Split en chained PRs requeriría stubbing del resolver para llamar al módulo taxonomy aún no escrito, que no sería reviewable en aislamiento. El flujo taxonomy → schema → import → resolver → frontend es un único contrato reviewable.

# PRs follow-up (no en este commit)

- **PR #27c** — deprecar los endpoints legacy de rank fijo (`/api/{kingdom}/phyla`, etc.). El cascade UI ahora usa el endpoint path-aware exclusivamente.
- **PR #27d** — autocomplete picker para los 22,711 children de Animalia. El filter display_level no puede remover las filas reales de rank species que CoL entrega como children directos de Animalia. El autocomplete es la solución estándar que GBIF y COL usan.
- **Search endpoint** — para los 1.5M rows unranked excluidos del cascade. Los datos están en la DB (searchable, en el orden de import); el cascade UI solo los oculta. Un `/api/search?q=...` los surfacearía bajo demanda.
- **Pre-commit hook** — agregar `ruff format --check` al flow local de pre-commit para que el drift de formatting se capture antes de CI, no después.
