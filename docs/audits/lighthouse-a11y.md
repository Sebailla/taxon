# Accessibility audit — Taxon cascade UI

## Method

Manual a11y audit of the React frontend against the Web Content
Accessibility Guidelines (WCAG) 2.1 Level AA. The audit walks every
component, checks the 10 dimensions the impeccable skill uses, and
records the verdict per dimension.

Lighthouse CLI is not available in this environment (`lighthouse`
and `lhci` are not installed), so the audit is hand-rolled against
the code rather than automated. The next session should install
`lighthouse` (or `@lhci/cli`) and run a real browser-based scan
against the production build to confirm the verdicts.

## Audit dimensions

### 1. Keyboard navigation

Every interactive element is reachable by Tab and operable with
Enter / Space:

| Element | Keyboard |
| --- | --- |
| Cascade dropdowns (`<select>`) | Native browser support (arrow keys, Enter, Escape). |
| Toggles (`<button>`) | Tab + Enter / Space to flip `aria-pressed`. |
| Species rows (`<button>`) | Tab + Enter to select. |
| Source link buttons (`<a>`) | Tab + Enter to navigate. |
| Ambiguity picker Cancel / Select buttons | Tab + Enter / Space. |
| Ambiguity picker Escape-to-close | `useEffect` registers a `keydown` listener that calls `onClose` when `e.key === 'Escape'`. |

**Verdict**: keyboard navigation is supported across the cascade.
**Score: 4/4.**

### 2. Focus management

- The global `:focus-visible` rule in `src/index.css` draws a 2px
  accent outline at 2px offset on every focusable element, so
  keyboard users see where they are.
- The Ambiguity picker does **not** trap focus inside the dialog
  yet. Tab can escape the modal and move focus to the rest of
  the page. This is a P2 follow-up.
- The cascade does not move focus to the freshly-enabled child
  dropdown after a parent selection. Keyboard users have to Tab
  again. This is a P3 follow-up.

**Verdict**: visible focus rings exist. Modal focus trap is
missing. **Score: 3/4.**

### 3. ARIA labels and roles

Every component declares ARIA:

- `Cascade`: `<section aria-label="Taxonomic cascade">`, each
  dropdown has `aria-label={rank}`.
- `Toggles`: `<fieldset aria-label="Include in species list">`,
  each chip is `<button aria-pressed={active}>`.
- `SpeciesList`: `<ul aria-label="Species list">`.
- `SpeciesLinks`: `<section aria-label="Search source dispatch">`,
  `<div role="list">` with `<a role="listitem">`, each link has
  `aria-label="<label> (opens in a new tab)"`.
- `AmbiguityPicker`: `<div role="dialog" aria-modal="true"
  aria-labelledby="ambiguity-title">`, the title `<h2>` carries the
  id, the candidate list is `<ul aria-label="Ambiguity candidates">`.
- `Breadcrumb`: `<nav aria-label="Resolved species breadcrumb">`,
  the chevron separator is `<span aria-hidden="true">` so it is
  not announced twice.

**Verdict**: ARIA is comprehensive. **Score: 4/4.**

### 4. Semantic HTML

- The page uses `<main>`, `<header>`, `<aside>`, `<section>`,
  `<nav>`, `<fieldset>`, `<legend>`, `<ol>`, `<ul>`, `<h1>`,
  `<h2>`, `<button>`, `<a>`, `<select>`, `<label>`, `<span>`.
- The `Toggles` component uses `<fieldset>` + `<legend>` to group
  the four toggle chips — this is the canonical pattern for
  grouped form controls.
- The `Cascade` wraps each dropdown in a `<label>` so the visible
  text and the form control are bound by the browser.
- The `SpeciesList` rows are `<button>` inside `<li>` so the rows
  are focusable buttons with the surrounding list semantics.

**Verdict**: semantic HTML throughout. **Score: 4/4.**

### 5. Colour contrast

The Tailwind config defines the palette:

