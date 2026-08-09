# Diseño: Despachador de búsquedas de especies

## Enfoque técnico
Construir una API FastAPI de solo lectura sobre SQLite y una SPA React/Vite/Tailwind. Un analizador de pasada única lee `/Users/sebailla/Developer/research/worm/dataset-2011.txt`, mantiene una pila de indentación, inserta taxones por lotes y emite una fila `species_paths` por especie. El TDD estricto avanza: analizador → esquema/importación → API → cliente/componentes. El diseño Pencil MCP y la auditoría `impeccable` preceden al frontend.

## Decisiones de arquitectura

### Decisión: lista de adyacencia SQLite + proyección `species_paths`
**Elección**: `taxa(parent_id)` conserva cada rango/estado; `species_paths` guarda la ruta completa Reino→Especie y los indicadores.
**Alternativas**: Las CTE recursivas por solicitud agregan costo de lectura; las tablas por rango no representan fielmente profundidades irregulares o infraespecíficas.
**Justificación**: Consultas directas, candidatos de ambigüedad deterministas y fidelidad completa a la fuente.

### Decisión: transmitir el conjunto de datos original
**Elección**: Analizar `/Users/sebailla/Developer/research/worm/dataset-2011.txt` en O(n), con memoria O(profundidad) y transacciones por lotes.
**Alternativas**: Analizar por separado las cuatro partes divididas.
**Justificación**: Una división puede comenzar a mitad de una rama y perder el estado de ancestros.

### Decisión: nombres codificados en rutas con ambigüedad explícita
**Elección**: Resolución de nombres de ruta sin distinguir mayúsculas; segmentos desconocidos devuelven 404 y colisiones devuelven 409 con rutas estables en `candidates[]`. Los ID numéricos permanecen como identificadores de respuestas/candidatos.
**Alternativas**: Rutas basadas solo en ID.
**Justificación**: Cumple el contrato de rutas legibles sin adivinar entre nombres duplicados.

### Decisión: las plantillas se cargan desde la fuente documental
**Elección**: Analizar `docs/sources/templates.md` una vez al iniciar la aplicación en un conjunto ordenado e inmutable de 12 plantillas; sustituir cada plantilla con `quote_plus(species, safe='')`, incluido Sci-hub (`https://sci-hub.ru/match/{q}`).
**Alternativas**: Duplicar las plantillas en Python.
**Justificación**: Evita divergencias y conserva la URL literal de Fotos de M9.

### Decisión: la cascada obtiene un nivel por vez
**Elección**: Cada selección obtiene solo el rango siguiente; los cambios de ancestro limpian descendientes y cancelan solicitudes obsoletas. La sexta superficie es una lista fija de especies paginada por cursor (máximo 500/página).
**Alternativas**: Enviar el árbol de 1,39 millones de filas al navegador.
**Justificación**: Cargas predecibles y navegación receptiva.

## Flujo de datos

```text
dataset-2011.txt -> analizador de flujo -> inserciones por lotes en taxa
                                                |
                                                v
                                     proyección species_paths
                                                |
                              consultas/rutas FastAPI (404/409)
                                  |                       |
                            cascada React        generador de 12 enlaces
```

## Cambios de archivos

| Archivo | Acción | Descripción |
|---|---|---|
| `pyproject.toml`, `.gitignore` | Crear | Dependencias Python/herramientas; excluir BD y cachés generados. |
| `taxon/db.py`, `taxon/schema.py` | Crear | Motor/sesión y modelos `Taxon`/`SpeciesPath` con índices. |
| `taxon/parser.py`, `taxon/import_data.py` | Crear | Analizador con pila y CLI de importación idempotente por lotes. |
| `taxon/search_links.py` | Crear | Cargador inmutable de plantillas y generador exacto de URL. |
| `taxon/api/{__init__,router,schemas}.py`, `taxon/main.py` | Crear | Fábrica de aplicación, modelos de respuesta y rutas. |
| `tests/test_{parser,schema,import_data,api_hierarchy,api_species,api_links}.py` | Crear | Cobertura backend unitaria/de integración, primero en ROJO. |
| `frontend/` | Crear | Configuración Vite/React/Tailwind y estructura de aplicación. |
| `frontend/src/{api,Cascade,Toggles,SpeciesLinks,AmbiguityPicker}.tsx` | Crear | Cliente tipado y comportamiento de UI. |
| `frontend/tests/` | Crear | Pruebas de componentes con Vitest/Testing Library. |
| `.pen` | Crear mediante Pencil MCP | Diseño de UI aprobado; nunca se accede como texto plano. |
| `README.md`, `documents-es/README-es.md` | Crear | Instrucciones de ejecución/importación y espejo en español. |
| `data/taxon.db` | Generar, excluido de Git | Base SQLite regenerable. |

## Interfaces / contratos

`Taxon` guarda ID de fuente, padre, rango, nombres canónico/visible y cuatro indicadores. `SpeciesPath` guarda ID, rangos hasta género, nombre/visualización e indicadores. La jerarquía contiene exactamente `{id,name,display_name}`. Las páginas de especies contienen `items[]` y `next_cursor` opcional; `include` reconoce cuatro clases con OR e ignora valores desconocidos. Una coincidencia devuelve especie y ruta; una ambigüedad devuelve `409 {"candidates":[...]}` ordenado por ruta. Los enlaces son 12 entradas `{source,label,url}` ordenadas.

Las rutas incluyen `/api/kingdoms`, los niveles codificados Reino→Género, `/species?include=&cursor=` y `/api/species/{genus}/{epithet}/links`; una ruta completa resuelve el candidato elegido tras un 409.

## Estrategia de pruebas

| Capa | Qué | Enfoque |
|---|---|---|
| Unidad BE | Analizador/esquema/enlaces | Indicadores y combinaciones, Candidatus entre comillas, profundidad irregular, plantillas exactas, Fotos, Sci-hub, `quote_plus`. |
| Integración BE | Importación/API | SQLite temporal; conteos/integridad; rutas sin distinguir mayúsculas; orden estable; 404/409; filtros; cursor de 500 elementos. |
| Unidad/Componente FE | Cliente/cascada/UI | Tipado 409, limpieza de descendientes, cancelación de carreras, OR de filtros, carga/error/vacío, 12 enlaces y rutas. |
| E2E | Flujo completo | Playwright diferido/opcional. |

## Matriz de amenazas
El enrutamiento HTTP es comportamiento de la aplicación, pero no aplican los límites de ejecución/automatización: no hay ejecución documental, selección Git, commits/push, comandos de PR, shell, subprocesos ni integración de procesos.

## Migración / despliegue
Proyecto nuevo; regenerar con `python -m taxon.import_data`. Sin indicadores de funcionalidad. El primer PR fundacional es intencionalmente monolítico.

## Preguntas abiertas
Ninguna bloqueante.