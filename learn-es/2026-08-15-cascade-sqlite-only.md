# Cascade endpoints routed through local SQLite (PR #58)

## Qué

Las tres endpoints de la cascada taxonómica (`/api/kingdoms`, `/api/path-children`, `/api/species-list`) dejan de consultar la API en vivo de ChecklistBank (`https://api.checklistbank.org`) y pasan a leer de la base SQLite local, alineándose con el resolver de species-lookup y el dispatcher de links. La forma del wire de `next_tiers` se preserva al 100 %, de modo que el frontend React no requiere cambios.

## Cómo

Tres decisiones arquitectónicas sostienen el cambio.

**1. Reglas de roll-up conservadas.** La cascada aplaza los rangos intermedios que no encajan en la tupla de 6 niveles visibles para el usuario (kingdom → phylum → class → order → family → genus):

- phylum → class aplaza subphylum, infraphylum, parvphylum, microphylum, megaclass.
- subphylum se omite cuando un phylum solo tiene hijos directos en `class`.
- family → genus aplaza subfamily, tribe, subtribe, infratribe.
- el nivel de species lista además subspecies / variety / form.

**2. Conjuntos de rangos intermedios derivados de `taxon.taxonomy.RANK_TO_DISPLAY_LEVEL`.** Cada regla de roll-up itera el bucket y excluye el nivel canónico. Añadir un nuevo rango (por ejemplo `nanoorder`) al módulo de taxonomía propaga las reglas sin tocar el resolver.

**3. `/api/kingdoms` sintetiza Biota + Viruses server-side.** Los dos taxa raíz tienen IDs hardcodeados `5T6MX` y `V` para preservar el contrato de las dos filas del dropdown (`Cascade.tsx` selecciona Biota explícitamente).

La raíz del resoledor es `taxon/api/sqlite_resolver.py`, que expone `list_kingdoms`, `list_path_children` y `list_species_under_path`. La nueva API de `taxon/api/hierarchy.py` añade `resolve_path_by_display_level`, `list_children_by_display_level` y `_intermediate_ranks_for`; el `resolve_path` estricto por `rank` permanece intacto para los endpoints de lookup y links.

## Dónde

- `taxon/api/sqlite_resolver.py` — módulo nuevo (602 LOC). Aloja la forma del wire; exporta las tres funciones públicas más los helpers `_phylum_rollup`, `_family_rollup` y `_collect_descendants_by_rank`.
- `taxon/api/hierarchy.py` — +136 LOC. Resolver por bucket de `display_level`.
- `taxon/api/router.py` — −204 LOC tras retirar la inyección de dependencias del cliente CLB. Los tres handlers reciben `Session` y delegan en el resolver SQLite.
- `taxon/tests/test_api_sqlite_only_router.py` — archivo nuevo (654 LOC, 12 tests). Cobertura contractual de los endpoints de cascada con fixtures cargados vía `taxon.import_data.import_dataset`.
- `taxon/tests/test_api_checklistbank_router.py` — eliminado (732 LOC). Sus 7 tests quedan cubiertos por el archivo nuevo.
- `taxon/checklistbank.py` y `taxon/api/clb_path_children.py` — siguen en el árbol (importables, sin uso). Su borrado se ejecuta en el PR #59.

## Por qué

El síntoma recurrente era una cascada que renderizaba un linaje pero cuya hoja devolvía "Could not load links": la lista de species del endpoint local no conocía la ruta que la UI mostraba. La causa estructural era dos endpoints leyendo de dos fuentes distintas. Eliminar la dependencia CLB de la cascada cierra el bucle: una sola fuente, una sola verdad.

Se preserva la forma del wire porque el frontend React es el consumidor con la cobertura de tests más amplia y reescribir la UI de cascada hubiera inflado el PR por encima del presupuesto de la excepción. El nivel de species extendido a subspecies / variety / form responde a la confirmación A2 del usuario: las subspecies deben aparecer listadas bajo su especie padre.

