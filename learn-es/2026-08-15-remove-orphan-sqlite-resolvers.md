# Orphan SQLite resolver modules removed (PR #61)

## Qué

`taxon/api/path_children.py` y `taxon/api/species_list.py` eran dos resolvers SQLite scaffolded en una iteración previa como reemplazos de los resolvers de la API en vivo. Tras el PR #58, la cadena convergió en `taxon/api/sqlite_resolver.py`, que es lo que `taxon/api/router.py` consume hoy. Los huérfanos nunca se importaron desde código de producción ni desde tests. El PR #61 los elimina.

## Cómo

Cambio mecánico sin lógica nueva. Verificación previa con ripgrep para confirmar cero importadores:

```
rg "from taxon\.api\.path_children|import taxon\.api\.path_children|taxon\.api\.path_children\b" --type py
→ (sin coincidencias)
rg "from taxon\.api\.species_list|import taxon\.api\.species_list|taxon\.api\.species_list\b" --type py
→ (sin coincidencias)
```

`taxon/api/__init__.py` no reexportaba ninguno de los dos módulos ni los declaraba en un `__all__`, así que no hubo que tocar el `__init__.py`. Borrado directo con `git rm`.

## Dónde

- `taxon/api/path_children.py` — eliminado (145 LOC).
- `taxon/api/species_list.py` — eliminado (106 LOC).

Ningún otro archivo del árbol modificado.

## Por qué

Acumular código muerto cuesta navegar el árbol y desorienta a quien hace `git grep` buscando el origen de una función. El módulo `taxon/api/sqlite_resolver.py` ya cubre la funcionalidad que los huérfanos pretendían ofrecer. Mantenerlos significaba pagar el costo de tres archivos para resolver el mismo problema.

## Cómo funciona

No hay cambio de comportamiento. Los huérfanos no tenían tests, ningún endpoint los invocaba, y ningún test dependía de su forma. La cobertura actual de la cascada (12 tests en `taxon/tests/test_api_sqlite_only_router.py`, 3 tests adicionales en `test_api_sqlite_only_indented_fixtures.py` desde el PR #62) sigue garantizando el contrato.

## Workflows

- **CI**: pytest 147 verde, ruff check y format limpios, mypy strict sin issues (el conteo de archivos bajó de 31 a 29), vitest 69/69.
- **Branching**: rama `chore/remove-orphan-sqlite-resolvers` desde `develop`, worktree en `../taxon-worktrees/chore-remove-orphan-sqlite-resolvers`, merge de vuelta por merge ort tras CI verde. Cleanup de worktree + rama local conforme a AGENTS.md §4.

## Lecciones aprendidas

- **Verificar antes de borrar, siempre.** Un `git grep` rápido (o `rg` en este caso) sobre el árbol entero evita el susto de descubrir un consumidor oculto. Aquí la verificación fue limpia; el susto memorable fue en el PR #60, donde `httpx` parecía borrable y resultó indispensable.
- **El "código muerto aparente" merece una segunda mirada.** Los huérfanos de hoy llevan meses en el árbol, esperando el PR de cleanup. Es legítimo diferirlo a un PR separado para no inflar el scope del cambio principal, siempre que el follow-up quede registrado en el learn-es o en un issue. En esta sesión el follow-up estaba nombrado en `/learn-es/2026-08-15-remove-dead-clb-modules.md`, así que la próxima sesión lo tomó sin ambigüedad.

## Follow-up PRs (no en este commit)

- **PR #62** (mergeado en la misma sesión) cierra el gotcha de `display_level IS NULL` en el resolver de cascada, permitiendo que los tests convivan con el importador indented.
- **Run del import GBIF Backbone completo** (7,7 M de filas, ~789 MB) — desbloqueado por el PR #62, queda como tarea operativa fuera del alcance de cleanup.
