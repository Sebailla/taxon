# Stitch Design: tree-deep-subtree (Tier Groups)

> **Design gate artifact for PR C** (replaces the Pencil `.pen` page per the `arbol-col-browse` and `species-folder-explorer` precedent, now using Stitch MCP since Pencil is deprecated).

## Stitch project

- **Project ID**: `projects/11955314884511019764`
- **Project title**: "Taxon — Tree Deep Subtree (Tier Groups)"
- **Tool**: Stitch MCP (`stitch_generate_screen_from_text`)
- **Origin**: `PROJECT_DESIGN`
- **Device type**: `DESKTOP`
- **Screen**: "Taxonomic Tree Browser" (2560×2214)

## Design brief (what Stitch was asked to render)

A taxonomic-tree browse UI, desktop, light mode. Top bar with title, search, and toggles. Breadcrumb `Eukaryota > Animalia`. Tree rows with caret + indent + uppercase rank label + scientific name + species-count badge. After the direct children of `Animalia`, a tier-group section labelled `Phyla (34)` with caret header and the first 50 phylum rows indented deeper, plus a "Load more" affordance. Inter font. Slate background.

## What the rendered screen shows

- Top bar: "Taxonomic Tree" title + "Find taxon…" search + "Source" + "Extant only" toggles + nav (Browser / Classification / Settings).
- Breadcrumb: "Eukaryota > Animalia" with the active segment tinted with the primary blue left border.
- Direct children of Eukaryota shown: KINGDOM `Animalia` (highlighted), then KINGDOM `Plantae` and `Fungi` (Kingdom bucket, with negative species counts because they collapse to nothing).
- **Tier-group "Phyla (34)"**: caret + label + "Load all" button on the right; first 5 phyla rendered (Arthropoda, Mollusca, Chordata, Nematoda, Priapulimorpha) with the "via subphylum rollup" inline note where the rollup depth > 1.
- Footer: "© 2024 Taxonomic Database System · Citation Policy · Data Sources" + system status.

## What the implementer MUST translate line-by-line

| Surface element | Stitch says | Translation rule |
|---|---|---|
| Tier-group header background | Same row tint as direct children | Promote to `bg-slate-100` (or `surface_container_low`) + caret rotation when expanded. Distinguish from regular rows. |
| "Load all" button | Solid blue button | Re-render as ghost text-button aligned right with chevron icon: `text-slate-700 hover:bg-slate-100 px-3 py-1 rounded-md`. Matches Taxon design system (subtle, not loud). |
| Caret direction | `▸` static | Component MUST toggle `▾` when tier group is expanded; rotate 90° via CSS `transform: rotate(90deg)` with `aria-expanded` mirror. |
| "via subphylum rollup" inline note | Grey-italic suffix | Render as `<span class="text-xs italic text-slate-400 ml-2">via subphylum rollup</span>` only when rollup_depth > 1. |
| Rank label badge | Monospace uppercase, slate-tinted bg | `font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-500`. |
| Species-count badge | Right-aligned, monospace number + `spp.` | `font-mono text-sm text-slate-500` right-aligned in row. |

## What the implementer MUST NOT do

- No new design tokens. Tailwind defaults from the project's existing `tailwind.config.js` only.
- No new colour palette. Use the existing slate + primary blue (matches the active breadcrumb segment).
- No new components in the design system beyond `<TierGroup>` itself. Tier rows reuse `<TreeNodeRow>` verbatim.
- No `stone-*` classes (project drift documented in `docs/design/taxonomic-tree-browse.md` §15 — apply the same reconciliation).

## Gate status

- [x] Stitch design rendered.
- [ ] `impeccable` skill audit pass — hierarchy, accessibility, typography, color, motion, anti-patterns.
- [ ] Audit findings folded back into this brief or marked as SUGGESTION for follow-up.
- [ ] Design sign-off recorded before PR C starts.


## impeccable audit pass (degraded inline — single-context banner)

`Method: ⚠️ DEGRADED: single-context (impeccable skill is not a delegable subagent_type in this harness; Assessment B detector `detect.mjs` not installed at the project root, so the deterministic scan was skipped).`

