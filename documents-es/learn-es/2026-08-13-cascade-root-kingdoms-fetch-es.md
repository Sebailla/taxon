# Cascade root consume /api/kingdoms (PR #30)

# Qué

El effect de mount del componente Cascade ahora rutea el fetch raíz (`state.path.length === 0`) por `fetchKingdoms` (`/api/kingdoms`) en lugar de `fetchPathChildren` (`/api/path-children?path=`). El resto de la cadena sigue usando `fetchPathChildren` por segmento.

# Por qué

El refactor path-aware (PR #29) salió con `fetchPathChildren([])` como fetch raíz. El endpoint `/api/path-children` del backend tiene la constraint `min_length=1` sobre el query param `path` — FastAPI devuelve 422 cuando el path está vacío. El fetch raíz siempre fallaba con 422, el reducer nunca recibía un snapshot, y el dropdown de Kingdom quedaba en el placeholder deshabilitado "Loading children…" para siempre.

Era un bug latente — los tests unitarios mockeaban el fetch, así que el fallo de red nunca se ejercitaba. El smoke test manual contra el dev server vivo (después de que PR #29 aterrizara) lo cazó enseguida: el dropdown de Kingdom renderizaba sin opciones porque el request de red era rechazado.

# Cómo

El fix vive en el primer `useEffect` de `Cascade.tsx`. El fetcher ahora es condicional en `state.path.length`:

```ts
if (state.path.length === 0) {
  void fetchKingdoms({ signal: ctrl.signal }).then(...)
} else {
  void fetchPathChildren(densePath(state.path), { signal: ctrl.signal }).then(...)
}
```

Ambas ramas comparten los mismos callbacks `onSuccess` (cachea el snapshot bajo la key de path) y `onError` (dispatcha `set-current-level-status: error`). Las dos firmas de fetcher son distintas (`fetchKingdoms(init)` vs `fetchPathChildren(segments, init)`), así que el split es la forma más limpia de mantener ambos call sites type-safe sin un discriminator ni un cast.

El snapshot raíz también necesita un `nextRankHint` de `"kingdom"` para que el cascade sepa qué label poner en el siguiente dropdown después de que el usuario elige un kingdom. El endpoint `/api/kingdoms` del backend devuelve un `TaxonResponse[]` plano (sin envelope), así que el effect construye el snapshot a mano:

```ts
onSuccess(result.data, "kingdom");  // nextRankHint = "kingdom"
```

Para los segmentos no-root, el snapshot viene directo del envelope de path-children:

```ts
onSuccess(result.data.children, result.data.next_rank_hint);
```

## Fixtures de test

Las suites de test en `Cascade.pathAware.test.tsx` y `Cascade.ui.test.tsx` se actualizaron para mockear `/api/kingdoms` para el fetch raíz (devolviendo un array `TaxonResponse[]`) y `/api/path-children` para el resto de la cadena. El helper `mockFetchSequence` ahora acepta la forma tuple `[urlMatcher, response]` para que el dispatch raíz pueda matchear `/api/kingdoms` con precisión y el resto de la cadena pueda seguir mockeando por orden de disparo:

```ts
mockFetchSequence([
  // /api/kingdoms — root kingdom list.
  ["/api/kingdoms", mockFetchJson([taxon(2, "Animalia", "kingdom")])],
  // /path-children?path=Animalia
  mockFetchJson({ parent: ..., children: [...], next_rank_hint: "phylum" }),
  // ...
]);
```

La forma bare-response se mantiene para back-compat; la forma tuple es opt-in por call site.

# Dónde

- `frontend/src/components/Cascade.tsx` — 56 líneas cambiadas (split del fetch en dos ramas, callbacks de success/error compartidos).
- `frontend/tests/Cascade.pathAware.test.tsx` — 89 líneas cambiadas (mockFetchSequence creció la forma tuple, más 4 cuerpos de test actualizados para mockear `/api/kingdoms` en el root).
- `frontend/tests/Cascade.ui.test.tsx` — 26 líneas cambiadas (2 cuerpos de test actualizados).
- `.gitignore` — 1 línea agregada (`frontend/pnpm-lock.yaml`). El proyecto usa npm (`package-lock.json`) y pnpm crea el lockfile como side effect de `pnpm install`.

# Verificación

- 55/55 vitest tests passing.
- TypeScript clean (`tsc --noEmit`).
- ESLint clean.
- Smoke test manual contra el dev server vivo: el dropdown de Kingdom ahora lista los 23 kingdoms de CoL (Animalia, Plantae, Fungi, Chromista, Protozoa, más los virus realms Abadenavirae, Sangervirae, Trapavirae, etc.). La selección dispara el siguiente `/path-children` como se esperaba.

# Workflows

- **CI** — 4 jobs green: backend (3.11, 3.12), frontend (node 20), lighthouse.
- **Reviews** — único commit `fix`, sin necesidad de chained PR.

# Aprendizajes

- **El `min_length=1` del endpoint path-aware era un contract assumption que rompió el fetch raíz.** El backend rechazaba el path vacío con 422 porque el resolver no tiene nada donde anclar. El refactor path-aware del frontend consumió silenciosamente el 422 como un "not ok" genérico y dejó el dropdown en estado de loading. El fix es usar el endpoint dedicado `/api/kingdoms` para el root, que no tiene esa constraint.

- **Los tests unitarios con fetch mockeado pueden esconder violaciones de contrato.** Los mocks siempre devuelven lo que el test quiere, así que los 422, 404 y fallos de red nunca se ejercitan. Los smoke tests manuales contra el dev server vivo son la única forma de cazarlos. La regla a futuro: cualquier cambio que toque un fetcher necesita un smoke test manual en el browser, incluso cuando los tests unitarios pasen.

- **Dos firmas de fetcher son un split limpio.** El fetcher del root (`fetchKingdoms(init)`) y el fetcher path-aware (`fetchPathChildren(segments, init)`) tienen firmas diferentes. Tratar de unificarlos con un único condicional requeriría o una discriminated union o un type cast. El split es honesto: dos ramas en el effect, dos `if`s, sin casts. Los callbacks compartidos `onSuccess`/`onError` mantienen la lógica de dispatch DRY.

- **El `nextRankHint` es lo que la UI usa para etiquetar el siguiente dropdown.** El snapshot raíz necesita `nextRankHint = "kingdom"` para que el cascade sepa qué label poner en el siguiente dropdown después de que el usuario elige un kingdom. El `/api/kingdoms` del backend devuelve un `TaxonResponse[]` plano (sin envelope), así que el effect tiene que construir el snapshot a mano. El fetcher no-root sí devuelve el envelope, así que el snapshot viene directo de la response.

- **`pnpm install` crea un `pnpm-lock.yaml` incluso cuando el proyecto usa npm.** El repo usa `package-lock.json` para installs reproducibles. Correr `pnpm install` (que pnpm prefiere por default en algunos agentes) crea un `pnpm-lock.yaml` como side effect. Agregarlo al `.gitignore` mantiene al repo limpio del lockfile equivocado.

# PRs follow-up (no en este commit)

- **PR #27d** — reemplazar el patrón de dropdown por un autocomplete picker para ranks con miles de children (los children a nivel kingdom de CoL son en su mayoría filas species/unranked, así que el dropdown es inmanejable). La implementación actual renderiza un dropdown por ancestro más el picker `next`; un autocomplete colapsaría la UX para chains poco profundos.
- **Cleanup backend** — el endpoint `/api/kingdoms` es ahora el único que el frontend usa en el fetch raíz. La deprecación de los seis endpoints legacy de rank fijo (PR #27c) sigue pendiente; una vez que el frontend deje de pegarle, se pueden remover.
