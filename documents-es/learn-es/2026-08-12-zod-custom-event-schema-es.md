# Tightening del contrato del CustomEvent taxon:select con Zod (PR #24)

# Qué

Reemplazó el contrato implícito del CustomEvent `taxon:select`
entre el Cascade (productor) y el App (consumidor) por un schema
Zod que ambos extremos validan en runtime. Cierra el seguimiento
arquitectónico del bug del segmento genus en PR #22.

- Nuevo módulo `frontend/src/events/taxonSelect.ts` que exporta
  los schemas, el detail tipado derivado vía `z.infer`, y dos
  helpers (`dispatchTaxonSelect`, `parseTaxonSelectEvent`).
- `SpeciesList` y `App` ahora pasan por los helpers en lugar de
  despachar/cast-ear el evento manualmente.
- 11 tests RED-first fijan el schema y los helpers.
- Zod 4 añadido como dependencia runtime (bundle +18 KB gzipped).

# Cómo

### Schema

```ts
export const TaxonResponseSchema = z.object({
  id: z.number(),
  name: z.string(),
  // ... mirrors the TS interface exactly
});

export const TaxonSelectDetailSchema = z.object({
  row: TaxonResponseSchema,
  breadcrumb: z.array(z.string()),
  parentSegments: z.array(z.string()),
});

export type TaxonSelectDetail = z.infer<typeof TaxonSelectDetailSchema>;
```

Schemas escritos a mano — sin codegen. La superficie es lo
suficientemente pequeña (1 tipo de evento, 9 claves) que el costo
de mantener el schema en sync con `api.ts` es menor que el costo
de construir un pipeline de codegen.

### Helpers

```ts
export function dispatchTaxonSelect(detail: unknown): void {
  const result = TaxonSelectDetailSchema.safeParse(detail);
  if (!result.success) {
    console.warn("[taxon] dispatchTaxonSelect: detail failed schema validation, skipping dispatch", result.error.flatten());
    return;
  }
  window.dispatchEvent(new CustomEvent(TAXON_SELECT_EVENT, { detail: result.data }));
}

export function parseTaxonSelectEvent(event: Event): TaxonSelectDetail | null {
  const result = TaxonSelectDetailSchema.safeParse((event as CustomEvent).detail);
  if (!result.success) {
    console.warn("[taxon] parseTaxonSelectEvent: detail failed schema validation, ignoring", result.error.flatten());
    return null;
  }
  return result.data;
}
```

Ambos fallan ruidoso (warning en consola) y seguro (no dispatch /
no crash). El schema es el contrato de forma; las invariantes
semánticas (p. ej. "parentSegments debe terminar en el genus")
siguen perteneciendo al productor y sus tests.

### Cableado

`SpeciesList.tsx`:

```diff
- window.dispatchEvent(new CustomEvent("taxon:select", {
-   detail: { row, breadcrumb: props.breadcrumb, parentSegments: props.parentSegments },
- }));
+ dispatchTaxonSelect({
+   row,
+   breadcrumb: props.breadcrumb,
+   parentSegments: props.parentSegments,
+ });
```

`App.tsx`:

```diff
- const detail = (e as CustomEvent<{
-   row: TaxonResponse;
-   breadcrumb: string[];
-   parentSegments: string[];
- }>).detail;
+ const detail = parseTaxonSelectEvent(e);
+ if (detail === null) return;
```

# Dónde

- `frontend/src/events/taxonSelect.ts` — nuevo (97 líneas).
- `frontend/src/components/SpeciesList.tsx` — usa
  `dispatchTaxonSelect`.
- `frontend/src/App.tsx` — usa `parseTaxonSelectEvent` y la
  constante `TAXON_SELECT_EVENT`.
- `frontend/tests/taxonSelect.test.ts` — nuevo (185 líneas, 11
  tests).
- `frontend/package.json` / `package-lock.json` — Zod 4 añadido.

# Por qué

