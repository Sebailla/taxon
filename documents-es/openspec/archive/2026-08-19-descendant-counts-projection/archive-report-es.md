# Reporte de Archivo: descendant-counts-projection

## Estado: archivado

El cambio cerró de extremo a extremo en `develop`. PR #86 mergeado como squash commit `915b1d6`. `/learn-es/2026-08-19-descendant-counts-projection.md` escrito conforme a AGENTS.md §2. Este reporte de archivo registra el estado final de los artefactos del cambio.

## Qué se envió

- Nueva clase ORM `TaxonDescendantCount` en `taxon/schema.py`.
- Nuevo módulo `taxon/api/projections.py` (~275 LOC) que posee:
  - `register_display_level(engine)` — cierra el gap de registro de la SQLite user function sobre engines bare.
  - `lookup_one`, `lookup_many` — lectores de cache.
  - `_table_exists`, `_projected_parent_ids` — helpers de población.
  - `materialize_for_parent`, `materialize_all` — workers de rebuild con presupuesto SLO.
- `taxon/migrate.py` ampliado: `_run_apply` crea la tabla de projection en `apply`; nuevo subcomando `apply-projection`.
- `taxon/api/tree.py:_count_descendant_species` consulta la cache antes del threshold guard.
- `taxon/api/_tree_tiers.py:_batch_species_counts` fusiona las filas cacheadas antes del seed de la CTE.
- `taxon/import_data.py` reconstruye la projection al final de cada importación exitosa.

## Artefactos finales

| Artefacto | Ruta | Estado |
|-----------|------|--------|
| Propuesta | `openspec/changes/descendant-counts-projection/proposal.md` | listo |
| Spec | `openspec/changes/descendant-counts-projection/specs/descendant-counts-projection/spec.md` | listo |
| Spec (delta) | `openspec/changes/descendant-counts-projection/specs/taxonomic-tree-browse/spec.md` | listo |
| Diseño | `openspec/changes/descendant-counts-projection/design.md` | listo |
| Tasks | `openspec/changes/descendant-counts-projection/tasks.md` | listo (71/71 tasks marcadas) |
| Progreso de apply | `openspec/changes/descendant-counts-projection/apply-progress.md` | listo |
| Reporte de verificación | `openspec/changes/descendant-counts-projection/verify-report.md` | listo |
| Mirrors en español | `documents-es/openspec/descendant-counts-projection/*.md` | listo |

## Specs permanentes sincronizadas

La spec delta en `openspec/changes/descendant-counts-projection/specs/taxonomic-tree-browse/spec.md` documenta los cambios de comportamiento. No hace falta más sincronización con `openspec/specs/taxonomic-tree-browse/spec.md` — ese archivo lleva el pequeño prune de la línea "Out of Scope" (commit `8a8927a`).

La nueva capacidad `descendant-counts-projection` está documentada en la carpeta del change; la promoción a `openspec/specs/descendant-counts-projection/spec.md` queda diferida hasta el próximo release que la consuma (la projection es interna a `taxon_descendant_counts` hasta que un cambio futuro introduzca un endpoint que exponga los valores cacheados directamente).

## Trayectoria del PR

- **Issue #87** abierto con el cuerpo de la propuesta.
- **PR #86** abierto con justificación de `size:exception`, cuerpo cubre los 5 commits work-unit, 22 archivos cambiados (+3304 / -25).
- **CI**: backend py3.11 ✅, backend py3.12 ✅, frontend ✅, lighthouse ✅.
- **Mergeado** como squash commit `915b1d6` en `develop`.
- **Limpieza**: worktree eliminado, rama local borrada.

## Aprendizajes

Capturados en `/learn-es/2026-08-19-descendant-counts-projection.md` conforme a AGENTS.md §2.

Puntos destacados para el archivo:

1. **Gap de registro de `taxonomy_display_level`** — descubierto por la fase de diseño, cerrado por `register_display_level`. Vale la pena marcarlo en futuras adiciones de SQLite user-function al repo.
2. **Cambio semántico de `_count_descendant_species`** — de "lazy-null sobre el umbral" a "rebuild + cache; lazy-null solo cuando se excede el presupuesto SLO". Documentado en el delta de spec + entrada de learn-es.
3. **`from X import Y` dentro de una función es monkey-patcheable desde `X.Y`** — usado en `test_lazy_null_helper_returns_none_when_rebuild_exceeds_budget` y vale la pena conocerlo para futuros tests de SLO guard.
4. **Los artefactos SDD necesitan un `git add` explícito** — las fases sdd-* escriben archivos con la herramienta `write` pero nunca commitean. El orchestrator debe añadirlos antes de abrir el PR.
5. **Asimetría de umbral entre `_count_descendant_species` (1M) y `_batch_species_counts` (100k)** es pre-existente y se dejó deliberadamente sin tocar — vale la pena abrir una propuesta de seguimiento.

## Próximos pasos

- La capacidad `descendant-counts-projection` está activa en `develop`. La primera request para `Animalia` dispara un rebuild síncrono; las requests siguientes leen desde la cache.
- Un cambio futuro podría promover la spec nueva a `openspec/specs/descendant-counts-projection/spec.md` una vez que la projection la consuma un endpoint nuevo.
- Un cambio futuro podría unificar las constantes de umbral entre los helpers per-row y batched.