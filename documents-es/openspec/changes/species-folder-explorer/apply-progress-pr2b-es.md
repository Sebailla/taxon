# Progreso de Aplicación — species-folder-explorer PR2b

## Alcance

PR2b entrega el switch inicial de `SpeciesLinks` que consume `workspaceStore.visitedLinks` y aplica el estilo `border-muted text-slate line-through` a las fuentes visitadas. `App.tsx` se actualiza para pasar la identidad de especie a `SpeciesLinks`. PR2a (store + api + columna final de SpeciesList) ya está mergeado vía PR #71. El ExplorerPanel queda diferido para PR3.

## Resultado

- Estado: éxito — implementación verde, muy por debajo del presupuesto del PR.
- Entrega: auto-chain, apilado-a-main, PR2b de 4 (PR2 se dividió en 2 slices por disciplina de presupuesto).
- Commits: `e1d5b2b` (cherry-pick como `4297214`).
- Verificación: 112 tests de Vitest pasaron; typecheck, ESLint y build de producción exitosos.

## Evidencia del Ciclo TDD

| Tarea | Archivo de test | Capa | RED | GREEN | Triangulación |
|---|---|---|---|---|---|
| Switch de visitado en SpeciesLinks | `SpeciesLinks.visited.test.tsx` | Componente | switch ausente y axe expuso rol listitem inválido | switch renderizado con estilo de visitado | marcar/desmarcar y aislamiento entre especies |

## Evidencia de Unidad de Trabajo

| Unidad de trabajo | Resultado del test focal | Harness de runtime | Límite de rollback |
|---|---|---|---|
| Switches en SpeciesLinks | 3 pasaron | build completo de Vite OK | revertir `4297214`; restaura las celdas de enlaces históricas |

## Desviaciones

- PR2 (planificado originalmente ≤350 LOC) terminó en 510 LOC de extremo a extremo; se dividió en PR2a (418 LOC código / 504 LOC con docs, mergeado vía PR #71) + PR2b (76 LOC código, este PR).
- `App.tsx` pasa la identidad de especie a `SpeciesLinks` pero NO monta `ExplorerPanel` — eso sigue siendo responsabilidad de PR3.
- El store usa claves URL-encoded `${genus}|${epithet}` y nunca lee `taxa.id` (disciplina de re-bind anclada por PR1).
- Los tests de React emiten warnings asíncronos de Zustand `act(...)`; no queda ningún fallo de aserción ni de accesibilidad.

## Archivos cambiados

- `frontend/src/components/SpeciesLinks.tsx` (+42/-18) — switch inicial de visitado con estilo `border-muted text-slate line-through` cuando está visitado
- `frontend/src/App.tsx` (+1/-1) — pasa la identidad de especie a `SpeciesLinks`
- `frontend/tests/SpeciesLinks.visited.test.tsx` (+50) — switch de visitado + aserciones de axe-core

Total: 76 inserciones, 18 eliminaciones en 3 archivos.

## Relacionado

- PR #71 (PR2a, mergeado): `feat(frontend): species workspace store + api wrappers + SpeciesList column`
- PR #70 (PR1, mergeado): `feat(api): species workspace backend`
- Issue #68: Species workspace — creación de carpeta, flag explorado, explorador embebido, switches por enlace
- PR3 (pendiente): ExplorerPanel con iframe + sandbox + tarjeta de fallback + doc de diseño + entrada learn-es