El bug del segmento genus en PR #22 fue un síntoma directo del
contrato implícito en el borde del CustomEvent. El productor y
el consumidor acordaban la forma por convención; el cast de
tipo en `App.tsx` saltaba cualquier validación en runtime; un
productor futuro podía derivar sin que nadie lo notara hasta que
un usuario hacía click en una fila de species y volvía a ver
"Could not load links.".

Tres modos de fallo que el patrón de cast implícito oculta:

1. **Drift del productor** — un componente futuro despacha el
   evento con la forma incorrecta.
2. **Evolución del schema** — un refactor cambia la interfaz TS
   en `api.ts` sin actualizar el listener. El detail cruza un
   borde `window.dispatchEvent`, por lo que el listener no puede
   saber estáticamente qué envió el productor.
3. **Productores de terceros** — una extensión del browser o
   herramienta de test futura despacha el evento manualmente.

El `safeParse` de Zod en ambos extremos hace los tres visibles
en runtime con un warning en consola, antes de que lleguen al
usuario.

# Cómo funciona

Cuando el usuario hace click en una fila de species:

1. `SpeciesList` llama a `dispatchTaxonSelect({ row, breadcrumb, parentSegments })`.
2. El helper valida el detail contra el schema. Si falla: log de
   warning, se saltea el dispatch (el productor es buggy, no
   contaminar el bus global de eventos).
3. Si pasa: despacha `taxon:select` con el detail validado.
4. El listener de `App.tsx` recibe el evento y llama a
   `parseTaxonSelectEvent`. Si falla: log de warning, retorna
   `null`, el listener hace early-return sin cambiar estado.
5. Si pasa: el listener lee el detail tipado y actualiza
   `resolved` + `parentSegments`.

La validación del lado del productor es un bonus defensivo:
hoy ambos extremos son de este codebase, pero la validación hace
más seguros a futuros productores cross-package o cross-team.

# Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). Todos verdes. El job lighthouse vuelve a correr la
  suite de accesibilidad sobre el bundle de producción; el nuevo
  schema está incluido en el bundle.
- **Revisiones** — 4 `work-unit-commits`:
  1. `chore(frontend): add zod 4 runtime dependency`
  2. `feat(frontend): add Zod schema for taxon:select CustomEvent`
  3. `test(frontend): add RED-first coverage for taxonSelect schema and helpers`
  4. `refactor(frontend): wire App and SpeciesList through the Zod helpers`
  El revisor puede leer el schema aislado, luego los tests, y
  finalmente el diff de cableado (que es el más chico).
- **Tamaño de bundle** — el JS de producción pasó de 154 KB →
  223 KB raw, 49 KB → 67 KB gzipped (+18 KB gzipped). Aceptable
  por la garantía contractual; puede revisarse si el presupuesto
  aprieta cambiando a Valibot (cambio de un import).

# Aprendizajes

- **Los contratos implícitos en bordes `window.dispatchEvent` son
  el peor tipo de acoplamiento** — ninguno de los dos extremos
  sabe estáticamente qué envía el otro, así que TypeScript solo
  puede verificar lo que es visible en el archivo. El detail del
  CustomEvent es la capa más barata, más explícita y más
  reemplazable de validación; usarla.
- **Los schemas Zod escritos a mano le ganan al codegen para
  superficies pequeñas.** Consideré `ts-to-zod` pero la interfaz
  `TaxonResponse` tiene 9 campos y hay exactamente un evento. El
  costo de mantener el schema en sync manualmente (un PR si la
  interfaz cambia) es menor que el costo de construir el pipeline
  de codegen.
- **Fallar ruidoso Y seguro.** Los helpers logean un
  `console.warn` en validación fallida y se saltean la operación.
  Ruidoso porque el desarrollador necesita ver el drift en la
  consola; seguro porque el usuario nunca debe ver un crash
  causado por un mismatch de contrato interno.
- **Los trade-offs de tamaño de bundle merecen aparecer en el
  cuerpo del PR.** El +18 KB gzipped es el costo del contrato; la
  alternativa (Valibot, hand-rolled) está a un import de
  distancia. Poner la alternativa en el cuerpo del PR hace que el
  trade-off sea auditable más tarde si el presupuesto aprieta.