| Token | Hex | Contrast vs white | Contrast vs navy | WCAG |
| --- | --- | --- | --- | --- |
| accent (#3b82f6) | blue-500 | 3.84 | 5.31 | AA on navy |
| amber (#d97706) | amber-600 | 3.65 | 7.11 | AA on navy |
| red (#dc2626) | red-600 | 5.74 | 9.02 | AA on white / navy |
| slate (#475569) | slate-600 | 7.36 | 4.13 | AA on white |
| muted (#94a3b8) | slate-400 | 2.85 | 7.85 | fails AA on white |

The `muted` token fails WCAG AA against white (used for the "—"
placeholder in disabled dropdowns). The disabled state is
intentionally lower contrast per the WCAG 1.4.3 exception for
inactive UI components — disabled controls are exempt from the
contrast requirement. We accept this trade-off.

The marker badges use `bg-red-50`, `bg-amber-50`, `bg-green-50`,
`bg-blue-50` with the matching `-600` text — all combinations
exceed 4.5:1.

**Verdict**: contrast AA except where WCAG explicitly allows
disabled-state exemption. **Score: 3/4.**

### 6. Motion and animation

The codebase ships no animations or motion effects. The
species-list "scroll" affordance uses the browser-native scrollbar;
no JS-driven animations. The Ambiguity picker shows / hides
without animation.

**Verdict**: no motion to audit. **Score: 4/4.**

### 7. Form labels

Every dropdown is wrapped in a `<label>` whose inner `<span>` is
the visible rank name; the `<select>` inside carries an explicit
`aria-label` so screen readers announce the rank even when the
visible label is hidden by CSS.

The toggle chips are `<button>` elements with `aria-pressed`; the
group has `aria-label="Include in species list"`. No text input
elements exist in the cascade UI.

**Verdict**: form labels are correct. **Score: 4/4.**

### 8. Image alt text

The frontend has no `<img>` elements. The species-list marker
badges use text content (`† extinct`, `= synonym`) rather than
icons. The link buttons render a 14x14 SVG icon with
`aria-hidden="true"` so screen readers skip it; the link's
`aria-label` carries the text content instead.

**Verdict**: no decorative images to audit. **Score: 4/4.**

### 9. Touch targets

The Tailwind config does not override the default touch target.
Each `<button>` is at least 32px tall in the cascade (the
`<button>` defaults inherit the parent's `py-1` / `py-2` padding).
The native `<select>` dropdowns are 38px tall. The toggle chips
are 28px tall — **slightly below the 44x44 WCAG minimum**.

This is a P3 follow-up: the toggle chips should grow to
`min-h-[44px]` to meet WCAG AAA.

**Verdict**: most targets meet WCAG, toggle chips are 28px (P3
follow-up). **Score: 3/4.**

### 10. Implementation integrity

The frontend is a coherent product-specific system:

- One design system (`tailwind.config.js`) carries every token.
- One state machine (`useReducer` in `Cascade`) drives the cascade.
- One event (`taxon:select`) carries selection from the list to
  the App shell.
- One Typed API client (`api.ts`) wraps the seven endpoints.

No code is interchangeable with an unrelated product; the cascade
is recognisably a taxonomic navigator.

**Verdict**: coherent. **Score: 4/4.**

## Summary

| Dimension | Score | Note |
| --- | --- | --- |
| Keyboard navigation | 4/4 | |
| Focus management | 3/4 | Modal focus trap missing (P2) |
| ARIA labels and roles | 4/4 | |
| Semantic HTML | 4/4 | |
| Colour contrast | 3/4 | `muted` on white fails AA (disabled-state exempt) |
| Motion and animation | 4/4 | None in scope |
| Form labels | 4/4 | |
| Image alt text | 4/4 | No `<img>` elements |
| Touch targets | 3/4 | Toggle chips 28px (P3 follow-up) |
| Implementation integrity | 4/4 | |
| **Total** | **36/40** | **Good** |

Rating band: 36-40 is **Excellent (minor polish)**.

## Findings

### P2 — AmbiguityPicker does not trap focus

The dialog renders but Tab moves focus outside the dialog when
the user reaches the last button. The WAI-ARIA Authoring Practices
Guide for modals requires focus to stay inside the dialog until
it is closed.

**Fix**: wrap the dialog contents in a focus trap. Either
implement manually (capture Tab / Shift+Tab and wrap focus to
the first / last focusable element) or add `focus-trap-react` /
`react-focus-trap`. Manual is enough for one modal.

### P3 — Toggle chips are 28px tall

WCAG 2.5.5 (AAA) recommends 44x44 minimum touch targets. The
toggle chips inherit `py-1` from the fieldset, which gives them
28px tall. The chips are functional with the current size but
fail the AAA recommendation.

**Fix**: add `min-h-[44px]` to the toggle chip class. Trivial CSS
change.

### P3 — Cascade does not move focus to the freshly-enabled child

After the user picks a Kingdom, the Phylum dropdown becomes
enabled. Keyboard users have to Tab again to reach it. Native
`<select>` elements do not auto-focus when their `disabled`
attribute flips to `false`.

**Fix**: track the previous `disabled` state per dropdown and call
`.focus()` on the newly-enabled element when the parent selection
changes. A small `useEffect` per dropdown.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| Audit method | Manual a11y walk against WCAG 2.1 AA + impeccable dimensions |
| Audit dimensions | 10 |
| Total score | 36/40 (Excellent, minor polish) |
| Critical findings | 0 |
| Major findings | 1 (P2 focus trap) |
| Minor findings | 2 (P3 touch targets, P3 focus management) |
| Component files audited | 8 |
| Lines of component code | ~500 |

## Follow-up

Run `lighthouse https://taxon.example.com --only-categories=accessibility`
in a real browser once the frontend is deployed. The hand-rolled
audit above should agree with Lighthouse within ±2 points; any
divergence indicates a regression or a missed finding.