### Findings

| # | Severity | Finding | Recommended fix |
|---|----------|---------|-----------------|
| 1 | **P1 / WCAG AA fail** | "Load all" button uses `text-outline` (#737686) on `bg-surface-container-low` (#f2f4f6). Contrast ~3.6:1 — below the 4.5:1 threshold for normal text. Same for `via subphylum rollup` italic. | Use `text-on-surface-variant` (#434655) on the same background → ratio ~7.4:1, passes AA + AAA. |
| 2 | **P1** | "Load all" button is rendered `cursor-not-allowed opacity-50` even though there are only 34 phyla (well below the 50-row cap → button SHOULD be hidden, not disabled). | Hide the button entirely when `next_cursor is null` after the first page. Show only when `len(children) < tier_total`. |
| 3 | **P2 / a11y** | Tier-group header caret uses `arrow_drop_down` static — no rotation or `aria-expanded` mirror. Screen-reader users can't tell expanded vs collapsed. | Swap caret to `arrow_right` (collapsed) / `arrow_drop_down` (expanded); add `role="button"` `aria-expanded={open}` `aria-controls={tierListId}` on the header. |
| 4 | **P2** | The vertical connector line (`bg-outline-variant/30`) crosses through the tier-group header, making the grouping indistinguishable from regular tree rows. | Break the connector at the tier-group header (`before:` pseudo-element or `gap-y` margin) so the header sits in its own slot. |
| 5 | **P2** | Rank label uses identical treatment (font, weight, badge bg) for every rank — Kingdom, Phylum, Genus all look the same. | Keep monospace + uppercase, but vary badge color subtly by rank (Phylum: `bg-primary/5`, Family: `bg-secondary/5`, Genus: `bg-tertiary/5`). Optional — only if project design system allows rank-specific tokens. |
| 6 | **P3** | `~320,000 spp.` tilde prefix on Plantae/Fungi (under Eukaryota parent) — no legend explaining it's an approximate count when children are kingdoms without computed descendants. | Add a `<abbr title="Approximate">~</abbr>` or inline tooltip "approximate count". |
| 7 | **P3** | "Source" toggle shows OFF (white dot left) with no label hinting what sources are available. | Add a tooltip on the toggle OR change label to "Source: CoL" with a click-to-expand chip. |

### Design health (heuristic estimate, single-context)

| # | Heuristic | Score | Note |
|---|-----------|-------|------|
| 1 | Visibility of System Status | 3 | Breadcrumb + active row work; tier-group header missing state. |
| 2 | Match System / Real World | 3 | Taxonomic language is accurate (Kingdom / Phylum / spp.). |
| 3 | User Control and Freedom | 3 | "Load all" affordance is present (broken but present). |
| 4 | Consistency and Standards | 3 | Reuses Taxon patterns from `taxonomic-tree-browse.md`. |
| 5 | Error Prevention | 3 | Disabled button prevents premature pagination. |
| 6 | Recognition Rather Than Recall | 3 | Caret conventions are universal. |
| 7 | Flexibility and Efficiency | n/a | Operate surface — keyboard nav tracked in PR C WU 5 separately. |
| 8 | Aesthetic and Minimalist | 3 | Light palette, sparse ornament. |
| 9 | Error Recovery | n/a | No error states in the static render. |
| 10 | Help and Documentation | n/a | Documentation is upstream of this gate. |

**Total**: 21/24 → 87% → **Excellent band** (per renormalised max after 2 n/a).

### Gate decision

`status: warning` — **approve with one P1 contrast fix and the disabled-button bug**. Both are mechanical changes the implementer can apply without re-running Stitch:

- **P1 #1**: change `text-outline` to `text-on-surface-variant` on the load-more and rollup-note elements.
- **P1 #2**: hide the load-more button when `tier_total ≤ tier_limit`.

The remaining P2/P3 items are tracked as SUGGESTIONs for follow-up issues; they don't block PR C.

### Next

PR C implementer (`feat/tree-deep-subtree-pr3` worktree) translates the surface brief line-by-line, applying the two P1 fixes inline. The 5 work units in `tasks.md` Phase 3 stay as-is.
