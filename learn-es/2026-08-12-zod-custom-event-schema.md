# Tighten the taxon:select CustomEvent contract with Zod (PR #24)

## What

Replaced the implicit `taxon:select` CustomEvent contract between
the Cascade (producer) and the App (consumer) with a Zod schema
that both ends validate at runtime. Closes the architectural
follow-up to the genus-segment bug in PR #22.

- New module `frontend/src/events/taxonSelect.ts` exports the
  schemas, the typed detail derived via `z.infer`, and two helpers
  (`dispatchTaxonSelect`, `parseTaxonSelectEvent`).
- `SpeciesList` and `App` now go through the helpers instead of
  dispatching/casting the event manually.
- 11 RED-first tests pin the schema and the helpers.
- Zod 4 added as a runtime dep (bundle +18 KB gzipped).

## How

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

Schemas are written by hand — no codegen. The surface is small
enough (1 event type, 9 keys) that the cost of keeping the schema
in sync with `api.ts` is lower than the cost of building a
codegen pipeline.

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

Both fail loud (console warning) and fail safe (no dispatch / no
crash). The schema is the shape contract; semantic invariants
(e.g. "parentSegments must end in the genus") still belong in the
producer and its tests.

### Wiring

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

## Where

- `frontend/src/events/taxonSelect.ts` — new (97 lines).
- `frontend/src/components/SpeciesList.tsx` — uses `dispatchTaxonSelect`.
- `frontend/src/App.tsx` — uses `parseTaxonSelectEvent` and the `TAXON_SELECT_EVENT` constant.
- `frontend/tests/taxonSelect.test.ts` — new (185 lines, 11 tests).
- `frontend/package.json` / `package-lock.json` — Zod 4 added.

## Why

The genus-segment bug in PR #22 was a direct symptom of the
implicit contract at the CustomEvent boundary. The producer and
the consumer agreed on the shape by convention; the type cast in
`App.tsx` skipped any runtime validation; a future producer could
drift without anyone noticing until a user clicked a species row
and got "Could not load links." again.

Three failure modes the implicit cast pattern hides:

1. **Producer drift** — a future component dispatches the event
   with the wrong shape.
2. **Schema evolution** — a refactor changes the TS interface in
   `api.ts` without updating the listener. The detail crosses a
   `window.dispatchEvent` boundary, so the listener cannot
   statically know what the producer sent.
3. **Third-party producers** — a future browser extension or test
   harness dispatches the event manually.

Zod's `safeParse` at both ends makes all three visible at runtime
with a console warning, before they reach the user.

## How it works

When the user clicks a species row:

1. `SpeciesList` calls `dispatchTaxonSelect({ row, breadcrumb, parentSegments })`.
2. The helper validates the detail against the schema. On failure:
   logs a warning, skips the dispatch (producer is buggy, do not
   pollute the global event bus).
3. On success: dispatches `taxon:select` with the validated detail.
4. `App.tsx`'s listener receives the event and calls
   `parseTaxonSelectEvent`. On failure: logs a warning, returns
   `null`, the listener early-returns without changing state.
5. On success: the listener reads the typed detail and updates
   `resolved` + `parentSegments`.

The producer-side validation is a defensive bonus: today both
ends are owned by this codebase, but the validation makes future
cross-package or cross-team producers safer.

## Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). All green. The lighthouse job re-runs the
  accessibility suite on the production bundle; the new schema is
  included in the bundle.
- **Reviews** — 4 `work-unit-commits`:
  1. `chore(frontend): add zod 4 runtime dependency`
  2. `feat(frontend): add Zod schema for taxon:select CustomEvent`
  3. `test(frontend): add RED-first coverage for taxonSelect schema and helpers`
  4. `refactor(frontend): wire App and SpeciesList through the Zod helpers`
  Reviewer can read the schema in isolation, then the tests, then
  the wiring diff (which is the smallest).
- **Bundle size** — production JS went from 154 KB → 223 KB raw,
  49 KB → 67 KB gzipped (+18 KB gzipped). Acceptable for the
  contract guarantee; can be revisited if the budget tightens by
  switching to Valibot (one import change).

## Lessons learned

- **Implicit contracts at `window.dispatchEvent` boundaries are
  the worst kind of coupling** — neither end statically knows
  what the other sends, so TypeScript can only check what is
  visible in the file. The CustomEvent detail type is the
  cheapest, most-explicit, most-replaceable layer of validation;
  use it.
- **Hand-written Zod schemas beat codegen for small surfaces.** I
  considered `ts-to-zod` but the `TaxonResponse` interface has 9
  fields and there is exactly one event. The cost of keeping the
  schema in sync manually (one PR if the interface changes) is
  lower than the cost of building the codegen pipeline.
- **Fail loud AND fail safe.** The helpers log a `console.warn`
  on validation failure and skip the operation. Loud because the
  developer needs to see the drift in the console; safe because
  the user must never see a crash caused by an internal contract
  mismatch.
- **Bundle size trade-offs are worth surfacing in the PR body.**
  The +18 KB gzipped is the cost of the contract; the alternative
  (Valibot, hand-rolled) is one-import-away. Putting the
  alternative in the PR body makes the trade-off auditable later
  if the budget tightens.
