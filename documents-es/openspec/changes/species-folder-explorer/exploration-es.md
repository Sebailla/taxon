# Exploración — species-folder-explorer

> Cierra el issue #68. Cuatro sub-features acopladas (A. flag explored, B. creación de carpeta, C. switches por enlace, D. explorador embebido) para el change `species-folder-explorer`, planificado DESPUÉS de que `arbol-col-browse` (issue #67) aterrice en `develop` (PR #69 mergeada en `3fc2eb1`, archivada en `openspec/changes/archive/2026-08-16-arbol-col-browse/`).

## Estado actual

### 1. Forma de `SpeciesList.tsx` (`frontend/src/components/SpeciesList.tsx`)

- **Contrato del componente** (`SpeciesListProps`, líneas 18–27): `rows: TaxonResponse[]`, `status: "idle" | "loading" | "error"`, `cursor: string | null`, `parentSegments: string[]`, `breadcrumb: string[]`, `onLoadMore` opcional.
- **Estado**: render puro — sin estado interno, sin hooks consumidos. Todo el estado lo posee `App.tsx` y se pasa por props.
- **Contrato de click de fila** (`dispatchTaxonSelect`, líneas 64–70): al hacer click, dispara el evento CustomEvent `taxon:select` con `{row, breadcrumb, parentSegments}`, validado por el schema Zod `TaxonSelectDetailSchema` en `frontend/src/events/taxonSelect.ts`. `App.tsx` (líneas 70–93) escucha `TAXON_SELECT_EVENT` y actualiza `resolved` + `parentSegments`.
- **Layout de la fila** (líneas 60–82): un `<ul aria-label="Species list">` con filas `<button type="button">`. Cada fila renderiza `name` (`font-mono text-sm text-navy`, truncado) y `display_name` condicional (cuando `display_name !== name`), con un slot `<MarkerBadges>` al final.
- **Badges de marcadores** (`MarkerBadges`, líneas 97–142): cuatro flags desde `TaxonResponse`: `is_extinct` (`† extinct`, rojo), `is_synonym` (`= synonym`, ámbar), `is_uncertain` (`? uncertain`, slate), `is_unassigned` (`unassigned`, slate). El slot es un `flex gap-1` de chips a la derecha de cada fila.
- **Estados vacío / loading / error** (líneas 30–52): tarjetas `<p>` distintas con estilo `rounded-card border`; `cursor` no nulo dispara un botón `Load more` debajo de la lista.
- **Dónde se enganchan las columnas nuevas**: la fila es hoy `[name / display_name] [MarkerBadges]`. Una columna al final con `[checkbox-explored] [badge-o-botón-carpeta]` se ubicará a la derecha de `MarkerBadges`; la columna de switch inicial `[visited]` NO aplica aquí (la sub-feature C apunta a `SpeciesLinks`, no a `SpeciesList`).

### 2. Forma de `SpeciesLinks.tsx` (`frontend/src/components/SpeciesLinks.tsx`)

