# Propuesta: Despachador de Búsqueda de Especies

## Intención
Hoy el usuario recorre la taxonomía de WoRMS y los enlaces de búsqueda por especie a través de una hoja de cálculo de Google Sheets que resulta difícil de mantener, difícil de compartir y no ofrece acceso programático. Este cambio reemplaza la hoja de cálculo con un backend tipado (Python + FastAPI + SQLite) más una interfaz React con selecciones en cascada, de modo que tanto investigadores como acuaristas puedan navegar Reino→Género, elegir una especie y despachar hacia los mismos 12 orígenes de búsqueda que la hoja codifica hoy.

## Alcance
### Dentro del Alcance
- Un PR fundacional de extremo a extremo: parser del backend, esquema SQLite, endpoints FastAPI, UI React, y un segmento del dataset funcionando en verde.
- 12 endpoints/URLs de búsqueda que coincidan literalmente con `docs/sources/templates.md`, incluyendo la URL literal M9 de Fotos.
- HTTP 409 Conflict con `candidates[]` para búsquedas de especies ambiguas.
- 5 desplegables en cascada (Reino→Filo→Clase→Orden→Familia→Género) + 6ª lista fija y desplazable de especies.
- Filtros toggle para extintas (`†`), sinónimos (`=`), inciertas (`?`), sin asignar; por defecto solo aceptadas.
### Fuera del Alcance
- Autenticación, multiusuario, rutas de escritura (taxon es de solo lectura).
- Hosting productivo, Docker, despliegue en la nube.
- Suite E2E de Playwright (capa opcional, diferida).
- Localización más allá de la copia de UI en español ya existente.

## Capacidades
### Capacidades Nuevas
- `taxonomy-hierarchy`: navegar Reino→Género mediante rutas URL-encoded por nombre de ruta.
- `species-list-by-genus`: listar especies de un Género dado (6ª lista).
- `species-lookup`: resolver un par (género, epíteto); devolver 409 con candidatos ante ambigüedad.
- `species-search-links`: emitir 12 URLs de despacho por especie, literalmente desde las plantillas de la hoja.
- `inclusion-filters`: toggle para extintas/sinónimos/inciertas/sin asignar; por defecto solo aceptadas.
### Capacidades Modificadas
- (ninguna — proyecto greenfield)

## Enfoque
Lista de adyacencia en SQLite (tabla `taxa` con `parent_id`) más una proyección materializada `species_paths` para consulta O(1) de la jerarquía. Parser por streaming sobre `dataset-2011.txt` (1.394.847 líneas) con inserciones por lotes y criterios de aceptación medidos. FastAPI expone rutas URL-encoded por nombre de ruta (`/api/kingdoms/{k}/phyla/{p}/.../genera/{g}/species`). La ambigüedad se resuelve devolviendo HTTP 409 con candidatos de ruta completa para que la UI muestre un selector. SPA con React 18 + Vite + TailwindCSS 3 con cinco desplegables en cascada y una sexta lista fija de especies. TDD estricto desde el parser hacia afuera: test rojo → implementación → verde. El primer PR es monolítico y fundacional; los cambios posteriores se dividen por capacidad.

## Áreas Afectadas
| Área | Impacto | Descripción |
|------|---------|-------------|
| `/Users/sebailla/Developer/taxon/` | Nuevo | raíz de proyecto greenfield |
| `/Users/sebailla/Developer/research/worm/dataset-2011.txt` | Fuente de solo lectura | datos de entrada (1,39M líneas, WoRMS-2011) |
| `/Users/sebailla/Developer/taxon/docs/sources/templates.md` | Nuevo | plantillas de enlaces de búsqueda capturadas desde la hoja |
| `taxon/data/taxon.db` | Nuevo (local) | BD SQLite, borrable para rollback |

## Riesgos
| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Rendimiento de importación de 1,39M de filas | Media | parser por streaming, inserciones SQLite por lotes, benchmarks indexados de aceptación |
| Colisiones de nombre de Género entre padres | Alta (conocida) | la API devuelve 409 con candidatos; la UI muestra selector |
| La URL de Fotos contiene parámetros de seguimiento que pueden caducar | Baja | preservada literal para paridad con la hoja; nota sobre override por variable de entorno |
| Contenido mixto HTTP vs HTTPS | Baja | preservado para paridad con la hoja; advertencia de seguridad en el README |
| Fronteras de archivos parciales a mitad de rama | Media | re-leer el dataset original, no las 4 partes divididas |
| Confusión con la política de ramas | Baja | documentada en AGENTS.md; el primer PR apunta explícitamente a develop |
| Saltarse la puerta de flujo de trabajo de UI | Media | la revisión con Pencil MCP + impecable debe preceder a cualquier código de UI |

## Plan de Rollback
- Revertir el PR que introduce la porción fundacional de backend + frontend.
- La base de datos es SQLite local bajo `taxon/data/taxon.db` — borrar el archivo elimina esquema y datos.
- No hay dependencias externas ni recursos en la nube que revertir.

## Dependencias
- `/Users/sebailla/Developer/research/worm/dataset-2011.txt` debe permanecer legible (solo lectura).
- Python 3.11+, Node 20+.
- Sin dependencias SaaS externas.

## Criterios de Éxito
- [ ] `/api/kingdoms/{name}/phyla/{name}/.../genera/{name}/species` devuelve la lista de especies.
- [ ] `/api/species/{genus}/{epithet}/links` devuelve 12 enlaces de búsqueda con URLs que coinciden literalmente con las plantillas de la hoja.
- [ ] Las búsquedas ambiguas de especie devuelven HTTP 409 con `candidates[]`.
- [ ] La UI React muestra 5 desplegables en cascada + lista fija de especies; toggles para extintas/sinónimos.
- [ ] Suites de pytest + vitest en verde; CI en `develop` en verde.
- [ ] Entrada `/learn-es/2026-08-09-...` creada tras el merge.

## Notas Operativas
- El PR apunta a `develop` (nunca a `main`). Worktree bajo `../taxon-worktrees/species-search-dispatcher`.
- El diseño de UI debe autorarse en Pencil MCP y auditarse bajo `impeccable` antes de que aterrice cualquier código de frontend.
- Conventional commits; sin atribución de IA; mensajes en inglés (`docs(es): …` para docs solo en español).
- Cada artefacto (incluida esta propuesta) debe tener un espejo en español bajo `/documents-es/openspec/`.
