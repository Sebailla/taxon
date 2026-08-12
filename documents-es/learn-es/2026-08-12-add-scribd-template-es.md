# Añadir Scribd como 13º template de search-source (PR #25)

# Qué

Añadido `Scribd` como el 13º template de search-source al final
de la lista de dispatch (después de Sci-hub). La URL es la
verbatim `https://es.scribd.com/search?query={q}`, siguiendo la
misma convención de sustitución `{q}` que los otros 12 templates.
Subí el guard de conteo de `load_templates` de 12 a 13 y
actualicé dos archivos de test para esperar 13 templates.

Este es el primer template nuevo desde que los 12 originales
fueron capturados del Google Sheet legacy el 2026-08-09.

# Cómo

### Archivo de templates

Una nueva fila en `docs/sources/templates.md`:

```markdown
| Sci-hub      | `https://sci-hub.ru/match/{q}` (substitutes species) |
| Scribd       | `https://es.scribd.com/search?query={q}` |
```

El orden se preserva por la regex del parser; añadir una fila
al final coloca a Scribd último en el grid de dispatch.

### Guard de conteo

`taxon/search_links.py`:

```python
if len(templates) != 13:
    raise ValueError(f"Expected exactly 13 search templates, found {len(templates)}")
```

El guard existe para detectar drift entre la hoja de cálculo (hoy
templates.md) y las expectativas de los tests. Cada futuro
template añadido requiere subir este número y los asserts
correspondientes en los tests.

### Tests

`taxon/tests/test_search_links.py`:

- `test_load_templates_preserves_exact_order_and_verbatim_urls`
  ahora verifica la tupla ordenada de 13 terminando en
  `"Scribd"`, chequea la nueva URL en índice `-1`, y re-apunta
  los asserts existentes de Sci-hub y Photos a los índices `-2`
  y `-3` respectivamente.
- `test_build_search_links_uses_quote_plus_for_every_template`
  verifica que las URLs sustituidas terminen con la query
  encoded de Scribd y que la segunda desde el final siga siendo
  Sci-hub.

`taxon/tests/test_api_species_links.py`:

- El test de conteo del envelope renombrado de
  `test_links_envelope_emits_exactly_twelve_links` a
  `..._thirteen_links`, conteo 12 → 13.
- El test de orden lee templates.md en runtime, así que toma
  la nueva fila automáticamente. Solo se actualizó el docstring.

El test de orden lee del disco en cada corrida, lo que hace a la
suite resiliente a adiciones/eliminaciones siempre que
templates.md se mantenga como la única fuente de verdad.

# Dónde

- `docs/sources/templates.md` — una fila añadida.
- `taxon/search_links.py` — guard de conteo subido.
- `taxon/tests/test_search_links.py` — asserts de orden + conteo.
- `taxon/tests/test_api_species_links.py` — assert de conteo +
  docstrings.

# Por qué

Los 12 templates embarcados en PR #16 vinieron del Google Sheet
legacy capturado el 2026-08-09. Este es el primer template nuevo
desde entonces, solicitado explícitamente para expandir las
opciones de dispatch para usuarios hispanohablantes de la
herramienta de búsqueda de species. La URL de búsqueda de Scribd
se capturó del endpoint upstream; no hizo falta DOM con JS
renderizado para descubrir el parámetro de query.

### Sobre la pregunta del modal/iframe

El usuario también preguntó si Scribd podía abrir en un modal
in-app con iframe en lugar de una nueva pestaña. Investigué el
sitio upstream antes de commitear: `https://es.scribd.com/
search?query=...` devuelve un shell de anti-bot "Client
Challenge" de Cloudflare/F5 bajo `Content-Security-Policy:
default-src 'self'`, que bloquea el framing cross-origin desde
cualquier dominio que no sea scribd. Un iframe dentro de
`taxon.localhost` mostraría la página de challenge, no los
resultados de búsqueda — una UX peor que abrir una nueva
pestaña. La nueva fuente mantiene entonces el mismo
comportamiento `<a target="_blank">` que las otras 12 por
consistencia. La decisión está documentada en el cuerpo del PR
para que futuros lectores no la re-litiguen.

# Cómo funciona

Cuando el usuario hace click en una fila de species:

1. El Cascade despacha el evento `taxon:select` con el
   breadcrumb resuelto + parent segments (ahora validados con
   Zod según PR #24).
2. El App construye `/api/{path}/{genus}/{epithet}/links` (con
   el segmento genus incluido, según PR #22).
3. El endpoint FastAPI llama a `load_templates()` que lee
   `docs/sources/templates.md` y devuelve 13 templates
   ordenados.
4. `build_search_links()` sustituye `quote_plus(species)` en
   cada template. El 13º template (Scribd) produce
   `https://es.scribd.com/search?query={encoded_species}`.
5. El endpoint retorna el envelope de 13 links; el frontend
   renderiza el grid de 4 columnas con Scribd en la posición
   13 (visualmente debajo de Sci-hub en el mismo flujo de
   filas).

# Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). Todos verdes. El job lighthouse audita el bundle
  de frontend de producción que incluye la nueva fuente como
  botón — no hay regresión de accesibilidad porque
  `<a target="_blank" rel="noopener noreferrer">` ya cubre las
  13 fuentes.
- **Revisiones** — 2 `work-unit-commits`:
  1. `f66b37a test(backend): add Scribd as the 13th search-source template (RED-first)`
  2. `77d44b6 feat(backend): add Scribd as the 13th search-source template`
- **Adiciones futuras** — cuando la hoja gane una fila 14, el
  flujo es: editar `templates.md`, subir el guard de conteo,
  subir la tupla ordenada del test, subir el assert de conteo.
  No se necesitan otros cambios de código.

# Aprendizajes

- **El guard de conteo en `load_templates` es un detector de
  drift, no un límite arbitrario.** Atrapa el modo de fallo en
  el que alguien edita `templates.md` sin actualizar los tests.
  Vale la pena conservarlo, aunque añada una pequeña carga de
  mantenimiento en cada adición.
- **`X-Frame-Options` y CSP `frame-ancestors` son cambios de
  contrato silenciosos para cualquier feature de "embeber un
  sitio externo".** Siempre chequear `curl -sI` en los headers
  de respuesta antes de prometer iframe embebido a un usuario.
  La página de challenge de Cloudflare/F5 es el bloqueador más
  común para fuentes académicas (Sci-hub, ResearchGate,
  Academia.edu están en la misma situación).
- **El test de orden lee templates.md en runtime** — ese patrón
  (assert contra el doc vivo, no contra una lista hardcoded)
  escala mejor que mantener dos fuentes de verdad. La lista
  hardcoded en `test_search_links.py` sigue ahí porque también
  fija la estabilidad de la URL de Photos y la posición de
  Sci-hub; para chequeos de orden puro gana la versión
  disk-read.
- **`work-unit-commits` mantiene RED y GREEN legibles en
  aislamiento.** Un revisor puede leer el commit del test y ver
  exactamente cuál es el contrato, y después leer el commit de
  implementación y ver exactamente qué cambió para
  satisfacerlo.
