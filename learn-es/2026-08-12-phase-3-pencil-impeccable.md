# Phase 3 — Frontend design (Pencil + impeccable)

## What

Generated the cascade UI design via `pen --agent codex --model gpt-5.5`,
audited it under the impeccable skill criteria, and approved the
design for code translation. Phase 4 (React frontend) starts now.

## How

- `pen --in taxon.pen --out taxon.pen --agent codex --model gpt-5.5
  --effort high --prompt "<detailed brief>"` generated the design.
- The brief encoded all 8 requirements (header, toggles, cascade,
  species list, breadcrumb, links, ambiguity picker, states), the
  design system (palette, typography, spacing, radius, shadow), the
  accessibility checklist (labels, ARIA, focus rings, contrast,
  modal escape), and the layout (max width, two-column on desktop,
  single column on mobile).
- The audit walked the resulting `taxon.pen` JSON for hierarchy,
  token usage, reusable components, state coverage, and dimensions.
  Each dimension scored 0-4 per the impeccable rubric.
- The Pencil CLI was reached via the OAuth login
  (`pen login → email + password`) the user set up. No MCP server
  involvement.

## Where

- `taxon.pen` — Pencil design file (109 KB, 2984 lines).
- `docs/design/design-audit.md` — impeccable audit (17/20, Good).
- `docs/design/approval.md` — Phase 3 sign-off.
- `docs/design/blocked.md` — documents the Pencil MCP server bug
  we hit before pivoting to the CLI.
- `documents-es/design/approval-es.md` — Spanish mirror.
- `scripts/pencil_client.py` — minimal MCP client kept as a
  debugging reference (Pencil MCP server rejects external tool
  calls; the CLI is the working alternative).

## Why

AGENTS.md §5 mandates:

> any UI design work is performed **first** in Pencil MCP and
> audited under the `impeccable` skill before any implementation in
> code.

The design must exist and be approved before any React frontend
code lands. The Phase 4 frontend will reference the same color
tokens, typography, and component shapes captured here.

## How it works

The design is structured as four top-level frames inside the
`.pen` canvas:

1. **Component Shelf** — 4 reusable primitives (Toggle Chip,
   Dropdown Field, Source Link Button, Species Row). Each is
   referenced from both Desktop and Mobile frames so the
   components own the design language, not free-laid geometry.
2. **Desktop / Taxon Species Dispatcher** (1440×1180) — Header +
   two-column workspace (cascade + list on left, links + breadcrumb
   on right).
3. **Mobile / Taxon Species Dispatcher** (390×1880) — Header +
   Include Group + Cascade Stack + Species List + Breadcrumb.
4. **States / Taxon Feedback Matrix** (980×1080) — 8 state cards
   parallel to the canonical UI: Loading children, No children,
   Not found, Network error, Ambiguous — pick one, Disabled Cascade,
   Focus Ring, Active Toggle.

The audit script walks the JSON tree and reports:

- 9 semantic tokens used (`$accent`, `$amber`, `$bg`, `$border`,
  `$muted`, `$navy`, `$red`, `$slate`, `$surface`).
- 10 hard-coded hex values for badge backgrounds (flagged P2 — to
  be token-extracted during React implementation).
- 4 reusable components isolated in Component Shelf.
- 2 viewports (Desktop 1440, Mobile 390).
- 8 state cards in the feedback matrix.

## Workflows

- Pencil CLI auth: `pen login` (email + password) or
  `PEN_CLI_KEY=...` for CI/CD.
- Design generation: `pen --in taxon.pen --out taxon.pen --prompt
  "..." --agent codex --model gpt-5.5 --effort high`.
- Audit: walk the JSON tree, score each dimension 0-4 per the
  impeccable rubric, write `docs/design/design-audit.md`.
- Approval: write `docs/design/approval.md` with the score, the
  two follow-ups, and the next phase. Mirror in
  `documents-es/design/approval-es.md` per AGENTS.md §1.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| Design file | `taxon.pen` (109 KB) |
| Audit | `docs/design/design-audit.md` (17/20, Good) |
| Approval | `docs/design/approval.md` |
| Spanish mirror | `documents-es/design/approval-es.md` |
| Generator | `pen --agent codex --model gpt-5.5` |
| Issue | https://github.com/Sebailla/taxon/issues/9 (Phase 3 slice) |
| PR | https://github.com/Sebailla/taxon/pull/10 (squash-merged) |
| Worktree | `../taxon-worktrees/pr4-frontend` (cleaned up) |
| Branch | `feat/species-search-dispatcher-frontend` (deleted) |
| Components | 4 reusable |
| Viewports | 2 (Desktop 1440, Mobile 390) |
| States | 8 |
| Audit dimensions | 5 (hierarchy, a11y, typography, color, integrity) |
| Issues | 1 P2 + 2 P3 |

## Deviations

- **System font stack rejected.** The brief specified
  `system-ui` / `ui-monospace`. The Pencil CLI agent chose
  `Inter` / `IBM Plex Mono` because Pencil's text engine rejected
  the `system-ui` literal. Tracked as P3 — the React CSS will
  declare `system-ui, Inter, sans-serif` so the user's OS font
  wins before Inter loads.
- **Pencil MCP server bug blocked the standard workflow.** The
  Pencil MCP server (Pen.app) registered my client connection but
  rejected every `tools/call` request with a 62-second timeout. The
  `client_id` monkey-patch in `scripts/pencil_client.py` cleared
  the "missing client_id" log error but the timeout persisted.
  Pivoted to the Pencil CLI (`pen`), which bypasses the MCP server
  entirely. Documented in `docs/design/blocked.md`.
- **Visual review in Pen.app deferred.** A final visual review of
  `taxon.pen` is recommended in the Pen.app UI before code
  translation begins. Deferred to the user — the JSON walk
  confirmed the structure is coherent but does not catch visual
  regressions.

## Next steps

Phase 4 (React + Vite + Tailwind frontend) ships next. The
frontend will:

- Use the same color palette and typography as `taxon.pen`.
- Implement the cascade as a 6-step `useReducer` state machine so
  every transition is testable.
- Render the 12-link grid with the same visual treatment.
- Use Tailwind tokens to substitute the 10 hard-coded badge colors
  from the design.
- Be audited with the impeccable `audit` command during code
  review.