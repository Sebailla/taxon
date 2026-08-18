# Delta: envelope-de-subarbol

Fija el contrato de envelope para `GET /api/tree/children?parent_id={id}`: hijos directos + un `NextTier` por bucket en cascada (reino → filo → clase → orden → familia → género → especie), con filas recursivas por tier, paginación con cursor por tier y orden por rango en cascada. Reutiliza los helpers de roll-up en `taxon/api/sqlite_resolver.py` para que el árbol de exploración y la cascada compartan las mismas reglas de visibilidad off-tuple. (Anteriormente: `TreeChildrenResponse` solo llevaba hijos directos + `next_cursor` de nivel superior; `next_tiers` es aditivo.)

## ADDED Requirements

### Requirement: TreeChildrenResponse gana next_tiers

`GET /api/tree/children` SHALL retornar `{parent, children: list[TreeNodeResponse], next_tiers: list[TreeNodeTier] | None, next_cursor: str | None}`. `next_tiers` SHALL ser `None` cuando el padre no tiene descendientes no directos. `TreeNodeTier` SHALL llevar `{rank, label, examples, children: list[TreeNodeResponse], next_cursor: str | None}` donde `rank` es el bucket en cascada en minúsculas, `label` es el nombre humano del tier (p. ej. `"Phyla"`), y `examples` son los primeros tres nombres canónicos. `children` (directos) permanece como el primer campo posicional.

| Escenario | Dado | Cuando | Entonces |
|---|---|---|---|
| Animalia expone cuatro tiers no vacíos | `parent_id=43342` (Animalia) | respuesta parseada | `next_tiers.length >= 4`; tier phylum `children.length >= 30`; family `children.length >= 100`; tiers genus + species presentes |
| Padre hoja emite next_tiers: None | el padre es una hoja verdadera | cliente pide hijos | `next_tiers is None`; `children` es la lista de descendientes directos |
| Tier vacío se omite | el padre tiene hijos directos solo en `phylum` | cliente pide hijos | exactamente una entrada `next_tiers` (`rank="phylum"`); sin entradas vacías para otros rangos |

### Requirement: Tope de filas por tier y límite configurable

Cada `TreeNodeTier.children` SHALL estar limitado a `tier_limit` filas. El `tier_limit` por defecto SHALL ser `50`, máximo `200`. Los clientes SHALL controlarlo mediante `?tier_limit={n}`. El servidor SHALL truncar silenciosamente `tier_limit > 200` y rechazar valores negativos con HTTP 400.

| Escenario | Dado | Cuando | Entonces |
|---|---|---|---|
| Tope por defecto es 50 | sin `tier_limit` enviado | servidor procesa | todo tier `children.length <= 50`; los tiers que superan 50 retornan `next_cursor` no vacío |
| Tope elevado a 200 vía parámetro | `?tier_limit=200` | servidor procesa | todo tier `children.length <= 200`; SQL usa `LIMIT 200` por tier |
| Tope por encima de 200 se trunca | `?tier_limit=500` | servidor procesa | truncado silenciosamente a `200`; sin HTTP 400 |
| tier_limit negativo rechazado | `?tier_limit=-1` | servidor procesa | HTTP 400 con cuerpo identificando el valor inválido |

### Requirement: Paginación por tier con cursor keyed (name, id)

Cada tier SHALL paginar de forma independiente. Los clientes SHALL pedir la siguiente página con `?tier={rank}&cursor={cursor}`. El cursor SHALL ser base64 opaco de `f"{name}\x00{id}"`. El servidor SHALL saltar filas cuyo `id` ya no coincida con el id del cursor (tolerancia de id obsoleto para re-imports).

| Escenario | Dado | Cuando | Entonces |
|---|---|---|---|
| El cursor hace round-trip a la siguiente página | la primera página del tier family retorna `next_cursor="X"`, `children.length == 50` | cliente pide `?tier=family&cursor=X` | retornadas las siguientes 50 filas; ordenadas estrictamente después del `(name, id)` del cursor por `name` en minúsculas, ties por `id` |
| El cursor retorna None en la última página | el tier family tiene 75 filas, `tier_limit=50` | cliente pide segunda página | `children.length == 25`; `next_cursor is None` |
| El cursor tolera id renumerado | la fila `name` no cambia pero `id` se renumera | cliente presenta cursor obsoleto | servidor salta por mismatch de `id`; reanuda desde el `name` del cursor contra la nueva secuencia de id; sin error |
| La paginación por tier mantiene los otros tiers intactos | el tier genus retorna cursor | cliente pide `?tier=genus&cursor=…` | las filas del tier family sin cambios; solo genus avanza |

