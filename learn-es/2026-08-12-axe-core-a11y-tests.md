# Axe-core a11y regression tests (PR #20)

## What

Added automated axe-core coverage on the rendered React UI. Four
RED-first tests pin the accessibility contract for App, Toggles
(default + active), and AmbiguityPicker (open) so the 70+ WCAG 2.1
A/AA + best-practice rules run on every PR. Shipped as PR #20,
which partially closed issue #19 (axe-core half — Lighthouse CI
half deferred to a follow-up PR).

Also fixed a CI flake in `tests/Cascade.test.tsx` where
`user.selectOptions` fired before the kingdoms fetch populated the
`<option>` list.

## How

### 1. axe-core tests

New file `frontend/tests/a11y.test.tsx` with 4 RED-first tests:

- App has no axe violations on the empty render.
- Toggles has no axe violations with default state.
- Toggles has no axe violations with active toggles.
- AmbiguityPicker has no axe violations when open.

Used the raw `axe()` return value rather than `toHaveNoViolations`
because `vitest-axe/extend-expect` only takes effect in some Vitest
contexts. The raw check yields a clear failure message with
violation id, impact, and help URL when an assertion fires.

Rule set: `wcag2a, wcag2aa, wcag21a, wcag21aa, best-practice` —
matches what Lighthouse audits in CI, so the verdict stays
consistent across both checks once LHCI lands.

`tests/setup.ts` stubs `HTMLCanvasElement.prototype.getContext` so
jsdom does not spam a warning every time axe-core evaluates colour
contrast.

### 2. CI flake fix in Cascade test

The kingdom `<select>` renders with only "Loading children…" while
the initial kingdoms fetch is in flight. `findByRole("combobox", {
name: /kingdom/i })` returns as soon as the `<select>` exists, but
`user.selectOptions` requires the target `<option>` to be present.
On the CI runner the kingdoms fetch resolved microseconds after
`findByRole`, so `selectOptions` fired against a select whose
option list did not yet contain "Animalia" and failed with
"Value 'Animalia' not found in options". Local runs masked the
flake because the fetch resolved microseconds before
`findByRole`.

Fix: `await screen.findByRole("option", { name: "Animalia" })`
before `selectOptions`. Same pattern the rest of the file already
uses for the phyla switches.

## Where

- `frontend/tests/a11y.test.tsx` — new, 4 axe-core tests.
- `frontend/tests/setup.ts` — canvas getContext stub.
- `frontend/package.json` — `axe-core` + `vitest-axe` deps.
- `frontend/package-lock.json` — lockfile update.
- `frontend/tests/Cascade.test.tsx` — wait for Animalia option
  before selectOptions.

## Why

The hand-rolled audit (`docs/audits/lighthouse-a11y.md`) walks
the 10 dimensions from the impeccable skill and produced the P2/P3
fixes in #18, but it only runs manually. axe-core adds automated
coverage for a wider rule set (form labels, colour contrast, alt
text, heading hierarchy, accessible button names, and 70+ others)
on every PR. Catching regressions automatically is cheaper than
discovering them in the next manual audit cycle.

Issue #19 grouped this work with Lighthouse CI as one followup.
Slicing them was a judgement call:

- axe-core is self-contained (a Vitest dependency + 4 tests,
  zero CI infra changes).
- Lighthouse CI needs four pieces of glue (npm scripts, lhci
  config, Puppeteer script + stub server, new CI job in
  `.github/workflows/ci.yml`).
- Putting them in one PR would have ballooned the diff to
  ~300 lines and mixed test-only with infra.

The smaller slice ships the higher-value coverage first; LHCI
follows in a separate PR with its own focused review.

## How it works

`npm test` in `frontend/` runs 51 tests across 7 files. On the
CI runner (Ubuntu + Node 20), Vitest spins up jsdom and Vitest
executes the 4 axe-core tests serially. Each test renders the
component under test, runs `axe()` with the standard rule set,
and asserts `violations.length === 0`. Any violation fails the
test with the rule id, impact level, affected nodes, and a help
URL pointing at the axe-core rule documentation.

The fix in Cascade test makes the timing explicit: the test now
waits for the kingdoms `<option>` to exist before issuing the
`selectOptions` user event, which is the correct RTL pattern
when an async fetch populates a `<select>`.

## Workflows

- **CI** — frontend job runs `vitest run` after `tsc --noEmit`
  + `eslint`. Axe-core failures surface as Vitest assertion
  errors with the rule context inline.
- **Reviews** — small PR (4 files, +246 / -163 lines). Fits the
  review-budget line. Reviewer focus: the test list (4 axe-core
  + the timing fix) and the deps bump (`axe-core`, `vitest-axe`).
- **Future PR (LHCI)** — needs npm scripts, `.lighthouserc.json`
  `puppeteerScript` reference, `*.tsbuildinfo` added to
  `frontend/.gitignore`, and a new `lighthouse` job in
  `.github/workflows/ci.yml` that downloads the
  `frontend-dist` artifact and runs `npx lhci autorun`. Drafted
  config and scripts are stashed on `feat/a11y-ci-axe` as
  `stash@{0}` for that PR.
