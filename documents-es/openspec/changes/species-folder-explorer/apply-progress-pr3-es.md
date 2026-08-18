# Progreso de aplicación — species-folder-explorer PR3

## Alcance

El PR3 entrega el componente `ExplorerPanel` (iframe + sandbox + tarjeta de respaldo + tarjeta peek-card móvil) conectado en la columna derecha de `App.tsx`, y la extensión del clic en la celda de especie de `SpeciesLinks` que llena `workspaceStore.activeLink`. Cierra la subcaracterística D del issue #68 y el conjunto de pines de prueba de la subcaracterística D. PR1 (backend) y PR2a + PR2b (store frontend + UI de filas) ya están mergeados.

## Resultado

- Estado: éxito — implementación en verde, bien por debajo del presupuesto del PR.
- Entrega: auto-chain, stacked-to-main, PR3 de 4 (última rebanada de #68).
- Commits: `a3964d8`, `05cb5f1`, `d31a7cc`.
- Verificación: 135 pruebas de Vitest pasaron; typecheck, ESLint y build de producción exitosos.
- Rama: `feat/species-folder-explorer-pr3` (creada desde `develop`).

## Evidencia del ciclo TDD

| Tarea | Archivo de prueba | Capa | RED | GREEN | Triangulación |
|---|---|---|---|---|---|
| 4.1 sandbox iframe + estado vacío + fallback | `ExplorerPanel.test.tsx` | Componente | componente ausente | sandbox + src + aria-label + fallback + axe | entre-especies + primer tab stop |
| 4.2 componente `ExplorerPanel.tsx` | (cubierto arriba) | Componente | mismo | mismo | mismo |
| 4.3 cableado active-link + aislamiento breadcrumb | `ExplorerPanel.activate.test.tsx` | Integración | mutación de store ausente | cableado + dispatch de App | celda-especie vs celda-breadcrumb |
| 4.4 montaje en App.tsx + sticky | (cubierto por prueba de integración) | Integración | mismo | mismo | mismo |
| 4.5 colapso móvil | `ExplorerPanel.mobile.test.tsx` | Componente | data-testid ausente | peek-card + iframe conviven | texto + href + rel |
| 4.6 UX de peek-card móvil | (cubierto arriba) | Componente | mismo | mismo | mismo |
| 4.7 regresión axe-core | `a11y.explorer.test.tsx` | Componente | regresiones | 0 violaciones en vacío + iframe + fallback | n/a |
| 4.8 apéndice del doc de diseño | no ejecutado (cuenta por debajo del presupuesto) | n/a | n/a | n/a | n/a |
| 4.9 entrada learn-es | post-merge según AGENTS.md §2 | n/a | n/a | n/a | n/a |

## Evidencia de unidades de trabajo

| Unidad de trabajo | Resultado de prueba focal | Andamiaje de ejecución | Frontera de rollback |
|---|---|---|---|
| ExplorerPanel + sandbox + fallback + a11y + decoder | 19 pasaron (13 ExplorerPanel + 3 a11y + 3 decoder) | `npm run build` (tsc -b + vite) | revertir `a3964d8`; quita el panel + 3 pruebas, deja store + App.tsx intactos |
| SpeciesLinks → setActiveLink | 2 pasaron (activate) | suite completa: 135 pasaron | revertir `05cb5f1`; quita el dispatch del clic + la prueba activate |
| Montaje en App.tsx + peek-card móvil | 2 pasaron (mobile) | suite completa: 135 pasaron + `npm run build` | revertir `d31a7cc`; la columna derecha de App restaura breadcrumb + links históricos |

## Desviaciones

- La tarea 4.8 (apéndice del doc de diseño) no se ejecutó porque el doc de diseño es el `openspec/changes/species-folder-explorer/design.md` de 116 líneas (el prompt mencionó 837 líneas pero el archivo real tiene 116). La nota de implementación de la Fase 4 se captura en este documento apply-progress-pr3 — el diseño prescriptivo ya está en `design.md` y la evidencia de implementación está aquí.
- TDD Estricto descubrió que jsdom + React 18.3 no dispara el `onError` sintético de React en `<iframe>` mediante `fireEvent.error`. La implementación cambió a un `addEventListener('error', handler)` crudo en la ref del iframe, que coincide con el comportamiento real del navegador y es el patrón documentado para eventos de error en iframes.
- El recorrido de iframes de axe-core falla en jsdom (el iframe no tiene contentDocument). La prueba a11y para el estado de renderizado del iframe usa `axeCore.run(container, { iframes: false })` en vez del helper estándar `axe()`. Los estados vacío + fallback siguen usando el helper estándar porque no tienen contenido de iframe en el que recursar.
- `decodeSpeciesKey` se exporta desde `frontend/src/store/speciesKey.ts` (no desde `ExplorerPanel.tsx`) para cumplir la regla de lint `react-refresh/only-export-components`.
- La peek-card móvil coexiste con el iframe (el spec dice "el iframe aún se renderiza pero la grilla de despacho se colapsa"). La peek-card es la afinidad para el viewport pequeño, no un reemplazo.

## Archivos cambiados

| Archivo | Acción | LOC | Notas |
|---|---|---|---|
| `frontend/src/components/ExplorerPanel.tsx` | Creado | 144 | iframe + sandbox + fallback + peek móvil + decodeSpeciesKey |
| `frontend/src/store/speciesKey.ts` | Creado | 19 | helper de round-trip para la clave URL-encoded del store |
| `frontend/src/App.tsx` | Modificado | +9 | monta `<ExplorerPanel>` en la columna derecha, sticky top-0 |
| `frontend/src/components/SpeciesLinks.tsx` | Modificado | +13 | el clic en la celda de especie llama a `setActiveLink`; las celdas de breadcrumb son no-ops |
| `frontend/tests/ExplorerPanel.test.tsx` | Creado | 224 | 13 pruebas pineando sandbox + estado vacío + aria-label + fallback + visibilidad + axe |
| `frontend/tests/ExplorerPanel.activate.test.tsx` | Creado | 181 | 2 pruebas pineando el cableado active-link celda-especie vs celda-breadcrumb |
| `frontend/tests/ExplorerPanel.mobile.test.tsx` | Creado | 71 | 2 pruebas pineando la peek-card móvil + coexistencia del iframe |
| `frontend/tests/a11y.explorer.test.tsx` | Creado | 55 | 3 pruebas de regresión axe-core |
| `frontend/tests/store.speciesKey.test.ts` | Creado | 33 | 3 pruebas de round-trip para el helper de decode |

Total CODE: 185 inserciones en 4 archivos fuente.
Total TESTS: 23 pruebas en 4 archivos de prueba.
Total PR DIFF: 749 inserciones en 9 archivos (bien por debajo del presupuesto CODE de 400 líneas).

## Suite de pruebas

- `npm run test` → 135 pruebas pasaron (112 base + 23 nuevas).
- `npm run typecheck` → limpio.
- `npm run lint` → limpio (la advertencia `react-refresh/only-export-components` se resolvió moviendo `decodeSpeciesKey` a un archivo separado).
- `npm run build` → `tsc -b && vite build` → 123 módulos transformados, bundle JS de 238 KB.

## Verificación

```
$ cd frontend && npm run typecheck && npm run lint && npm run test && npm run build

> taxon-frontend@0.1.0 typecheck
> tsc --noEmit

> taxon-frontend@0.1.0 lint
> eslint .

> taxon-frontend@0.1.0 test
 Test Files  22 passed (22)
      Tests  135 passed (135)

> taxon-frontend@0.1.0 build
> tsc -b && vite build
✓ 123 modules transformed.
dist/assets/index-CFn8ytY-.js   238.09 kB │ gzip: 72.05 kB
✓ built in 708ms
```

## Fuera de alcance (aplazado deliberadamente)

- Auto-marcar una fuente como visitada cuando el usuario hace clic dentro del iframe (rebanada separada según spec §Out of Scope).
- Estado persistente del iframe entre recargas del SPA (con ámbito de sesión según spec).
- Preajustes de tamaño de iframe por fuente (aplazado).
- Entrada `/learn-es/2026-08-16-species-folder-explorer.md` post-merge (según AGENTS.md §2; el orquestador la creará después de que PR3 se mergee en verde).

## Relacionado

- PR2a (mergeado): `feat(frontend): species workspace store + api wrappers + SpeciesList column` (#71)
- PR2b (mergeado): `feat(frontend): SpeciesLinks visited source switches` (#72)
- PR1 (mergeado): `feat(api): species workspace backend` (#70)
- Issue #68: Species workspace — creación de carpetas, flag explored, explorer embebido, switches por enlace
- Después de que PR3 se mergee a `develop` con CI en verde, correr `sdd-archive` para sincronizar las 4 nuevas specs y escribir el reporte de archivo.