### Requirement: Orden por rango en cascada y roll-up off-tuple

`next_tiers` SHALL estar ordenado por `_DISPLAY_LEVELS_IN_ORDER` (`realm, kingdom, phylum, class, order, family, genus, species`). Los intermedios off-tuple (subphylum, infraphylum, parvphylum, microphylum, megaclass → bucket phylum; subfamily, tribe, subtribe, infratribe → bucket family) SHALL colapsar en su bucket padre vía `_phylum_rollup` y `_family_rollup`. Las reglas SHALL coincidir con el endpoint de cascada para que `Archaea → Nanoarchaeota` aparezca en phylum y `Felidae → Pantherinae` aparezca en genus.

| Escenario | Dado | Cuando | Entonces |
|---|---|---|---|
| Tiers ordenados por rango en cascada | el padre tiene descendientes en phylum, class, order, family, genus, species | cliente pide hijos | `next_tiers[0].rank == "phylum"`; rangos en orden de cascada; tier realm solo cuando el padre está por encima de kingdom |
| Roll-up de phylum colapsa intermedios | Chordata tiene hijos en `subphylum` y `class` | resolver aplica `_phylum_rollup` | subphylum descendido a `class`; tier class incluye directos + rolled-up; sin tier subphylum separado |
| Roll-up de family colapsa intermedios | Felidae tiene hijos en `subfamily`, `tribe`, `genus` | resolver aplica `_family_rollup` | subfamily/tribe descendidos a `genus`; tier genus incluye directos + rolled-up; sin tiers subfamily/tribe separados |
| Archaea expone Nanoarchaeota en el tier phylum | Archaea tiene hijo directo Nanoarchaeota en `phylum` | cliente pide hijos | el tier phylum incluye Nanoarchaeota; sin tier kingdom separado |

### Requirement: CTE recursivo por tier con max_depth=8

Cada tier SHALL obtenerse vía una CTE recursiva limitada al bucket de rango de ese tier con `max_depth=8`:

```sql
WITH RECURSIVE descendants(id, depth) AS (
    SELECT child_id, 0 FROM taxa WHERE parent_id = :pid AND rank IN :tier_ranks
    UNION ALL
    SELECT t.id, d.depth + 1 FROM taxa t JOIN descendants d ON t.parent_id = d.id
    WHERE d.depth < :max_depth
)
SELECT … FROM taxa t JOIN descendants d ON t.id = d.id ORDER BY LOWER(t.name), t.name LIMIT :tier_limit;
```

`:tier_ranks` SHALL ser el conjunto de rangos en minúsculas para el bucket actual de modo que el conjunto de trabajo quede limitado por bucket en cascada. `:max_depth` SHALL ser `8` en la primera iteración.

| Escenario | Dado | Cuando | Entonces |
|---|---|---|---|
| CTE por tier limita el conjunto de trabajo | petición de tier phylum contra Animalia (~70 clases) | CTE ejecuta | recorre como máximo 8 saltos en cascada; completa < 50ms p95 contra `data/col.db` |
| rank IN filtra el conjunto de trabajo | petición de tier class contra un padre con filas subspecies/variety/form | CTE ejecuta con `rank IN ("class",)` | no enumera subspecies/variety/form; retorna solo filas de rango `class` |
| El tope de profundidad protege contra jerarquías patológicas | los descendientes forman una cadena más profunda que 8 saltos en cascada | CTE ejecuta con `max_depth=8` | termina en profundidad 8; `WARNING` registrado del lado servidor; el envelope de wire no expone el banner |

### Requirement: Los hijos del tier llevan campos TreeNodeResponse

Cada fila de `TreeNodeTier.children` SHALL ser un `TreeNodeResponse` completo (`has_children`, `species_count`, `authorship` más los campos heredados de `TaxonResponse`). El umbral lazy-null de `species_count` (100.000 hijos directos) de `taxonomic-tree-browse` SHALL aplicarse a las filas del tier. `authorship` SHALL separarse de `display_name` como en la carga útil de hijos directos.

| Escenario | Dado | Cuando | Entonces |
|---|---|---|---|
| La fila del tier lleva campos derivados | fila de tier para `Felidae` con `display_name="Felidae Waldheim, 1817"` | cliente parsea la carga útil del tier | la fila lleva `has_children`, `species_count` (int o null), `authorship`; `display_name` coincide con la etiqueta fuente verbatim |
| Lazy null aplica a filas de tier | el padre del tier tiene > 100.000 descendientes directos | la consulta del tier ejecuta | cada fila lleva `species_count: null`; la respuesta renderiza dentro del presupuesto existente de 100ms por tier |
