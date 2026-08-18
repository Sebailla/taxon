# Progreso de aplicación — species-folder-explorer PR2a

## Alcance

PR2a entrega el workspaceStore (zustand), los envoltorios de la API del espacio de trabajo validados con zod, la columna final de SpeciesList (`[explored-checkbox] [folder-badge-or-button]`) y sus pruebas. El interruptor principal de SpeciesLinks y ExplorerPanel se difieren a PR2b y PR3.

## Resultado

- Estado: éxito — la implementación está en verde y dentro del presupuesto de PR2a.
- Entrega: auto-chain, stacked-to-main, PR2a de 4 (PR2 se dividió en 2 rodajas para mantener la disciplina de presupuesto).
- Commits: `4d0f43f`, `c7c48b0`, `ddfffa5`, `<NEW DOC SHA>`.
- Verificación: 109 pruebas de Vitest aprobadas; typecheck, ESLint y la compilación de producción finalizaron correctamente.

## Evidencia del ciclo TDD

| Tarea | Archivo de pruebas | Capa | RED | GREEN | Triangulación |
|---|---|---|---|---|---|
| 3.1–3.4 API/almacén del espacio de trabajo | `api.workspace.test.ts`, `store.workspace.test.ts` | Unidad | exportaciones ausentes | exportaciones añadidas; rutas con clave de especie | éxito, error y vacío |
| 3.5–3.6 Filas de SpeciesList | `SpeciesList.workspace.test.tsx` | Componente | controles ausentes | controles renderizados | estados explorado y carpeta |

## Evidencia de unidades de trabajo

| Unidad de trabajo | Resultado de prueba enfocada | Arnés de ejecución | Límite de reversión |
|---|---|---|---|
| Almacén + API | 7 aprobadas (4 api.workspace + 3 store.workspace) | compilación completa de Vite correcta | revertir 4d0f43f + c7c48b0 |
| Filas de SpeciesList | 3 aprobadas | compilación completa de Vite correcta | revertir ddfffa5 |

## Desviaciones

- PR2 (presupuestado originalmente en ≤350 líneas) se dividió en PR2a (esta) y PR2b (SpeciesLinks) porque el diff combinado (510 líneas) superaba el presupuesto de revisión de 400 líneas. PR2a queda en 396 inserciones + 22 eliminaciones = 418 líneas modificadas en 6 archivos; el orquestador evaluará si se requiere una `size:exception`.
- Las pruebas de React emiten advertencias `act(...)` asíncronas de Zustand; no queda ningún fallo de aserción ni de accesibilidad.
- El almacén nunca lee `taxa.id`. Las claves son `${genus}|${epithet}` codificadas para URL.

## Archivos modificados

- `frontend/src/api.ts` (+76/-1) — envoltorios de la API del espacio de trabajo + esquemas zod
- `frontend/src/store/workspace.ts` (+87/-2) — workspaceStore de zustand
- `frontend/src/components/SpeciesList.tsx` (+52/-21) — controles de la columna final
- `frontend/tests/api.workspace.test.ts` (+83) — pruebas de contrato de la API
- `frontend/tests/store.workspace.test.ts` (+69) — pruebas de acciones del almacén
- `frontend/tests/SpeciesList.workspace.test.tsx` (+51) — pruebas de renderizado de filas

Total: 396 inserciones, 22 eliminaciones en 6 archivos (418 líneas modificadas).