## Cómo funciona

1. La UI invoca `GET /api/kingdoms` y obtiene dos filas: Biota (`id: "5T6MX"`) y Viruses (`id: "V"`), sintetizadas desde constantes del servidor.
2. Al elegir Biota, la UI llama `GET /api/path-children?path=Biota`. El backend recorre el linaje con `resolve_path_by_display_level(["Biota"])`, agrupa los hijos de Biota en el bucket `phylum` por su rango real y devuelve `next_tiers`.
3. Cada selección de phylum enciende una llamada `GET /api/path-children?path=...|Phylum` que vuelve a caminar por bucket de `display_level` y aplica las tres reglas de roll-up emitiendo uno o más `NextTier`.
4. El usuario elige un género y la UI pide `GET /api/species-list?path=...|Genus&cursor=...&include=synonyms,extinct,uncertain`. El backend camina por bucket, consulta los hijos del género en el nivel de species (incluyendo subspecies / variety / form) y pagina con `list_species_page` (cap de 500 filas).
5. La selección de la especie dispara `GET /api/{K}/{P}/{C}/{O}/{F}/{G}/{epithet}/links`, que ya era SQLite-backed y devuelve los 13 destinos de despacho.

## Workflows

- **CI**: ruff check, ruff format --check, mypy, pytest (backend) más typecheck, vitest, lint, build (frontend). Todos los jobs corren en cada PR contra `develop`.
- **Branching**: PR #58 parte de `develop` hacia `feat/api-sqlite-only-resolver` y vuelve por la misma base. Worktree en `../taxon-worktrees/<feature-name>`, borrado tras el merge conforme a AGENTS.md §4.
- **Cleanup**: PR #59 cierra el ciclo eliminando `taxon/checklistbank.py`, `taxon/api/clb_path_children.py`, sus tests y la dependencia `httpx`, una vez que la cascada es demostrablemente solo SQLite.

## Lecciones aprendidas

- **`display_level IS NULL` rompe el resolver.** `taxon.indented_import` deja `display_level` en NULL por diseño; el resolver filtra por esta columna, de modo que la cascada devuelve 404 en cada path hasta que se rellene. Los endpoints de lookup y links no sufren el problema porque filtran por `Taxon.rank`. El docstring del módulo en `taxon/api/sqlite_resolver.py` documenta la trampa.
- **Los fixtures de test se siembran con `taxon.import_data.import_dataset` (WoRMS DwC-A), no con `taxon.indented_import`.** Mezclar importadores en el mismo test es inviable por la brecha de `display_level`; migrar los fixtures al importador indented es un follow-up fuera del PR #58.
- **Dos módulos huérfanos** sobreviven en el árbol: `taxon/api/path_children.py` y `taxon/api/species_list.py`. Ninguno se importa; quedaron como scaffold de una iteración previa que convergió en `taxon/api/sqlite_resolver.py`. Un PR de limpieza posterior puede eliminarlos.
- **El BFS de roll-up desciende en cada hijo intermedio.** Un phylum cuyo subphylum no tiene hijos en `class` pero cuyo nieto megaclass sí los tiene, expone los descendientes del megaclass. El comportamiento coincide con la API en vivo de ChecklistBank y con la expectativa del usuario.

## Follow-up PRs (no en este commit)

- **PR #59** — eliminación de `taxon/checklistbank.py`, `taxon/api/clb_path_children.py`, sus tests y la dependencia `httpx`, ahora que la cascada es solo SQLite.
- **Cleanup de módulos huérfanos** — `taxon/api/path_children.py` y `taxon/api/species_list.py` pueden borrarse en un PR aparte.
- **Migración de fixtures** — portar los tests de `test_api_sqlite_only_router.py` al importador `indented_import` requiere poblar `display_level` en ese flujo; queda fuera del scope de PR #58.
