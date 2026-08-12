# Fix: el fetch de links de species omitía el segmento del genus

# Qué

Bug fix embarcado como PR #22: al hacer click en una fila de
species en la UI del cascade aparecía "Could not load links.". El
Cascade estaba quitando con `.slice` el segmento del genus del
array `parentSegments` antes de despachar el CustomEvent
`taxon:select`, por lo que el App construía la URL de links sin
el genus y el backend devolvía 404.

Fix de un carácter (quitar `.slice(0, -1)`) más un test RED-first
de regresión que fija el contrato de extremo a extremo.

# Cómo

### Bug

`frontend/src/components/Cascade.tsx:301` pasaba los segmentos
padre a `SpeciesList` con el genus recortado:

```tsx
<SpeciesList
  ...
  parentSegments={parentSegments(state.selected).slice(0, -1)}
  ...
/>
```

La intención probablemente era mantener `SpeciesList` ignorante
de su propio genus (el endpoint de species es `{...path}/species`
donde el genus es el último segmento). Pero `SpeciesList` solo
reenvía el array en el CustomEvent `taxon:select`; el App usa el
array para construir la URL `/api/{kingdom}/{phylum}/{class}/{
order}/{family}/{genus}/{epithet}/links` — que **requiere el
genus**.

El hand-off era invisible para el sistema de tipos:
`parentSegments` es solo `string[]`, y ambos extremos del contrato
aceptaban lo que recibían. El 404 se manifestaba como "Could not
load links." en la UI sin ninguna indicación de que el path
estaba mal formado.

### Fix

Quitar `.slice(0, -1)`. SpeciesList no consume el genus; solo
reenvía el array.

```tsx
parentSegments={parentSegments(state.selected)}
```

### Test de regresión

`frontend/tests/Cascade.test.tsx` — nuevo bloque `describe` que:

1. Mockea la cadena completa de fetch Kingdom → Genus.
2. Monta el Cascade.
3. Lleva al usuario a través de cada dropdown hasta que aparece
   la lista de species.
4. Se suscribe al CustomEvent `taxon:select` vía
   `window.addEventListener`.
5. Hace click en la fila de species.
6. Verifica que el `parentSegments` despachado contiene los 6
   ranks, incluido el genus.

Falló RED antes del fix (array de 5 elementos vs 6 esperados),
pasa GREEN después.

# Dónde

- `frontend/src/components/Cascade.tsx` — línea 301, el slice.
- `frontend/tests/Cascade.test.tsx` — nuevo bloque `describe`
  al final del archivo.

# Por qué

Dos razones por las que esto se escapó de los tests existentes:

1. El contrato nunca estuvo fijado. Ningún test verificaba que
   `taxon:select.detail.parentSegments` tiene una forma
   particular. El contrato era implícito en la llamada
   `fetchLinks(parentSegments, epithet)` del componente App.
2. El comportamiento end-to-end solo era verificable en un
   browser corriendo. Vitest + jsdom no pueden reproducir el
   síntoma porque el backend nunca se invoca desde un test.

El nuevo test corrige (1) verificando el contrato en el borde
del evento. No puede corregir completamente (2) porque Vitest no
habla con FastAPI, pero la verificación del contrato basta para
detectar esta clase de bug.

# Cómo funciona

Cuando el usuario hace click en una fila de species, `SpeciesList`
despacha:

```js
window.dispatchEvent(new CustomEvent("taxon:select", {
  detail: {
    row: <la fila de species>,
    breadcrumb: <breadcrumb sin biota>,
    parentSegments: <path completo Kingdom → Genus>,
  },
}));
```

El listener de `taxon:select` en App almacena `parentSegments`. El
effect de `fetchLinks` ejecuta `fetchLinks(parentSegments, epithet)`,
que construye `/${parentSegments}/${epithet}/links`. El backend
espera este path de 7 segmentos; con el fix lo recibe; antes del
fix recibía un path de 6 segmentos que devolvía 404.

# Workflows

- **CI**: 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). Todos verdes. No se necesitan cambios en el
  workflow de CI — el fix es solo en código de aplicación.
- **Revisiones**: 2 commits (`work-unit-commits`):
  1. `ca0138e test(frontend): add RED regression test for taxon:select path segments`
  2. `daeec8e fix(frontend): include genus in parentSegments dispatched on species click`
  El revisor puede leer el test de regresión por sí solo para
  entender el contrato, y luego ver el fix de una línea.
- **Reproducción manual**: abrir
  `http://localhost:5173/`, navegar Animalia → ... → Genus,
  hacer click en cualquier species. Antes del fix: panel rojo
  "Could not load links.". Después del fix: grid 4×3 de botones
  de fuentes de búsqueda (WoRMS, GBIF, OBIS, IUCN, etc.).

# Aprendizajes

- **Los contratos implícitos en bordes de eventos son el peor
  tipo de acoplamiento.** `taxon:select` no tenía test de
  schema; el productor y el consumidor acordaban por convención.
  El fix es pequeño pero el síntoma ("Could not load links.")
  era un fallo a nivel de UX que podría haber ocultado otros
  mismatches de forma en el mismo array. Futuros eventos de esta
  forma deberían llevar un tipo runtime (Zod, Valibot, plano
  `as const`) y verificarse en tests.
- **Los tests end-to-end pertenecen a la superficie del
  contrato, no a la UI.** El Cascade testeaba su propia máquina
  de estados y SpeciesList testeaba su propio renderizado, pero
  ningún test fijaba el contrato entre componentes. Añadir el
  test basado en listener costó ~160 líneas pero bloqueó el bug
  para siempre.
- **Los 404s en producción merecen una auditoría de la forma
  del request.** Cuando el backend devuelve 404 a una URL que
  el cliente acaba de construir, el bug casi siempre está en
  el cliente, no en el servidor. Un paso útil de debug: pegar
  la URL fallida en una shell y hacerle curl. Si 404, rastrear
  la lógica de construcción del path. Si 200, el bug está en
  la rama del código de estado (parseo de respuesta, unión
  discriminada).