- **Contrato del componente** (`SpeciesLinksProps`, líneas 19–21): una sola prop `links: SearchLinkItem[]`.
- **Layout de render** (líneas 32–44): `<section aria-label="Search source dispatch">` con grid responsivo de 4 columnas (`grid-cols-2 sm:grid-cols-3 lg:grid-cols-4`), cada celda renderizada por `SourceLink` (líneas 47–65).
- **Semántica del anchor**: `target="_blank" rel="noopener noreferrer"` — abre en pestaña nueva, hijacking de `window.opener` prevenido.
- **Separación visual de Sci-hub** (línea 48 + línea 58): `border-red` en vez de `border-border`. **Sin estado hoy** — el enlace es siempre clickable.
- **Interfaz `SearchLinkItem`** (`frontend/src/api.ts`, líneas 82–86): `{ source: string; label: string; url: string }`. `source` es el nombre canónico desde `docs/sources/templates.md` ("Wikipedia", "Google", "BHL", "ResearchGate", "Plos", "Academia", "Scielo", "Scholar", "Youtube", "Zootaxa", "Photos", "Sci-hub", "Scribd" — 13 items). `label == source` para el caso species-links; los enlaces per-taxon llevan la misma forma.
- **Dos consumidores** (ambos renderizan `<SpeciesLinks>`):
  1. `App.tsx:205` — estado `links` desde `fetchLinks(parentSegments, epithet)` (panel species-links, "last-clicked wins" sobre el panel breadcrumb).
  2. `App.tsx:219` — `breadcrumbLinks.data.links` desde `fetchTaxonLinks(cascadePath)` (panel per-taxon breadcrumb-links de `breadcrumb-dinamico` PR #66).
- **Sub-feature C se engancha aquí**: cada celda necesita un switch `[visited]` al inicio; el estado visitado debe persistir a través de ambos consumidores (panel species-links y panel per-taxon breadcrumb-links).
- **Sub-feature D se engancha aquí**: la URL del enlace actualmente activo debe estar disponible para `<ExplorerPanel>` para que el iframe la cargue. La costura más limpia es elevar el estado del enlace activo a un store al que el explorer se suscribe.

### 3. `resolve_path_by_display_level` (`taxon/api/hierarchy.py`, líneas 292–338)

- **Firma**: `def resolve_path_by_display_level(session: Session, segments: list[str]) -> TaxonRow | None`.
- **Retorna**: `TaxonRow` (dataclass frozen en líneas 71–88, campos `id`, `name`, `display_name`, `rank`, `parent_id`, más los cuatro flags de marcadores), o `None` cuando algún segmento no resuelve.
- **Semántica de error**: `None` se propaga al caller; el router levanta `NotFoundError(f"taxon not found: {segments[-1]!r}")` (ver `router.py:184` y `router.py:884`). No hay 422 para input inválido; el resolver es total (retorna `None` en cualquier modo de falla).
- **Mecánica del walk**: cada segmento matchea contra `Taxon` cuyo `display_level` es un bucket debajo del bucket del segmento previo, o el mismo bucket (intermedios off-tuple: subphylum, infraphylum, parvphylum, subfamily, tribe, subtribe, infratribe). El primer segmento ancla sin padre (parent desconocido); los segmentos siguientes anclan en el `id` del match previo. Match de nombre case-insensitive vía `func.lower(Taxon.name) == segment.lower()`.
- **Orden de buckets** (`_DISPLAY_LEVELS_IN_ORDER`, líneas 204–213): `("realm", "kingdom", "phylum", "class", "order", "family", "genus", "species")`. El primer segmento ancla en `kingdom`.
- **Historia de reuso para sub-feature B (creación de carpeta)**: el endpoint recibe `(genus, epithet)` como path params (mirror del breadcrumb-shaped lookup de `/{kingdom}/.../{genus}/{epithet}`), resuelve el breadcrumb completo vía `resolve_path_by_display_level([kingdom, phylum, class, order, family, genus, epithet])` (donde el epithet es el último segmento en el bucket species), y une los segmentos `taxon.name` con `os.sep` para construir la ruta de la carpeta. La función NO sintetiza una raíz Biota — el resolver arranca en el bucket kingdom. El breadcrumb builder en `taxon/api/species.py::build_breadcrumb` (re-exportado) entrega el mismo path en la forma que consume `App.tsx`.

### 4. Superficie de `taxon/api/router.py` + `taxon/api/schemas.py`

**Routers (16 GET, 0 POST, 0 DELETE — verificado línea por línea contra `router.py`):**

| Método | Path | Función | Líneas | Notas |
|--------|------|---------|--------|-------|
| GET | `/_meta` | `api_meta` | 132–135 | Smoke probe; retorna `{"phase": "2C"}` (stale, pero conservado por docstring). |
| GET | `/path-children` | `path_children` | 138–185 | Query: `path: str`. Pydantic: `PathChildrenEnvelope`. |
| GET | `/species-list` | `species_list` | 188–246 | Query: `path: str, include: str \| None, cursor: str \| None`. Pydantic: `SpeciesListResponse`. |
| GET | `/kingdoms` | `list_kingdoms` | 249–263 | Sintetiza Biota + Viruses con ids opacos CLB `5T6MX` / `V`. |
| GET | `/{kingdom}/phyla` | `list_phyla` | 295–304 | Forma path legacy. |
| GET | `/{kingdom}/{phylum}/classes` | `list_classes` | 307–317 | Forma path legacy. |
| GET | `/{kingdom}/{phylum}/{class_name}/orders` | `list_orders` | 320–332 | Forma path legacy. |
| GET | `/{kingdom}/{phylum}/{class_name}/{order_name}/families` | `list_families` | 335–347 | Forma path legacy. |
| GET | `/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/genera` | `list_genera` | 350–367 | Forma path legacy. |
| GET | `/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/species` | `list_species` | 370–427 | Forma path legacy, paginado, filtro `include`. |
| GET | `/{kingdom}/.../{genus_name}/{epithet}` | `lookup_species` | 541–574 | Lookup species con forma breadcrumb. |
| GET | `/species/{genus_name}/{epithet}` | `lookup_species_by_pair` | 577–602 | Solo por par; puede retornar 409 con `candidates[]`. |
| GET | `/{kingdom}/.../{genus_name}/{epithet}/links` | `species_links` | 605–647 | El dispatch de 13 enlaces (el issue #68 dice 12; el conteo real es 13 según `templates.md`). |
| GET | `/tree/children` | `get_tree_children` | 676–770 | Tree expand por parent-id; `parent_id=0` para roots. |
| GET | `/tree/search` | `get_tree_search` | 773–831 | Autocompletar "Find taxon". |
| GET | `/{path:path}/taxon-links` | `taxon_links` | 834–894 | Dispatch per-taxon para segmentos del breadcrumb (sin epithet). |

**Convenciones de routing** (verificadas a lo largo del archivo):
- `router = APIRouter(prefix="/api")` (línea 107). Cada endpoint vive bajo `/api`.
- Los path params usan `Annotated[..., Path(min_length=1)]`; `class_name`, `order_name`, `family_name`, `genus_name`, `epithet` llevan `alias=...` para mantener el identificador Python legible mientras el segmento URL queda sin cambios.
- Los query params usan `Annotated[..., Query(description=...)]` con validadores `min_length` / `max_length` / `ge` / `le` donde aplica.
- Dep de sesión: `Annotated[Session, Depends(get_db)]`.
- Envelopes de error: `NotFoundError` → 404, `AmbiguousError` → 409 con `candidates[]`; ambos se renderizan vía el helper `_error_response` en `taxon/api/__init__.py:106-123` (cuerpo uniforme `{detail: str, candidates?: [...]}`).
- El orden de registro de rutas importa: los endpoints de tree DEBEN registrarse antes del catch-all `/{path:path}/taxon-links` o los segmentos literales `tree/children` serán consumidos. Lo mismo aplica a cualquier endpoint nuevo con segmentos literales — registrar ANTES de los catch-alls.

**Modelos Pydantic** (`taxon/api/schemas.py`, todos en `__all__`):
- `TaxonResponse` (línea 46) — taxon único: `id: int|str`, `name`, `display_name`, `rank`, `parent_id`, cuatro flags de marcadores.
- `SpeciesPathResponse` (línea 72) — breadcrumb materializado con columnas de rank.
- `MarkerFlags` (línea 139) — grupo anidado de marcadores.
- `SpeciesListItem` (línea 153) — misma forma que `TaxonResponse` más `parent_segments: list[str]`.
- `SpeciesListResponse` (línea 178) — `{items, next_cursor}`.
- `SpeciesLookupResponse` (línea 191) — `{id, canonical_name, display_name, markers, breadcrumb}`.
- `AmbiguityCandidate` (línea 207) — payload de candidato 409.
- `SearchLinkItem` (línea 221) — `{source, label, url}` (la tabla `link_visited` se keyará en `source`).
- `LinksResponse` (línea 235) — envelope `{species, links}`.
- `TaxonLinksResponse` (línea 248) — envelope `{taxon, links}` (dispatch per-taxon).
- `NextTier` (línea 264), `PathChildrenEnvelope` (línea 293) — envelope cascade.
- `TreeNodeResponse` (línea 318), `TreeChildrenResponse` (línea 336), `TreeSearchHit` (línea 352), `TreeSearchResponse` (línea 372) — superficie tree.
- Mixin `_ORMBase` (línea 34) carga `model_config = ConfigDict(from_attributes=True)`.
- `HealthResponse` (línea 100), `CandidateRef` (línea 106), `ErrorResponse` (línea 118) — envelopes de health + error.

**No existen `POST` / `DELETE` hoy.** El change agrega los primeros endpoints POST/DELETE; el patrón `Annotated[..., Path]` + `Depends(get_db)` + levantar `NotFoundError`/`APIError` se traslada literal.

### 5. Migraciones Alembic

**NO hay migraciones Alembic en este proyecto.** Los únicos caminos de gestión de DB son:

- `taxon/schema.py` (archivo completo, 55 líneas) — SQLAlchemy 2.0 DeclarativeBase tipado con dos modelos: `Taxon` (tabla `taxa`) y `SpeciesPath` (tabla `species_paths`). La llamada `Base.metadata.create_all(engine)` vive en `taxon/api/__init__.py:145` y SOLO dispara para `sqlite:///:memory:` (tests). Los engines file-backed asumen que el schema ya existe (creado out-of-band por `python -m taxon.import_data`).
- `taxon/import_data.py` (14369 bytes) — importer del dataset GBIF/WoRMS; construye las tablas `taxa` + `species_paths` en tiempo de import. **No existen columnas `species_folders`, `link_visited`, `explored_flags`, ni `is_explored`** — verificado con `sqlite3 data/col.db ".tables"` que retorna solo `species_paths` y `taxa`, y `rg 'is_explored|explored_flags|species_folders|link_visited'` que retorna cero matches en `taxon/` o `docs/`.

**Implicación para el milestone del issue #68**: el milestone "Alembic migration `0010_add_species_folders_link_visited_explored.py`" debe reemplazarse con **una de**:
- (a) un script `python -m taxon.migrate` hecho a mano que use `Base.metadata.create_all(...)` para las tablas nuevas + un `ALTER TABLE taxa ADD COLUMN is_explored BOOLEAN NOT NULL DEFAULT 0` si el flag explored se materializa sobre `taxa`, **o**
- (b) un enfoque runtime-only: las tablas nuevas se crean al arranque de la app vía `Base.metadata.create_all(engine)` en el lifespan (con un check de versión de schema en una línea), y el change se entrega sin script de migración.

Esta es una bifurcación real — `sdd-propose` debe decidir.

### 6. Patrones de stores en frontend

**`frontend/src/store/cascadePath.ts` (62 líneas, archivo completo):**

- Zustand `create<CascadePathState>` con la interfaz de estado (líneas 27–30): `{path: string[], setPath(path: string[]): void}`.
- `setPath` es un replace no-op (líneas 52–61): cuando `arraysEqual(prev.path, next)` retorna `prev` para que los subscribers no refiren en una llamada redundante.
- El export es `useCascadePath` (línea 50) — un hook tipado que dobla como store vanilla (`useCascadePath.getState()`, `useCascadePath.subscribe()`).
- El mismo archivo es importado por `App.tsx` (línea 39), `frontend/src/components/Breadcrumb.tsx` (no — breadcrumb es prop local), y los tests usan el store directamente vía patrones `useTaxonomicTree.setState(...)`.

**`frontend/src/store/taxonomicTree.ts` (267 líneas, archivo completo):**

- Zustand `create<TreeState>` con la interfaz completa (líneas 43–67): `childrenByParentId: Map<number, TreeNodeResponse[]>`, `expandedIds: Set<number>`, `rootIds: number[] | null`, `loadingParentIds: Set<number>`, `errorByParentId: Map<number, string>`, `includeExtinct: boolean`; acciones `loadRoots`, `ensureChildren`, `toggleExpand`, `setError`, `clearError`, `revealNode`, `setIncludeExtinct`.
- Patrón: cada mutación construye un `Map` / `Set` nuevo (ej. líneas 90–93 `const next = new Map(get().childrenByParentId); next.set(0, result.data.children); set({...})`) para que el chequeo de shallow-equality de Zustand dispare solo en cambios reales.
- Las acciones async retornan `Promise<void>`; el caller espera la promesa (ej. `TaxonomicTree.test.tsx` espera `revealNode`).

**Plan para un nuevo `workspaceStore`** (`frontend/src/store/workspace.ts`):

- Forma (propuesta): `{exploredBySpeciesId: Map<number, boolean>, foldersBySpeciesId: Map<number, string>, visitedByKey: Map<string, Set<string>>, activeLink: {speciesId: number, source: string, url: string} | null, setExplored(speciesId, value), createFolder(speciesId): Promise<void>, setFolderPath(speciesId, path), toggleVisited(speciesId, source), setActiveLink(speciesId, source)}`.
- Modelo de persistencia: el store es la cache; el backend es la fuente de verdad. Cada mutación llama a un endpoint backend que retorna la fila canónica, y el store la refleja. Una sola acción `hydrate()` trae todas las filas del workspace del usuario al montar la app (`GET /api/workspace?genus=…&epithet=…` para la especie actualmente resuelta, con scope reducido para mantener el payload chico; o `GET /api/explored/list` + `GET /api/link-visited/list` para un hydrate completo).
- El store se ubica junto a `cascadePath` y `taxonomicTree`; sin fusión con ninguno. La fila de `SpeciesList` lee `useWorkspace((s) => s.exploredBySpeciesId.get(row.id))` y llama `setExplored(row.id, !current)` en el change del checkbox. `SpeciesLinks` lee `useWorkspace((s) => s.visitedByKey.get(`${speciesId}`))` (un `Set<string>` de source labels).
- La URL del iframe es `useWorkspace((s) => s.activeLink?.url ?? null)`; setear activeLink es el acto de hacer click en una celda de `SpeciesLinks` (el handler hace ambos `window.open(url, "_blank", "noopener,noreferrer")` y `setActiveLink(speciesId, source, url)`).

### 7. Convención de filesystem `./Proyecto-Aqualife/`

- **No existe** en el filesystem local hoy (`ls Proyecto-Aqualife` → no presente). El proyecto tampoco tiene llamadas `os.makedirs('./Proyecto-Aqualife/...')` en ningún lugar del repo — `rg 'AQUALIFE_ROOT|Proyecto-Aqualife|os\.makedirs'` retorna cero matches.
- **Patrón de lectura de env vars** (verificado en `taxon/api/__init__.py:59` y `taxon/import_data.py:203,208`): `os.environ.get("TAXON_*", DEFAULT)` — misma forma que `TAXON_DATABASE_URL`, `TAXON_TEMPLATES`, `TAXON_DATASET`, `TAXON_DATABASE`. La convención son env vars `TAXON_*` con default de path relativo que resuelve contra `Path(".")`.
- **No hay `python-dotenv`** en las dependencias del proyecto (verificado en `pyproject.toml:11-23`: solo `fastapi`, `pydantic`, `sqlalchemy`, `uvicorn`). El patrón de env var es `os.environ.get()` directo — sin loader de `.env`.
- **Root por defecto** (según el cuerpo del issue #68): `./Proyecto-Aqualife/` relativo al project root (`/Users/<user>/Developer/taxon/`).
- **Plan para la env var `AQUALIFE_ROOT`**: agregar `os.environ.get("AQUALIFE_ROOT", "./Proyecto-Aqualife/")` a un nuevo módulo helper `taxon/api/workspace.py` (o `taxon/api/folders.py`), exportado desde `taxon.api.__init__`. En el arranque de `create_app`, asegurar que el directorio exista con `Path(root).mkdir(parents=True, exist_ok=True)` y rechazar un root no escribible con un envelope de error claro. Espejar el precedente de `TAXON_DATABASE_URL`: env var + default sensato + sin dotenv.

### 8. Templates de fuentes de búsqueda (`docs/sources/templates.md`)

13 templates, en orden de fila, parseados por `taxon/search_links.py::load_templates` (el regex en línea 11 fuerza la sintaxis de tabla; la función en línea 41 levanta `ValueError` si `len != 13`):

| # | source (clave canónica) | Patrón URL |
|---|-------------------------|------------|
| 1 | Wikipedia | `http://es.Wikipedia.org/wiki/Special:Search?search={q}` |
| 2 | Google | `http://Google.com/search?q={q}` |
| 3 | BHL | `http://biodiversitylibrary.org/search?SearchTerm={q}` |
| 4 | ResearchGate | `http://researchgate.net/search?q={q}` |
| 5 | Plos | `http://journals.plos.org/plosone/search?filterJournals=PLoSONE&q={q}&page=1` |
| 6 | Academia | `http://academia.edu/people/search?utf8=%E2%9C%93&q={q}` |
| 7 | Scielo | `http://search.scielo.org/?q={q}` |
| 8 | Scholar | `http://scholar.google.com/scholar?hl=es&as_sdt=0%2C5&q={q}&btnG=` |
| 9 | Youtube | `http://youtube.com/results?search_query={q}` |
| 10 | Zootaxa | `http://mapress.com/j/zt/search/search?query={q}` |
| 11 | Photos | URL larga de Google Images (preservada verbatim) |
| 12 | Sci-hub | `https://sci-hub.ru/match/{q}` |
| 13 | Scribd | `https://es.scribd.com/search?query={q}` |

La columna `link_visited.source_label` es exactamente el string `source` de arriba. La celda de `SpeciesLinks` renderiza el `label` (que es `source` para ambos endpoints según `search_links.py:53` — `SearchLink.label == source`).

**Nota sobre la wording del #68**: el issue dice "12 dispatch URLs" y "13 links". Ambos son correctos — el endpoint species-links emite 13 (según `templates.md` y el guard `len(templates) != 13` en `search_links.py:41`), mientras que comentarios viejos en `router.py:17,619` los describen como "12 dispatch URLs" porque la hoja de cálculo original traía 12 y Sci-hub se añadió después. Usar **13** en todas partes del nuevo spec.

### 9. Sandbox de iframe + Content-Disposition (nota de investigación, no exhaustiva)

La fase de diseño DEBE cerrar estos detalles; la exploración captura solo el territorio:

- **Atributos sandbox del iframe**: un combo permisivo-pero-sin-top-level-navigation para downloads es `sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`. Los flags habilitan: same-origin (para que los scripts del iframe lean/escriban cookies/storage del propio iframe), scripts (para que la página de terceros funcione), forms (para que los inputs de búsqueda funcionen), popups (para que `<a target="_blank">` clicks dentro del iframe abran en nueva pestaña), y downloads (para que `<a href="...pdf" download>` dispare una descarga). El flag NO habilitado es `allow-top-navigation` — el iframe no debe poder navegar el parent (previene hijacking del SPA vía la fuente embebida).
- **Routing de descarga cross-origin**: `<a href="..." download>` dentro del iframe dispara un download event; el browser maneja la escritura en el sistema de archivos. El header Content-Disposition (`attachment; filename="..."` vs `inline`) controla si el iframe trata la respuesta como download o como navegación. Para el workflow del usuario de "guardar en la carpeta de la especie", el download por defecto del browser es la primitiva correcta — el iframe del SPA no necesita interceptar el download vía parseo de `Content-Disposition`. Un drag-and-drop desde el iframe al explorador de archivos del OS funciona porque el iframe corre en un contexto de navegación separado.
- **X-Frame-Options / CSP frame-ancestors**: muchos sitios (Wikipedia, Google Scholar, BHL) envían `X-Frame-Options: SAMEORIGIN` o `Content-Security-Policy: frame-ancestors 'self'` y rechazarán renderizar dentro de cualquier iframe. El fallback es `target="_blank"` (ya cableado) — el iframe puede mostrar un mensaje "esta fuente rechaza embedding" con un botón que abre la URL en nueva pestaña. El issue #68 lo reconoce explícitamente ("accept those limitations").
- **Limitaciones del browser**: Safari y Firefox ambos controlan downloads iniciados por iframe de forma más estricta que Chrome. El fallback `target="_blank"` del SPA cubre el modo de falla de forma uniforme.
- **Iframe sandboxed + el árbol React del propio SPA**: el SPA NO debe colocar el iframe dentro del elemento `<form>` / `<dialog>` / `<main role=main>` si intenta renderizar el contenido del explorer; un `aria-label` en el iframe (`aria-label="Embedded search result for {species}"`) es obligatorio para pasar axe-core.

### 10. Disponibilidad de Pencil MCP

- **El Pencil MCP está deshabilitado en esta sesión.** Una prueba directa (`pencil_get_app_state`) retornó `MCP error -32603: failed to connect to running Pencil app: visual_studio_code after 3 retries: transport not connected to app: visual_studio_code`. `list_mcp_resources` confirma que `pencil` es alcanzable pero no tiene superficie de recursos para consultar.
- **Precedente**: `arbol-col-browse` (issue #67, archivado 2026-08-16) cayó en el mismo estado y lo resolvió escribiendo un `docs/design/taxonomic-tree-browse.md` prescriptivo (784 líneas) en lugar de una página `.pen`. El `archive-report.md:115` anota la diferición verbatim y reserva el derecho de rehacer la página `.pen` en un slice futuro.
- **Mantener el patrón hacia adelante**: este change NO tendrá página `.pen`. La fase de diseño escribe `docs/design/species-folder-explorer.md` + mirror español `documents-es/docs/design/species-folder-explorer-es.md`, con specs de implementación línea por línea para los componentes nuevos (`ExplorerPanel.tsx`, los switches nuevos en `SpeciesList` / `SpeciesLinks`). El audit con el skill `impeccable` se aplica igualmente al markdown prescriptivo (per AGENTS.md §5 el audit ocurre ANTES de la implementación — el markdown es la entrada de diseño).

### 11. Superficie del schema de `data/col.db` (verificado con `sqlite3 data/col.db ".schema"`)

**Solo existen dos tablas**:

- `taxa` — 11 columnas: `id INTEGER PK autoincrement`, `source_id VARCHAR NOT NULL UNIQUE` (identificador CLB/CoL, ej. `5T6MX`), `parent_id INTEGER FK→taxa.id`, `rank VARCHAR NOT NULL`, `name VARCHAR NOT NULL`, `display_name VARCHAR NOT NULL`, `display_level VARCHAR` (NULL en `col.db`, poblado en `taxon.db`; se resuelve vía la función SQL `taxonomy_display_level`), `is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned` — todas `BOOLEAN NOT NULL`. Índices: `ix_taxa_parent_name (parent_id, name)`, `ix_taxa_rank (rank)`, `ix_taxa_display_level (display_level)`.
- `species_paths` — 11 columnas: `id INTEGER PK autoincrement`, `species_id VARCHAR FK→taxa.source_id UNIQUE` (nota: ¡el FK va a `source_id`, no a `id`!), `kingdom`, `phylum`, `class_name`, `"order"`, `family`, `genus` — todos `VARCHAR NULL`, `species VARCHAR NOT NULL`, `display_name VARCHAR NOT NULL`, más los cuatro flags de marcadores. Índice: `ix_species_paths_species (species)`. **0 filas** en `col.db` (solo poblado por el importer WoRMS; el re-import de CoL lo dejó vacío).

**Decisión de storage para el flag `explored`**: dos formas viables:
- (a) Agregar `is_explored BOOLEAN NOT NULL DEFAULT 0` a la tabla `taxa` (desnormalizado). Pro: lecturas de una sola fila vía el modelo ORM `Taxon` existente; sin join. Con: los re-imports (el importer recrea la tabla `taxa`) borran el flag — hay que re-aplicarlo o enseñarle al importer a preservarlo.
- (b) Nueva tabla `explored_flags(species_id INTEGER FK→taxa.id, explored_at TIMESTAMP)`. Pro: ortogonal a `Taxon`; seguro ante re-imports. Con: join extra en cada lectura de fila de species-list, o un hydrate por fila (cacheado en el `workspaceStore`).

**Recomendación para que `sdd-propose` confirme**: la opción (b) es la elección más segura dada la fragilidad del pipeline de datos conocido del proyecto (`taxon/import_data.py` y `taxon/indented_import.py` ambos construyen la tabla `taxa` desde cero en cada corrida — ver `learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` para la fragilidad del pipeline). Las tablas `species_folders` y `link_visited` son sin ambigüedad nuevas (sin preocupaciones de churn de schema); el flag explored es la única bifurcación column-vs-table.

**Target de FK**: la columna `species_folders.species_id` debe hacer FK a `taxa.id` (autoincrement integer), NO a `taxa.source_id` (string opaco CLB). El `link_visited.species_id` también debería hacer FK a `taxa.id` por consistencia. El FK de `species_paths.species_id` a `source_id` es precedente solo para la proyección del importer, no una regla general.

## Puntos de integración

**Backend**:
- `taxon/schema.py` — agregar tres modelos SQLAlchemy (o extender `MarkerColumns` si se elige la opción (a) para explored). Usar semántica `Base.metadata.create_all(engine)`; agregar un paso de migración o doblarlo dentro del lifespan.
- `taxon/api/router.py` — registrar **cuatro endpoints nuevos** ANTES del catch-all `/{path:path}/taxon-links` (líneas 834–894) para que los segmentos literales de ruta no se ensombrezcan. Cada endpoint toma `(genus, epithet)` como path params O un capture shape-path `{path:path}`; la fase de proposal debe elegir.
  - `POST /api/explored/{genus}/{epithet}` → toggle explored = True; retorna la fila de species.
  - `DELETE /api/explored/{genus}/{epithet}` → toggle explored = False; retorna la fila de species.
  - `POST /api/species-folder/{genus}/{epithet}` → resolver breadcrumb vía `resolve_path_by_display_level`, mkdir `Path(AQUALIFE_ROOT) / "Animalia" / "Chordata" / ... / "Panthera tigris"`, insert fila `species_folders`, retornar `{path: str}`.
  - `GET /api/species-folder/{genus}/{epithet}` → leer fila existente; 404 si aún no hay carpeta.
  - `POST /api/link-visited/{genus}/{epithet}` → upsert `{source, visited_at}`; idempotente.
  - Opcional: `GET /api/link-visited/{genus}/{epithet}` → lista de `{source, visited_at}` para la especie; el SPA hidrata el set de visited al montar.
- `taxon/api/schemas.py` — agregar `ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedRequest`, `LinkVisitedResponse`. Exportar desde `__all__`.
- `taxon/api/workspace.py` (nuevo) — el resolver: `set_explored`, `unset_explored`, `create_species_folder`, `record_link_visited`, `unrecord_link_visited`, `list_link_visited`. Más el lector de la env var `AQUALIFE_ROOT`.

**Frontend**:
- `frontend/src/components/SpeciesList.tsx` — agregar la columna al final `[checkbox-explored] [badge-o-botón-carpeta]`. Nuevas props `onExploredChange(row, value)`, `onCreateFolder(row)`. `MarkerBadges` no cambia.
- `frontend/src/components/SpeciesLinks.tsx` — agregar el switch `[visited]` al inicio de cada `SourceLink`. Nuevas props `visited: Set<string>`, `onToggleVisited(source, value)`. Estilo visited: `border-muted` + `text-slate` + strikethrough (según spec del issue #68).
- `frontend/src/components/ExplorerPanel.tsx` (nuevo) — `<iframe sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads" src={activeLink?.url ?? ""} aria-label={...} />`. Se monta dentro de la columna derecha de `App.tsx`. Renderiza un estado "ninguna fuente seleccionada" cuando `activeLink` es null. Un fallback "X-Frame-Options bloqueado" se renderiza cuando el `onError` del iframe dispara (la carga del iframe falla por cualquier razón). El panel es `sticky top-0` para mantenerse visible mientras el usuario hace scroll en la grilla de dispatch.
- `frontend/src/store/workspace.ts` (nuevo) — ver §6.
- `frontend/src/api.ts` — agregar `setExplored`, `unsetExplored`, `createSpeciesFolder`, `getSpeciesFolder`, `recordLinkVisited`, `listLinkVisited`, `unrecordLinkVisited`. La unión discriminada `ApiResult<T>` se mantiene; los métodos nuevos siguen la forma de `fetchRoots`.
- `frontend/src/App.tsx` — montar `<ExplorerPanel>` debajo del bloque `<SpeciesLinks>` / `<Breadcrumb>`; el panel renderiza siempre que `activeLink` sea no-null (es decir, cuando el usuario hizo click en un enlace). El store Zustand `cascadePath` se mantiene; sin cambios al listener `path:change` existente.

**Tests**:
- Backend (`taxon/tests/`): `test_workspace_resolver.py` (unit, los helpers nuevos), `test_api_router_workspace.py` (integración vía FastAPI TestClient + `sqlite:///:memory:` con las tablas nuevas creadas vía `Base.metadata.create_all`); expandir `test_api_sqlite_only_router.py` si el schema cambia.
- Frontend (`frontend/tests/`): `SpeciesList.workspace.test.tsx` (checkbox explored + botón carpeta + persistencia al recargar), `SpeciesLinks.visited.test.tsx` (toggle del switch + estilo disabled), `ExplorerPanel.test.tsx` (`src` del iframe matchea el enlace activo; atributos sandbox; aria-label; fallback para X-Frame-Options), `workspace.store.test.ts` (set / unset / optimistic update / hydrate), `api.workspace.test.ts` (URL + decode de cada método nuevo).

**Specs OpenSpec** (delta specs, según el workflow archive-required de `openspec/config.yaml`):
- Nuevo `openspec/specs/species-folder/spec.md` (sub-feature B: creación de carpeta + persistencia).
- Nuevo `openspec/specs/link-visited/spec.md` (sub-feature C: switch visited por enlace + persistencia).
- Nuevo `openspec/specs/species-explored/spec.md` (sub-feature A: flag explored + persistencia).
- Delta sobre `openspec/specs/taxonomy-hierarchy/spec.md` (sin cambios — el contrato del resolver se preserva; este change usa `resolve_path_by_display_level` verbatim).
- Delta sobre `openspec/specs/species-search-links/spec.md` (sin cambios — el dispatch de 13 enlaces se mantiene; solo crece la UI que lo rodea).

**Entrada de learn-es** (`learn-es/2026-08-15-species-folder-explorer.md` + mirror español `documents-es/learn-es/2026-08-15-species-folder-explorer-es.md`): escrita tras CI verde según AGENTS.md §2.

## Restricciones descubiertas

1. **No hay Alembic** (verificado). El plan de migración debe ser un script `python -m taxon.migrate` O una llamada `Base.metadata.create_all(engine)` doblada dentro del lifespan para las tablas nuevas (lo segundo es consistente con cómo el path de tests bootea el schema; lo primero es consistente con cómo `taxon/import_data.py` construye las tablas `taxa` / `species_paths` out-of-band).
2. **`Proyecto-Aqualife/` no existe en el filesystem** (verificado). La carpeta es el workspace project-root-relative del usuario y se creará en el primer `POST /api/species-folder/{g}/{e}`.
3. **No hay `python-dotenv`** en `pyproject.toml`. El patrón de env var es `os.environ.get("TAXON_*", DEFAULT)` directo — igual que `TAXON_DATABASE_URL`, `TAXON_TEMPLATES`, `TAXON_DATABASE`, `TAXON_DATABASE_URL`.
4. **El store `cascadePath` se queda** — `App.tsx` es estado mid-cascade. El nuevo `workspaceStore` es una preocupación aparte (datos de workspace per-species) y vive junto a `cascadePath` + `taxonomicTree`. Sin fusión.
5. **El catch-all `/api/{path:path}/taxon-links` debe quedarse registrado al final** (según el test de regresión `test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall`, ver `archive-report.md` para el precedente). Cada endpoint nuevo de workspace DEBE registrarse ANTES de ese catch-all.
6. **`SearchLink.label == source`** para ambos endpoints (`search_links.py:53`). El estado visited se keya en `source`, nunca en `url` (que cambia por substitución).
7. **13 templates, no 12** (el issue #68 dice ambos). El conteo canónico es 13; el drift de comentarios en `router.py:17,619` es stale.
8. **`TaxonRow` es un dataclass frozen**, no una fila ORM. Los helpers nuevos en `taxon/api/workspace.py` DEBEN construir `TaxonRow` vía el mismo patrón `_to_row` en `hierarchy.py:92` (o importar el helper).
9. **`Taxon.id` es autoincrement int; `Taxon.source_id` es el string opaco CLB**. Los targets de FK en las tablas nuevas deben ser `taxa.id` (integer) para `species_folders.species_id`, `link_visited.species_id`, y `explored_flags.species_id` (si se elige la opción (b)).
10. **`species_paths` está vacío en `col.db`** — el breadcrumb builder en `species.py::build_breadcrumb` camina la cadena de padres vía `Taxon.parent_id`, no vía `species_paths`, así que el breadcrumb sigue siendo resoluble. El código nuevo NO depende de `species_paths`.
11. **Pencil MCP deshabilitado** — el diseño va vía `docs/design/species-folder-explorer.md` markdown prescriptivo, NO una página `.pen` (mismo precedente que `arbol-col-browse`).
12. **Strict TDD activo** (`openspec/config.yaml` `strict_tdd: true`): cada tarea escribe el archivo de test primero (RED), afirma el fallo, implementa el mínimo (GREEN), refactoriza. El drift del PR3 de `arbol-col-browse` previo enseña que el fallo de transporte de la fase apply puede enmascarar una violación MUST — cada requisito MUST de backend y frontend recibe un test dedicado que pinea el contrato WHEN/THEN.
13. **El budget de review de PR es 400 líneas** (`additions + deletions`, goldens excluidos). El PR3 de `arbol-col-browse` previo entró en 3 PRs chained (backend, frontend, learn-es); la estrategia de PR de este change es `auto-chain` según la cache de pre-flight del orchestrator.

## Preguntas abiertas para spec/design

1. **Forma de storage para el flag explored**: columna en `taxa` (desnormalizado; frágil ante re-import) vs nueva tabla `explored_flags` (ortogonal; join extra). La fase de proposal DEBE elegir. Recomendación desde la exploración: tabla nueva (ortogonal a los rebuilds de `taxon/import_data.py`).
2. **Semántica de fallo en creación de carpeta**: cuando `os.makedirs` levanta `PermissionError` (filesystem read-only, parent no escribible), ¿el endpoint retorna 500, 503, o 409 con un hint de retry? El envelope de error debe ser uniforme con `ErrorResponse` (`{detail: str}`) — elegir el status.
3. **Normalización de la ruta de carpeta**: el walk del breadcrumb vía `resolve_path_by_display_level` retorna el `name` canónico (sin citation); ¿un join con `os.sep` + lowercase + percent-decode es la ruta correcta, o queremos `safe_name` (`re.sub(r"[^\w\s-]", "_", segment)`) para manejar el raro segmento non-ASCII? La especie `Panthera tigris` está bien; la ruta visible para el usuario podría querer espacios preservados o reemplazados. Elegir una política y pinearla con un test.
4. **De-duplicación de carpeta entre re-imports**: el PK de la fila `species_folders` es `species_id INTEGER`; el re-import de `data/taxon.db` puede bumpear `taxa.id` (el autoincrement se resetea cuando se recrea la tabla). ¿El endpoint camina la especie por `(genus, epithet)` primero y re-vincula la fila, o falla con un error de PK stale? Elegir una política de reconciliación.
5. **Forma del endpoint link visited**: `POST /api/link-visited/{genus}/{epithet}` body `{source: "Wikipedia"}` → set idempotente; `DELETE` para unset. O un `PUT` con `{visited: true|false}`. El patrón `POST/DELETE` matchea los endpoints del flag explored; el `PUT` es un endpoint menos pero menos REST-puro. Elegir.
6. **Endpoint de hydrate del workspace**: al montar la app, ¿el SPA trae un solo envelope (`GET /api/workspace`) o muchos (`GET /api/explored/list` + `GET /api/link-visited/list`)? Un envelope mantiene la superficie wire más chica; muchos mantienen los contratos de endpoint más estrechos. Elegir. El endpoint species-folder puede ser lazy-fetched en el mount de `SpeciesList` (sin lista global necesaria; la fila solo conoce su propia especie).
7. **UX del fallback de X-Frame-Options del iframe**: cuando una fuente rechaza embedding, renderizar (a) un iframe en blanco + error en consola, (b) una tarjeta placeholder "esta fuente rechaza embedding — abrir en nueva pestaña" con un botón, (c) auto-open en nueva pestaña y mostrar un toast. (b) es el más descubrible y matchea la wording de "graceful degradation" del issue #68. Elegir.
8. **Alcance del estado active-link**: cuando el usuario hace click en un enlace del panel per-taxon breadcrumb-links (click de segmento, sin epithet), ¿el explorer se activa? Si sí, la URL del iframe substituye el `name` canónico del segmento, no de ninguna especie — el target de substitución es el segmento. Si no, el explorer solo activa tras un click de especie. El issue #68 dice "todo esto está gated por el switch por enlace: solo la URL del enlace actualmente activo se carga en el iframe" — pero no dice qué set de enlaces cuenta como "activo". Elegir: solo-especie (más limpio) o ambos (más rico).
9. **Comportamiento sticky del `<ExplorerPanel>`**: `sticky top-0` mantiene el iframe visible durante scroll; algunos browsers throttlean iframes sticky y el iframe re-carga en cada scroll. `position: fixed` en una columna separada lo mantiene siempre visible pero se come el layout. Elegir el layout.
10. **Posición del switch en `<SpeciesLinks>`**: el switch `[visited]` al inicio (antes del label del enlace) hace que el switch sea el primer tab stop, bueno para teclado pero rompe la memoria muscular "click el enlace para abrir". El switch `[visited]` al final (después del label) preserva la affordance de click pero agrega ruido visual. Elegir.
11. **Set de atributos sandbox**: la exploración flaguea `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads`. Si el usuario quiere descargar imágenes de Google Images, `allow-popups` es requerido (Google sirve las descargas de imágenes vía popup). Confirmar vía test contra el sitio en vivo O aceptar la caveat del issue #68.
12. **Key de `link_visited`: source-label vs URL**: `source` es estable (template-driven) y human-readable; `url` cambia por substitución (contiene el query de la especie). Keyear en `source` está bien; confirmar.
13. **Estado del workspace al cargar la app**: hidratar eagerly al mount de App (`useEffect` que llama los endpoints de hydrate), o lazy mientras el usuario hace scroll en una fila de especie. Eager mantiene el switch visited siempre actual; lazy mantiene el cold-start chico. Elegir.

## Riesgos flagueados

- **Race de filesystem en la primera creación de carpeta**: `os.makedirs` no es atómico entre procesos. Si dos instancias del SPA arrancan (ej. el usuario abre dos pestañas), ambas POSTean al endpoint; el insert de la fila es idempotente sobre `species_id PK`, pero el segundo POST retorna 409 en vez de 201. Pinear el comportamiento con un test.
- **`AQUALIFE_ROOT` no seteado + cwd ≠ project root**: si el usuario corre `python -m taxon.main` desde un subfolder de worktree (común en el workflow de `develop`), `./Proyecto-Aqualife/` resuelve a `<worktree>/Proyecto-Aqualife/`, no a `<project>/Proyecto-Aqualife/`. El endpoint DEBE fallar fuerte (503 o 500 con `AQUALIFE_ROOT not resolvable from cwd <cwd>`) o aceptar un path absoluto. Pinear con un test que corre desde un subfolder y afirma el envelope de error.
- **Rechazo de X-Frame-Options / CSP**: muchas fuentes (Wikipedia, Google Scholar, BHL) rechazarán cargarse en cualquier iframe. El fallback de graceful degradation es obligatorio, no opcional. Sin él, el panel del explorer se ve roto (iframe en blanco) en las fuentes más usadas. Mitigación: el fallback `target="_blank"` debe ser obvio (un botón + tooltip, no una affordance escondida).
- **Sandbox del iframe + downloads**: Safari controla downloads iniciados por iframe de forma más estricta que Chrome/Firefox. El fallback `target="_blank"` del SPA cubre a usuarios Safari — pero el fallback debe ser alcanzable desde dentro del iframe (popups bloqueados en algunas configs). Mitigación: mantener el `<a target="_blank">` renderizado como un `<a>` regular fuera del iframe para que el usuario siempre pueda escapar.
- **Churn de schema por re-imports**: el importer recrea `taxa` (y bumpea `id`); cualquier FK desde las tablas nuevas a `taxa.id` se vuelve stale al re-import. El endpoint de creación de carpeta DEBE caminar por `(genus, epithet)` no por `taxa.id` raw. La fila de species_folders necesita columnas `genus TEXT, epithet TEXT` (o un re-bind en cada lectura) para que los re-imports puedan recuperar el FK. Pinear con un test.
- **Fallo de transporte enmascarando violaciones MUST**: el PR3 de `arbol-col-browse` previo enseñó que `sdd_task_result_empty` (a nivel de transporte) puede enmascarar drift de spec. La fase de proposal DEBE enumerar cada requisito MUST explícitamente (uno por cláusula WHEN/THEN en los deltas); la fase de apply DEBE pinear cada uno con un test dedicado antes del commit verde.
- **Riesgo de budget de 400 líneas**: el PR1 de backend (3 tablas nuevas + 4-6 endpoints nuevos + 8-12 tests) es ~250-350 líneas; el PR2 de frontend (columna al final en SpeciesList + switch al inicio en SpeciesLinks + ExplorerPanel + workspaceStore + extensiones de api.ts + 4-6 archivos de test) es ~600-900 líneas — **por encima del budget**. El pre-flight del orchestrator cacheó `auto-chain` + budget `review=400`, lo que obliga a PRs chained. La fase de proposal DEBE forecast el budget y dividir. Split recomendado: PR1 backend (≤350), PR2 frontend workspace store + cambios SpeciesList + SpeciesLinks (≤350), PR3 ExplorerPanel + design-doc + learn-es (≤350). El pase de diseño Pencil + impeccable es un gate duro según AGENTS.md §5 y debe aterrizar ANTES de que arranque PR1.
- **Strict TDD requiere pineo de test por requisito**: cada cláusula WHEN/THEN en los specs nuevos DEBE tener al menos un test antes del commit verde. Saltarse esto es exactamente lo que produjo el drift previo. La fase de proposal DEBE enumerar el conteo de tests.
- **No hay página `.pen`**: el design doc prescriptivo es la única superficie de diseño que este change entrega. Si el drift de diseño entre el doc y la implementación no es atrapado por `impeccable` antes del código, el resultado es una feature cuya UX es una moneda al aire (según la narrativa de drift del PR3 de `arbol-col-browse`). La fase de proposal DEBE reservar un paso de verificación donde los componentes del implementador se re-chequeen contra el diseño prescriptivo antes de que el PR abra.
- **Interacción `cascadePath` ↔ `workspaceStore`**: el workspace store es per-species; cascadePath es per-cascade-step. Un usuario que hace click en un segmento de breadcrumb (cascadePath actualiza) sin clickear una especie no tiene species_id para el workspace store. El activeLink del panel del explorer debe o bien keyear en `(cascadePath, source)` (path-level) o quedarse null hasta que se resuelva una especie. El riesgo es que el explorer se active sobre un segmento non-species y substituya el nombre del segmento, lo cual el usuario podría encontrar sorprendente. La fase de diseño DEBE escopar la regla de activación.

## Listo para Proposal

**Sí** — el orchestrator debe lanzar `sdd-propose` a continuación. La exploración cubre cada dimensión que el issue #68 señala: backend (router / schema / resolver), frontend (SpeciesList / SpeciesLinks / ExplorerPanel nuevo / workspaceStore), modelo de datos (tablas nuevas + la bifurcación column-vs-table del flag explored), filesystem (`AQUALIFE_ROOT`), sandbox del iframe + graceful degradation de X-Frame-Options, precedente del diseño con Pencil-MCP deshabilitado, y estructura de deltas OpenSpec. La fase de proposal DEBE decidir la forma de storage (columna vs tabla) y el split de la cadena de PRs antes de que arranque la fase de diseño.
