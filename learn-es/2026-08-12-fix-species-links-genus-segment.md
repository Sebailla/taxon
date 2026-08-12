# Fix: species links fetch was missing the genus segment

## What

Bug fix shipped as PR #22: clicking a species row in the cascade
UI showed "Could not load links." The Cascade was slicing off the
genus segment from `parentSegments` before dispatching the
`taxon:select` CustomEvent, so the App built the links URL without
the genus and the backend returned 404.

One-character fix (dropping `.slice(0, -1)`) plus a RED-first
regression test that pins the contract end-to-end.

## How

### Bug

`frontend/src/components/Cascade.tsx:301` was passing the parent
segments to `SpeciesList` with the genus sliced off:

```tsx
<SpeciesList
  ...
  parentSegments={parentSegments(state.selected).slice(0, -1)}
  ...
/>
```

The intent was probably to keep `SpeciesList` ignorant of its own
genus (the species list endpoint is `{...path}/species` where the
genus is the last segment). But `SpeciesList` only forwards the
array in the `taxon:select` CustomEvent; the App uses the array
to build the `/api/{kingdom}/{phylum}/{class}/{order}/{family}/{
genus}/{epithet}/links` URL — which **requires the genus**.

The hand-off was invisible to the type system: `parentSegments` is
just `string[]`, and both ends of the contract accepted whatever
they got. The 404 surfaced as "Could not load links." in the UI
without any indication that the path was malformed.

### Fix

Drop the `.slice(0, -1)`. SpeciesList does not consume the genus;
it only forwards the array.

```tsx
parentSegments={parentSegments(state.selected)}
```

### Regression test

`frontend/tests/Cascade.test.tsx` — new `describe` block that:

1. Mocks the full Kingdom → Genus fetch chain.
2. Mounts the Cascade.
3. Walks the user through every dropdown until the species list
   appears.
4. Subscribes to the `taxon:select` CustomEvent via
   `window.addEventListener`.
5. Clicks the species row.
6. Asserts the dispatched `parentSegments` contains all 6 ranks,
   including the genus.

Failed RED before the fix (5-element array vs expected 6), passes
GREEN after.

## Where

- `frontend/src/components/Cascade.tsx` — line 301, the slice.
- `frontend/tests/Cascade.test.tsx` — new describe block at the end
  of the file.

## Why

Two reasons this slipped past the existing tests:

1. The contract was never pinned. No test asserted that
   `taxon:select.detail.parentSegments` is a particular shape.
   The contract was implicit in the App component's
   `fetchLinks(parentSegments, epithet)` call.
2. End-to-end behaviour was only verifiable in a running browser.
   Vitest + jsdom cannot reproduce the symptom because the
   backend was never invoked from a test.

The new test fixes (1) by asserting the contract at the event
boundary. It cannot fully fix (2) because Vitest does not talk
to FastAPI, but the contract assertion is enough to catch this
class of bug.

## How it works

When the user clicks a species row, `SpeciesList` dispatches:

```js
window.dispatchEvent(new CustomEvent("taxon:select", {
  detail: {
    row: <the species row>,
    breadcrumb: <biota-stripped breadcrumb>,
    parentSegments: <full Kingdom → Genus path>,
  },
}));
```

App's `taxon:select` listener stores `parentSegments`. The
`fetchLinks` effect runs `fetchLinks(parentSegments, epithet)`,
which builds `/${parentSegments}/${epithet}/links`. The backend
expects this 7-segment path; with the fix it gets it; before the
fix it got a 6-segment path that returned 404.

## Workflows

- **CI**: 4 jobs (backend 3.11, backend 3.12, frontend, lighthouse).
  All green. No CI workflow changes needed — the fix is in app
  code only.
- **Reviews**: 2 commits (`work-unit-commits`):
  1. `ca0138e test(frontend): add RED regression test for taxon:select path segments`
  2. `daeec8d fix(frontend): include genus in parentSegments dispatched on species click`
  Reviewer can read the regression test alone to understand the
  contract, then see the one-line fix.
- **Manual reproduction**: open
  `http://localhost:5173/`, navigate Animalia → ... → Genus,
  click any species. Before the fix: red "Could not load links."
  panel. After the fix: 4×3 grid of search-source buttons
  (WoRMS, GBIF, OBIS, IUCN, etc.).

## Lessons learned

- **Implicit contracts at event boundaries are the worst kind of
  coupling.** `taxon:select` had no schema test; the producer
  and consumer agreed by convention. The fix is small but the
  symptom ("Could not load links.") was a UX-level failure that
  could have hidden other shape mismatches in the same array.
  Future events of this shape should carry a runtime type
  (Zod, Valibot, plain `as const`) and be asserted in tests.
- **End-to-end tests belong in the contract surface, not the
  UI.** The Cascade tested its own state machine and the
  SpeciesList tested its own rendering, but no test pinned the
  cross-component contract. Adding the listener-based test cost
  ~160 lines but locked the bug out forever.
- **404s in production deserve a request-shape audit.** When the
  backend returns 404 to a URL the client just built, the bug is
  almost always in the client, not the server. A useful debug
  step: paste the failing URL into a shell and curl it. If 404,
  trace the path-building logic. If 200, the bug is in the
  status-code branch (response parsing, discriminated union).
