# Design audit — taxon.pen (Phase 3)

## Context

The Pencil CLI (`pen --agent codex`) generated `taxon.pen` covering the cascade UI, mobile layout, and feedback state matrix. This audit inspects the generated design against the impeccable skill criteria: hierarchy, accessibility, typography, color, motion, and anti-patterns.

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Hierarchy & Information Architecture | 4 | Clear top-level partition: Component Shelf / Desktop / Mobile / States |
| 2 | Accessibility (Touch Targets, Contrast) | 3 | Touch targets ≥44px; focus-ring example rendered; toggle aria-pressed implied |
| 3 | Typography | 3 | Inter (sans) + IBM Plex Mono (mono) replaces system-ui; type scale implied via text styles |
| 4 | Color & Theming | 3 | 9 design tokens used; 10 hard-coded hex values flagged for token extraction |
| 5 | Implementation Integrity | 4 | Reusable components isolated in Component Shelf; states matrix parallel to canonical UI |
| **Total** | | **17/20** | **Good (minor polish recommended)** |

## Implementation Integrity Verdict

**Pass.** The design expresses a coherent product-specific system:
- Component Shelf isolates four reusable primitives (Toggle Chip, Dropdown Field, Source Link Button, Species Row). They are referenced from both Desktop and Mobile frames, so the design is anchored on the components rather than free-laid geometry.
- The States Feedback Matrix runs parallel to the canonical Desktop page, so every async surface (loading, empty, 404, 409 ambiguity, network error) has a representation the user can compare side-by-side.
- The design uses 9 semantic tokens (`$accent`, `$amber`, `$bg`, `$border`, `$muted`, `$navy`, `$red`, `$slate`, `$surface`) and only 10 hard-coded hex values — the latter are limited to dot/badge fills that need explicit semantic color (red-50 for extinct background, amber-100 for synonym background).

## Executive Summary

- Audit Health Score: **17/20** (Good — address weak dimensions).
- Issues: 1 P2 (hard-coded colors), 1 P3 (Inter + IBM Plex Mono vs system stack).
- Top issues:
  1. **[P2]** Hard-coded hex values used for badge backgrounds should resolve to `$red-50`, `$amber-100`, `$green-50`, `$blue-50` style tokens.
  2. **[P3]** System font stack rejected by Pencil; Inter + IBM Plex Mono chosen. Acceptable trade-off; document in DESIGN.md.
- Recommended next steps: extract color tokens, document DESIGN.md, then proceed to React implementation.

## Detailed Findings by Severity

### [P3] System font stack rejected by Pencil

- **Location**: All text elements in `taxon.pen`.
- **Category**: Typography.
- **Impact**: The system-ui / ui-monospace stack from the brief could not be expressed; Inter and IBM Plex Mono were substituted.
- **WCAG/Standard**: N/A (typographic preference).
- **Recommendation**: Accept the substitution; document in `frontend/src/index.css` that the production code falls back to system-ui before Inter.
- **Suggested command**: `/impeccable typeset` (in code review).

### [P2] Hard-coded hex values for badge backgrounds

- **Location**: Component Shelf → Component / Species Row → Badge Slot.
- **Category**: Color & Theming.
- **Impact**: 10 hex values (`#16a34a`, `#94a3b8`, `#bfdbfe`, `#cbd5e1`, `#e2e8f0`, `#eff6ff`, `#f8fafc`, `#fecaca`, `#fed7aa`, `#ffffff`) used for semantic badge states.
- **WCAG/Standard**: N/A (consistency, not accessibility).
- **Recommendation**: When translating to code, define tokens like `$success-50`, `$success-600`, `$danger-50`, `$warning-50`, `$neutral-100`, `$neutral-200`, `$neutral-300`, `$bg`, `$surface`, `$accent-50`. The React implementation should use Tailwind utility classes that resolve to the same token family.
- **Suggested command**: `/impeccable colorize` (during code review).

### [P3] Pencil `.pen` cannot be screenshot from external MCP client

- **Location**: N/A — environment limitation, not a design defect.
- **Category**: Operational.
- **Impact**: The audit relies on JSON inspection of the design rather than visual inspection. The design file is well-formed (109 KB, structured hierarchy) but a final visual review requires opening the file in Pen.app.
- **Recommendation**: Visual review should happen interactively in Pen.app before approval. Document the screenshot reference once taken.
- **Suggested command**: `/impeccable critique` (visual review when the user can show the screenshot).

## Positive Findings

- **Component-first design**: Four reusable primitives (Toggle Chip, Dropdown Field, Source Link Button, Species Row) referenced from Desktop and Mobile frames. This is the right pattern for a design system.
- **State coverage**: Loading / empty / 404 / 409 / network-error / disabled / focus / active toggle all rendered. The state matrix is rare and appreciated — most designs skip these.
- **Token discipline**: 9 semantic tokens used consistently; hard-coded hex limited to badge backgrounds that need explicit semantic color.
- **Mobile + Desktop parity**: Both breakpoints shipped side-by-side; the Mobile frame is 390×1880 (typical iPhone viewport) and the Desktop is 1440×1180 (typical laptop viewport).
- **Layout choice**: Two-column desktop (cascade + list on left, links + breadcrumb on right); single-column mobile. Matches the spec request.
- **Sci-hub visually separated**: Per the brief, Sci-hub is marked as a separate source in the links panel.

## Patterns & Systemic Issues

None. The design uses one consistent system across components and states.

## Recommended Actions

1. **[P3] `/impeccable polish`**: Final visual review in Pen.app after opening `taxon.pen` interactively. Look for any visual regressions before signing off.
2. **[P2] `/impeccable colorize`**: During React implementation, extract the 10 hard-coded hex values into named Tailwind tokens.
3. **[P3] `/impeccable typeset`**: During React implementation, document the system-ui → Inter fallback in the project's CSS entry point.

After all three are addressed, the design is ready for code translation.

## Approval

| Item | Status |
| --- | --- |
| Hierarchy | ✅ |
| Information architecture | ✅ |
| Reusable components | ✅ |
| States coverage | ✅ |
| Mobile + Desktop parity | ✅ |
| Color tokens | ⚠️ Token extraction during code |
| Typography | ⚠️ Fallback documented during code |
| Touch targets | ✅ |
| Focus management | ✅ |
| Visual review in Pen.app | ⏳ User action |

The design is **approved for code translation** with two follow-ups tracked for the React phase.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| Design file | `taxon.pen` (109 KB) |
| Generator | `pen --agent codex --model gpt-5.5` (Pencil CLI) |
| Audit score | 17/20 |
| Audit dimensions | 5 (hierarchy, a11y, typography, color, integrity) |
| Issues | 1 P2 + 2 P3 |
| States covered | 8 (loading, empty, 404, 409, network, disabled, focus, active) |
| Reusable components | 4 |
| Viewports | 2 (Desktop 1440, Mobile 390) |