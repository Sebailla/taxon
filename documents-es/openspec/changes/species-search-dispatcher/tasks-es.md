# Tareas: Despachador de Búsqueda de Especies

## Pronóstico de Carga de Revisión

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Líneas modificadas: 600-900. Estrategia de entrega: ask-on-risk. 6 PRs encadenados; base de cada hijo = rama del PR previo. Unidades: (1) parser+schema+import_data+search_links; (2) FastAPI+409; (3) Pencil+impeccable; (4) React+Cascade; (5) SpeciesLinks+Toggles+AmbiguityPicker; (6) Docs+CI+`/learn-es`.

## Fase 1: Cimiento / Infraestructura

- [x] 1.1 Crear `taxon/pyproject.toml` con deps (fastapi, uvicorn, sqlalchemy, pydantic, pytest, ruff, mypy).
- [x] 1.2 Crear `taxon/.gitignore` excluyendo `data/`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.pen`.
- [x] 1.3 Prueba RED `taxon/tests/test_parser.py` con fixtures: †, =, ?, [unassigned], Candidatus, anidamiento profundo.
- [x] 1.4 Impl GREEN `taxon/taxon/parser.py` pila de indentación streaming + extracción de marcadores.
- [x] 1.5 Prueba RED `taxon/tests/test_schema.py` invariantes `Taxon`/`SpeciesPath` + columnas de marcadores.
- [x] 1.6 Impl GREEN `taxon/taxon/schema.py` modelos SQLAlchemy con columnas de marcadores + índices.
- [x] 1.7 Prueba RED `taxon/tests/test_import.py` para conteo/integridad sobre `dataset-2011.txt`.
- [x] 1.8 Impl GREEN `taxon/taxon/import_data.py` inserciones por lotes en streaming contra `dataset-2011.txt`.
- [x] 1.9 Prueba RED `taxon/tests/test_search_links.py` paridad URL verbatim vs `templates.md` (incl. Sci-hub `https://sci-hub.ru/match/{q}`), `quote_plus(s, safe='')`.
- [x] 1.10 Impl GREEN `taxon/taxon/search_links.py` parsea `docs/sources/templates.md`, emite 12 URLs.

## Fase 2: Capa API

- [ ] 2.1 Prueba RED `taxon/tests/test_api_hierarchy.py` para cascada (404, 409, orden, casing).
- [ ] 2.2 Prueba RED `taxon/tests/test_api_species_list.py` para `/genera/{g}/species` + `include=` + cursor.
- [ ] 2.3 Prueba RED `taxon/tests/test_api_links.py` para 12 entradas en `/species/{genus}/{epithet}/links`.
- [ ] 2.4 Prueba RED `taxon/tests/test_api_ambiguity.py` para 409 con `candidates[]` de breadcrumb.
- [ ] 2.5 Impl GREEN `taxon/taxon/api/__init__.py` fábrica de app FastAPI + esquemas Pydantic.
- [ ] 2.6 Impl GREEN `taxon/taxon/api/router.py` rutas URL-encoded + handler 409.
- [ ] 2.7 Impl GREEN `taxon/taxon/main.py` punto de entrada uvicorn.

## Fase 3: Diseño Frontend (ANTES del código según AGENTS.md §5)

- [ ] 3.1 Crear `taxon/.pen` vía Pencil MCP: cascada + selector ambigüedad + panel enlaces especie.
- [ ] 3.2 Auditar bajo `impeccable` (a11y, jerarquía, tipografía, color, motion, anti-patrones); iterar.
- [ ] 3.3 Documentar aprobación en `taxon/docs/design/approval.md` (fecha+sign-off).

## Fase 4: Implementación Frontend

- [ ] 4.1 Scaffold `taxon/frontend/` Vite (React 18 + TS + TailwindCSS 3) + Vitest/Testing Library.
- [ ] 4.2 Prueba (R) `taxon/frontend/tests/api.test.ts` cliente tipado + manejo de 409.
- [ ] 4.3 Impl (G) `taxon/frontend/src/api.ts` cliente tipado.
- [ ] 4.4 Prueba (R) `taxon/frontend/tests/Cascade.test.tsx` reset al cambiar padre + abort + loading/error/vacío.
- [ ] 4.5 Impl (G) `taxon/frontend/src/Cascade.tsx` 5 dropdowns + 6ª lista scrollable de especies.
- [ ] 4.6 Prueba (R) `taxon/frontend/tests/SpeciesLinks.test.tsx` 12 botones + atributos de enlace externo.
- [ ] 4.7 Impl (G) `taxon/frontend/src/SpeciesLinks.tsx`.
- [ ] 4.8 Prueba (R) `taxon/frontend/tests/Toggles.test.tsx` semántica OR + default off.
- [ ] 4.9 Impl (G) `taxon/frontend/src/Toggles.tsx`.
- [ ] 4.10 Prueba (R) `taxon/frontend/tests/AmbiguityPicker.test.tsx` lista candidatos con breadcrumb.
- [ ] 4.11 Impl (G) `taxon/frontend/src/AmbiguityPicker.tsx`.

## Fase 5: Documentación y Limpieza

- [ ] 5.1 Escribir `taxon/README.md` (EN) + espejo ES `taxon/documents-es/README-es.md`.
- [ ] 5.2 CI en `develop` (pytest, vitest, ruff, mypy, eslint).
- [ ] 5.3 Tras merge verde: crear `/learn-es/2026-08-09-species-search-dispatcher.md`.
- [ ] 5.4 Commits: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`; sin atribución de IA.
