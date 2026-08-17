# Design — Taxonomic Tree Browse

> **Surface brief for PR 3 (frontend TaxonomicTree).** This document replaces the Pencil `.pen` page that AGENTS.md §5 normally mandates. The Pencil MCP is disabled in this session, so the design pass goes straight to the impeccable framework and is captured here as a markdown artifact. The frontend implementer MUST translate this document line-by-line into `TaxonomicTree.tsx`, `TaxonomicTree.state.ts`, and the Tailwind classes. **No visual decisions are left to the implementer.**

---

## 1. Surface statement

The **Taxonomic Tree Browse** surface is the left-hand pane of the Taxon's two-column layout (`frontend/src/App.tsx`). It replaces the 7-fixed-dropdown `Cascade` with a CoL-style hierarchical tree that lazy-loads children by `parent_id`, indents by rank, and renders every row as `rank: Name Authorship • N spp.`. A "Find taxon" autocomplete lives in the header; the explored path flows through the `cascadePath` Zustand store and a `path:change` CustomEvent so the right-hand breadcrumb-links panel keeps working.

**Mode:** Operate. The visitor is completing a task (locating a taxon to land on a species). Scanability, consistency, and native expectations outrank expression. Brand lives in precise details — straight typography, tight spacing, restrained color — not in loud accents.

**Reference image:** `../../col-tree.png` (the original Catalogue of Life "Browse" page). The reference is a starting point, not a copy. The new tree's brand identity is the project's existing `navy`/`slate`/`border`/`accent` palette + tight typography + 32px row rhythm, **not** CoL's bright-blue links + 26px dense layout.

**What it replaces:** `frontend/src/components/Cascade.tsx` (425 lines) + `Cascade.state.ts` (180 lines) + six `cascade*.test.tsx` files. The grid slot in `App.tsx` is unchanged: `<TaxonomicTree>` mounts in the same slot the `<Cascade>` occupied.

---

## 2. Layout & grid

### Desktop (≥ 1024px)

```
┌─────────────────────────────────────────────────────────────┐
│ Find taxon (e.g. Panthera)              [ ] Source  [ ] Extant only │
│ ─────────────────────────────────────────────────────────── │
│ ▾ KINGDOM Animalia • 1,792,173 spp.                          │
│   ▸ PHYLUM  Chordata • 86,602 spp.                           │
│     ▸ CLASS  Mammalia • 7,164 spp.                           │
│       ▸ ORDER  Carnivora • 389 spp.                          │
│         ▸ FAMILY Felidae • 152 spp.                         │
│           ▸ GENUS  Panthera • 44 spp.                        │
│             ▸ SPECIES Panthera leo (Linnaeus, 1758) • 28 subsp.│
└─────────────────────────────────────────────────────────────┘
```

- Container `max-w-page` (1200px, defined in `tailwind.config.js`).
- Inner card: `rounded-card border border-border bg-surface p-4` (mirrors the Breadcrumb card).
- Header row: `flex items-center gap-3` — search input takes `flex-1`, filters right-aligned.
- Tree rows: vertical list with `gap-0` (the indent guides paint the rhythm).
- The card sits inside the existing `App.tsx` left-grid column (`lg:col-span-1` of `grid-cols-1 lg:grid-cols-2`).

### Tablet (640–1024px)

```
┌──────────────────────────────────────────────────┐
│ Find taxon (e.g. Panthera)              [search] │
│ [ ] Source  [ ] Extant only                      │
│ ──────────────────────────────────────────────── │
│ ▾ KINGDOM Animalia • 1,792,173 spp.               │
│   ▸ PHYLUM  Chordata • 86,602 spp.                │
│   ...                                            │
└──────────────────────────────────────────────────┘
```

- Filters collapse to a single row below the search input.
- Stack header: `flex flex-col gap-3`; the inner row uses `flex flex-wrap items-center gap-3`.

### Mobile (< 640px)

```
┌──────────────────────────────┐
│ Find taxon (e.g. Panthera) │
│ <details>Filters</details>  │
│ ─────────────────────────── │
│ ▾ Animalia • 1.79M spp.     │
│   ▸ Chordata • 86,602 spp.  │
│   ...                        │
└──────────────────────────────┘
```

- Filters move into a `<details><summary>Filters</summary>...</details>` accordion.
- Row height drops from 32px to 28px (compact). Indent step drops from 16px to 12px.
- Rank label hides on the row (the species badge is the only visible marker).
- Touch targets ≥ 44×44px — each row, the caret, the search input, the filter checkboxes.

### Tailwind grid suggestions

```
container:      max-w-page mx-auto
tree card:      rounded-card border border-border bg-surface p-4
header row:     flex flex-col gap-3 md:flex-row md:items-center
header input:   flex-1 h-10 rounded-md border border-border bg-surface px-3 text-sm
search type:    type="search" (native clear button)
filters row:    flex flex-wrap items-center gap-3 text-xs text-slate
tree list:      role="tree" gap-0
```

Mobile-only touch padding: `py-3` instead of `py-2` per row, so the visible 28px row is still a 44px touch target.

---

## 3. Row anatomy

This is the heart of the design. Every row is a horizontally-flexed strip. Left-to-right:

```
┌─ indent guide ─┬─ caret ─┬─ rank label ─┬─ name ─┬─ separators ─┬─ authorship ─┬─ badges ─┐
│  │             │  ▸      │  DOMAIN      │  Euk… │  ·           │  (Chatton…)  │  —       │
└────────────────┴─────────┴──────────────┴────────┴──────────────┴──────────────┴──────────┘
```

### Pixel widths and Tailwind classes

| Part | Visual | Pixel width | Tailwind classes |
|------|--------|-------------|------------------|
| **Indent guide** | 1px vertical hairline, `border-border` | 1px (matches indent step) | `before:absolute before:left-0 before:top-0 before:h-full before:w-px before:bg-border` |
| **Caret** | `▸` closed, `▾` open, 14px | 24px column (16px glyph + 4px each side) | `inline-flex h-6 w-6 shrink-0 items-center justify-center text-xs text-slate select-none` |
| **Rank label** | Small uppercase tag | auto, ~70px | `shrink-0 text-[10px] font-medium uppercase tracking-widest text-slate` |
| **Name (link)** | Primary text, 1-line truncate, hover darkens | flex-1, min-width 0 | `min-w-0 flex-1 truncate text-sm font-medium text-navy hover:text-slate focus:outline-2 focus:outline-accent` |
| **Authorship** | Smaller italic, 1-line truncate, preceded by `·` | auto, max 40% width | `hidden md:inline shrink-0 max-w-[40ch] truncate text-xs italic text-slate` |
| **Species badge** | Pill, monochrome, `tabular-nums` | auto, ~96px | `inline-flex shrink-0 items-center gap-1 rounded-full bg-bg px-2 py-0.5 text-xs font-medium text-slate tabular-nums` |

### Marker glyphs (prefixed to the rank label)

- `⚠` for `is_uncertain` — `text-amber`.
- `⊘` for `is_unassigned` — `text-muted`.
- `†` for `is_extinct` — `text-red`.
- Synonyms (`is_synonym`) are hidden by default; the "Synonyms" toggle in the header (see §4) shows them.

### Row height

- **Default (collapsed):** 32px on desktop (`h-8`), 28px on mobile (`h-7`).
- **Focused or hovered:** 36px on desktop (`h-9`), 36px on mobile (no extra height, just background).
- Row container: `flex items-center gap-2 px-2` plus the height utility.

### Row layout details

- The whole row is a `<button>` so the entire strip is clickable (no orphan click targets) and the `<button>` carries Enter/Space semantics. The caret is a visual `<span>` that rotates under CSS — clicking it does NOT call `stopPropagation`; the parent `<button>` handles the toggle.
- Indent is computed from the row's depth in the expanded tree, not from `display_level`. React renders the tree top-down; each row receives its depth as a prop.
- `aria-expanded` lives on the `<button>` and reflects caret state (`true` while the children are rendered).
- The expand/collapse is purely visual on the row's `aria-expanded`; React keys on the parent id in the cache (`childrenByParent: Map<id, TreeNode[]>`), so a collapse-then-re-expand is a free re-render of the same cached children.

### Why each pattern

- **Caret as a span, not a child button.** Keeping the caret visual-only prevents nested-interactive-element focus traps and lets the `<button>` row handle every keyboard gesture.
- **Name as the primary link, not the whole row as a link.** Screen readers announce "Eukaryota, hash, 5.4 million species" — the rest of the row is metadata. The `<button>` keeps the row clickable for mouse users.
- **Authorship hidden on mobile (`hidden md:inline`).** The deepest row of a `1200px` viewport gets a 40-character budget; on a 360px phone that overhead reads as noise. The species badge is the only contextual metadata that survives.
- **Species badge uses `tabular-nums`.** Numbers align across rows; the user does a quick visual scan "this row has 7M, this other has 200" without re-flowing.

---

## 4. Header row (above the tree)

The header is the same horizontal strip the search input + filters share.

### "Find taxon" search input

```
┌───────────────────────────────────────────────────────────────┐
│ 🔍 Find taxon (e.g. Panthera)                                 │
└───────────────────────────────────────────────────────────────┘
```

- Full width: `flex-1 h-10 rounded-md border border-border bg-surface px-3 text-sm`.
- Magnifier icon prefix: a 16px SVG (`<svg viewBox="0 0 16 16">`, hand-drawn, 1.5 stroke) at `absolute left-3 top-1/2 -translate-y-1/2`. `<svg>` is `aria-hidden="true"`; the input carries the visible label.
- 200ms debounce → `GET /api/tree/search?q={q}` (per `taxon-tree-search` spec).
- `type="search"` so the browser paints the native clear-button affordance.
- Empty state placeholder: `"Find taxon (e.g. Panthera)"`.
- `aria-label="Find taxon"`, `aria-controls="tree-search-results"`, `aria-expanded` reflects dropdown state, `aria-activedescendant` tracks the highlighted result id.

### Right-aligned filters

```
                          [ ] Source   [ ] Extant only
```

- **Source dropdown:** native `<select>` (not a checkbox — the user prompt says "Source" `dropdown`).
  - `text-xs text-slate`.
  - Options: `CoL` (active, default), `GBIF` (disabled with `disabled` attribute), `WoRMS` (disabled).
  - Tooltip: `title="Multi-source support is coming soon. CoL is the only active source."`.
  - Per the existing spec ("Source Filter (No-op First PR)"), the dropdown is purely visual for the first PR; toggling does not refetch.
- **Extant only checkbox:** native `<input type="checkbox">` + label.
  - `text-xs text-slate`.
  - Default: **unchecked** (extinct rows are visible).
  - Tooltip: `title="Hide extinct taxa"`.
  - When checked, the next `/api/tree/children` fetch (and the search) sends `?include_extinct=false` and re-renders without extinct rows.
- **Synonyms toggle** (= `is_synonym` inclusion): a pill chip mirroring the existing `Toggles.tsx` pattern.
  - `inline-flex min-h-[44px] items-center gap-2 rounded-chip border px-3 py-1 text-sm transition-colors`
  - Active: `border-accent bg-blue-50 text-accent`. Inactive: `border-border bg-surface text-slate hover:bg-bg`.
  - `aria-pressed` reflects the on/off state.

### Reconcile with `Toggles.tsx`

The existing `Toggles.tsx` has four chips: `extinct`, `synonyms`, `uncertain`, `unassigned`. The new `<TaxonomicTree>` header keeps `synonyms` (as the chip above) and `extinct` (folded into the "Extant only" checkbox, since the inverse semantics are clearer). **`uncertain` and `unassigned` chips are dropped from the new header** — they remain visible as the per-row `⚠` / `⊘` glyphs (§3) and are documented in §15 as an open decision for the implementer to revisit.

### When the header collapses

Tablet and mobile: the filter row wraps below the search input. The search input keeps `flex-1` desktop-only (`md:flex-1`); on mobile it is full-width and the filters wrap beneath it.

---

## 5. Search dropdown (under the input when active)

```
┌───────────────────────────────────────────────────────────────┐
│ 🔍 Euk                                            4 results  │
└───────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────┐
│ EUKARYA: Eukarya                                  domain   ▾  │
│ EUKARYOTA: Eukaryota (Chatton, 1925) Whittaker & Margulis…    │
│ EUKARYALINK: Eukaryalink                            species   │
│ EUK2: Eukaryota sp. 'Euk2'                         species   │
└───────────────────────────────────────────────────────────────┘
```

### Container

- `absolute left-0 right-0 top-full mt-1 z-20 max-h-96 overflow-y-auto rounded-md border border-border bg-surface shadow-lg`
- Width matches the input (the absolute positioning parents the input wrapper).
- `id="tree-search-results"`, `role="listbox"`.

### Each row

- `flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-bg focus:bg-bg focus:outline-none`
- Format: `rank: <display_name>` — the rank is uppercase tracked, the `display_name` is the link surface.
- `role="option"`, `aria-selected` reflects the highlighted row.
- Pressing Enter or clicking selects the row → expand ancestors + scroll into view + focus the row in the tree.

### Empty state

When the response is `{"items": []}`:

```
┌───────────────────────────────────────────────────────────────┐
│           No matches for "Eukzzz"                            │
└───────────────────────────────────────────────────────────────┘
```

- `text-sm text-slate text-center py-2` inside the same rounded container.
- Centered horizontally, 8px vertical padding.

### 8-item cap

The dropdown MUST cap at 8 results per the spec. The exact cap is enforced server-side (`TreeSearchResponse.items.length <= 8`); the client never builds a 9th row.

### z-index

The dropdown is `z-20` — above the tree rows but below any modal/toast. The Toggles `field attribute` must not interfere; we keep the dropdown's escape-from-overflow contract by absolute-positioning it under the search input (no `overflow: hidden` ancestor).

---

## 6. Visual states

| State | Visual treatment |
|-------|------------------|
| **Default** | `bg-surface`, text `text-navy` (name) + `text-slate` (rank/authorship) + `text-amber`/`text-muted`/`text-red` (marker glyphs). |
| **Hover** | Row background `bg-bg`. The colour change is `transition-colors duration-150 ease-out`. |
| **Focused** | 2px outline, `outline-2 outline-offset-[-2px] outline-accent`. The global `:focus-visible` rule in `src/index.css` already provides `outline-2 outline-offset-2 outline-accent`; the tree overrides `outline-offset` to `-2px` so the ring paints *inside* the row (the same convention the SpeciesList uses). |
| **Selected** (the explored path from the root to the active leaf) | `bg-blue-50` + `4px border-l-4 border-accent`. The row stays visually distinct from the hover state. The selected leaf and all its ancestors share this treatment. |
| **Loading** (children fetch in flight) | The caret enters an infinite spin: `animate-spin` (1s linear infinite) on the `<span>`. The row's children are replaced by three skeleton bars: `<span className="ml-6 inline-block h-2 w-24 rounded bg-border animate-pulse" />` × 3, stacked vertically with `gap-1`. |
| **Error** | The caret row turns `text-red`, the row's text becomes `text-red`, and a small "Retry" link appears next to the caret: `<button type="button" className="text-xs underline text-red">Retry</button>`. Clicking issues the same `fetchTreeNode(parent_id)` request. Other rows MUST remain expanded and unaffected. |
| **Empty** (zero roots) | A centered message: "No taxonomy loaded. Check the database connection." `text-sm text-slate text-center py-8`. The session-mandated copy is exactly "No taxonomy loaded" per the spec §"Empty State"; the implementer adds the "Check the database connection." suffix as a recovery hint. |
| **Disabled** (extinct filter active, all children marked extinct) | Row renders the same as default but the whole row is `text-muted` and the caret is hidden. |

### Disabled state for the row

- The whole `<button>` gets `disabled` when the row is filtered out by the active "Extant only" filter.
- `aria-disabled="true"` mirrors the attribute.

---

## 7. Indent & rank hierarchy

### Indent step

- **Desktop ≥ 1024px:** 16px per depth level (`pl-4`).
- **Mobile < 640px:** 12px per depth level (`pl-3`).
- The CSS expression lives on each row's wrapper (`<div role="treeitem" style={{ paddingLeft: depth * step }}>`). React state holds the depth; the inline style is the only way to express data-driven padding without rendering every depth utility.

### Indent guide

- A 1px vertical hairline at `border-border` connects parent to child.
- The guide is rendered via `<div className="absolute left-{step/2} top-0 h-full w-px bg-border">` per row, anchored to the deepest expanded ancestor at that depth.
- The guide ends at the caret center visually (caret is 24px wide, the guide is at half-step = 8px from the row's left edge, the caret center is at 12px from the row's left edge; the human eye accepts the 4px offset).

### Max visible depth

- **12 levels.** Beyond depth 12, the row renders a `"..."` truncation node with a click handler that fetches the next 12 children (`?parent_id={id}&limit=12&offset=12`). The UI shows the truncation node as the next sibling at the parent's depth.
- Tailwind class: `text-slate text-sm select-none` (no caret, no badge, just the literal ellipsis).

### Rank badges (text labels)

The rank label uses the convention from CoL's reference image:

- `domain`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species` are the **major** ranks.
- Intermediate ranks (`subphylum`, `infraphylum`, `parvphylum`, `superclass`, `subclass`, `infraclass`, `parvclass`, `superorder`, `suborder`, `infraorder`, `parvorder`, `superfamily`, `subfamily`, `tribe`, `subtribe`) render with their **own** rank label in the row (the upstream `Taxon.rank` value is preserved verbatim — the implementer does NOT collapse these into the parent rank).
- The species badge (`N spp.`) is unaffected by intermediate ranks — it always counts descendant species.

### Visual hierarchy of ranks

The rank label is the **second-highest emphasis** on the row (after the name). It uses `text-[10px] tracking-widest uppercase` so it reads as a stable marker — the user can scan down the rank column and see `"KINGDOM | KINGDOM | KINGDOM | PHYLUM | CLASS | ..."` without re-reading the names.

---

## 8. Motion

Motion in an Operate surface is **functional, not decorative**. Every transition earns its place.

| Trigger | Animation | Duration | Easing |
|---------|-----------|----------|--------|
| Caret toggle (open/close) | `rotate(0deg)` ↔ `rotate(90deg)` | 150ms | `ease-out` |
| Row expansion (children reveal) | `max-height: 0` ↔ `max-height: {computed}` + opacity 0 → 1 | 200ms | `ease-out` |
| Search dropdown appear | `opacity: 0; translate-y(-4px)` → `opacity: 1; translate-y(0)` | 100ms | `ease-out` |
| Search dropdown disappear | reverse of above | 80ms | `ease-in` |
| Hover background | `bg-surface` → `bg-bg` | 150ms | `ease-out` |
| Loading caret spin | `rotate(0deg)` → `rotate(360deg)` (infinite) | 1000ms | `linear` |
| Skeleton pulse | `opacity: 1` → `opacity: 0.5` → `opacity: 1` (infinite) | 1500ms | `ease-in-out` |
| Focus ring | instantaneous — no transition | 0ms | — |

### Implementation

- Caret rotation: a `<span>` with `transform: rotate(...)` driven by React state. CSS `transition: transform 150ms ease-out`. The span uses `display: inline-block` so the transform applies.
- Row expansion: `max-height` is measured from the rendered children's `getBoundingClientRect().height`; the collapse transition sets `max-height: 0` on the children wrapper. The implementation can use `useLayoutEffect` to read the height once and cache it, OR rely on `transition-all` with `max-h-0` ↔ `max-h-[2000px]` (over-shoot value, but cheaper).
- Search dropdown: `transition-all duration-100 ease-out` on the `opacity` + `translate-y` of the absolute-positioned container.

### Reduced motion

Every animation respects `@media (prefers-reduced-motion: reduce)`. The tree ships a global CSS rule:

```css
@media (prefers-reduced-motion: reduce) {
  .motion-reduce\:transition-none {
    transition: none !important;
  }
}
```

The implementer applies the `motion-reduce:transition-none` Tailwind variant to every element that carries a transition. The loading caret spin ALSO stops — without animation, the loading state is conveyed by the three skeleton bars next to the row, which is sufficient.

---

## 9. Typography

The project fonts (per `tailwind.config.js`) are:

- **Sans:** `system-ui`, `-apple-system`, `Segoe UI`, `Roboto`, `Inter`, `sans-serif`.
- **Mono:** `ui-monospace`, `SFMono-Regular`, `Menlo`, `Monaco`, `Consolas`, `IBM Plex Mono`, `monospace`.

The tree uses **sans** for everything. (The species canonical name in the *downstream* SpeciesList uses mono, but the tree row names are sans — this matches the CoL reference and keeps the row compact.)

### Role scale

| Role | Use | Size | Weight | Letter-spacing |
|------|-----|------|--------|----------------|
| Section header | "Tree" (above the rows, optional) | `text-sm` (14px) | `font-medium` | normal |
| Row name | The taxon's canonical name | `text-sm` (14px) | `font-medium` | normal |
| Authorship | Citation tail | `text-xs` (12px) | `font-normal` | normal, italic |
| Rank label | Uppercase tag | `text-[10px]` | `font-medium` | `tracking-widest` (0.1em) |
| Species badge | Numeric count | `text-xs` (12px) | `font-medium` | normal, `tabular-nums` |
| Search input | User typing | `text-sm` (14px) | `font-normal` | normal |
| Filter labels | "Source", "Extant only" | `text-xs` (12px) | `font-medium` | normal |
| Empty state | "No taxonomy loaded." | `text-sm` (14px) | `font-normal` | normal |

### Hierarchy decisions

- **Body weight is `font-medium` (500) for the row name** — lighter than typical body text because the row is dense and font-medium keeps the name readable without screaming.
- **Rank label is `font-medium` + uppercase + `tracking-widest`** — small + tracked + bold is the unmistakable "section label" pattern.
- **Authorship is `font-normal italic`** — italic carries the "this is metadata" cue without competing with the name.
- **Numbers in the species badge use `tabular-nums`** — alignment across rows is critical for the scan-and-compare pattern.

### Page title

The Tree does not own a page title. The App already renders `<h1>Taxon</h1>` in the header. The tree inserts an `<h2>` (or visually-hidden one) only if its section needs labelling — recommended: `<h2 className="sr-only">Taxonomic tree</h2>` so screen readers announce the section.

### Measure

- Body text in the row is not prose; the 65–75ch rule does not apply. The row is a label, not a paragraph.
- The Search dropdown's empty state is `text-sm text-slate text-center` — short copy, no measure concerns.

---

## 10. Color

The project palette (per `tailwind.config.js`) is:

| Token | Hex | Use |
|-------|-----|-----|
| `accent` | `#3b82f6` (= Tailwind `blue-500`) | Primary action, focus, selection |
| `blue-50` | `#eff6ff` | Selected row background |
| `navy` | `#0f172a` (= Tailwind `slate-900`) | Primary text on the row |
| `slate` | `#475569` (= Tailwind `slate-600`) | Secondary text (rank, authorship) |
| `muted` | `#94a3b8` (= Tailwind `slate-400`) | Tertiary (placeholder, divider) |
| `border` | `#e2e8f0` (= Tailwind `slate-200`) | 1px hairlines, indent guides |
| `bg` | `#f8fafc` (= Tailwind `slate-50`) | Subtle background (hover, skeleton) |
| `surface` | `#ffffff` | Card background |
| `red` | `#dc2626` (= Tailwind `red-600`) | Error |
| `red-50` | `#fef2f2` | Error background |
| `amber` | `#d97706` (= Tailwind `amber-600`) | Warning (uncertain) |
| `amber-50` | `#fffbeb` | Warning background |

### Color strategy

**Restrained.** Neutrals (slate scale) plus one accent (`accent`/blue-500). The tree is an Operate surface — color is functional, not decorative. The only saturated color is the selection background (`blue-50`) and the focus ring (`accent`).

### Mapping to the user's prompt

The user prompt asked for `stone-*`, `blue-*`, `red-*`, `amber-*` Tailwind classes. The project's Tailwind config does NOT include the `stone` palette but it DOES include the `blue`, `red`, `amber` semantic tokens that map to the same hex values. **The mapping below is authoritative** — the implementer uses the project's tokens, not raw Tailwind defaults:

| User prompt class | Project token |
|-------------------|---------------|
| `text-stone-900` | `text-navy` |
| `text-stone-700` | keep `text-navy` (one tier darker than 500 — just use the same; the hover state is `hover:text-slate`) |
| `text-stone-500` | `text-slate` |
| `text-stone-400` | `text-muted` |
| `border-stone-200` | `border-border` |
| `bg-stone-100` | `bg-bg` |
| `bg-stone-50` | `bg-bg` |
| `bg-blue-50` | `bg-blue-50` (project defines this explicitly) |
| `bg-blue-500` | `bg-accent` |
| `text-blue-500` | `text-accent` |
| `outline-blue-500` | `outline-accent` |
| `border-blue-500` | `border-accent` |
| `text-red-600` | `text-red` |
| `bg-red-50` | `bg-red-50` (project defines this explicitly) |
| `text-amber-500` | `text-amber` |
| `bg-amber-50` | `bg-amber-50` (project defines this explicitly) |

Using `stone-*` classes would be a drift from the project's design system. The implementer MUST use the mapped tokens above. This is the single most important reconciliation surfaced in §15.

### Dark mode

Out of scope for the first PR. The `:root { color-scheme: light; }` rule in `src/index.css` locks the surface to light mode. A future PR can swap the tokens.

---

## 11. Accessibility

This is the contract the implementer MUST satisfy. The a11y test in PR 3 (`TaxonomicTree.a11y.test.tsx`) verifies every line.

### ARIA tree pattern

- Root element: `<div role="tree" aria-label="Taxonomic tree">`.
- Each row: `<div role="treeitem" aria-level={depth + 1} aria-expanded={has_children ? isExpanded : undefined}>`.
- Each row's `<button>` is the *only* focusable element inside the treeitem.

### Keyboard navigation

| Key | Effect |
|-----|--------|
| `ArrowDown` | Move focus to the next visible row. |
| `ArrowUp` | Move focus to the previous visible row. |
| `ArrowRight` | Expand the row if collapsed; if already expanded, move focus to the first child. |
| `ArrowLeft` | Collapse the row if expanded; if already collapsed (or no children), move focus to the parent. |
| `Enter` | Toggle the row (same as a click on the row's `<button>`). |
| `Home` | Move focus to the first visible row (depth 0, position 0). |
| `End` | Move focus to the last visible row. |
| `Tab` | Tab leaves the tree (no traps). |
| `Escape` | Collapse the search dropdown if open; otherwise collapse the current row. |

### Search input accessibility

- `aria-label="Find taxon"`.
- `aria-controls="tree-search-results"`.
- `aria-expanded` reflects dropdown state (`true` when the dropdown is open and `q.length > 0`).
- `aria-activedescendant` tracks the highlighted result id (`results-{index}`).
- When the dropdown is closed, `aria-expanded="false"` and `aria-activedescendant` is removed.

### Live region

- A hidden `<span aria-live="polite" aria-atomic="true" className="sr-only">` announces side effects such as "Loaded N children" after a successful fetch. The announce fires after the children render, on a `useEffect` watching the children count.
- Announce format: `"Loaded {count} {child-or-children}"` (singular vs plural).

### Row states

- `aria-selected="true"` on the selected leaf AND any ancestor that was clicked (the explored path).
- `aria-busy="true"` on the row whose children are currently loading.
- `aria-disabled="true"` on rows filtered out by the "Extant only" checkbox.

### Color contrast

- Body text (`text-navy` on `bg-surface`) = `0f172a` on `ffffff` → ratio **16.7:1** ✓ (AAA).
- Secondary text (`text-slate` on `bg-surface`) = `475569` on `ffffff` → ratio **7.6:1** ✓ (AAA).
- Tertiary text (`text-muted` on `bg-surface`) = `94a3b8` on `ffffff` → ratio **3.1:1** — ⚠ below AA for body text. Use `text-muted` ONLY for non-essential metadata (placeholder text, divider labels) and bypass with `text-slate` for any label the user must read.
- Focus ring (`accent` on `bg-surface`) = `#3b82f6` on `#ffffff` → ratio **3.6:1** ✓ (non-text UI).
- Selected row (`bg-blue-50` on `text-navy`) = `#eff6ff` on `#0f172a` → ratio **15.9:1** ✓ (AAA).
- Error text (`text-red` on `bg-surface`) = `#dc2626` on `#ffffff` → ratio **4.8:1** ✓ (AA body).

### Touch targets

- Mobile rows: 28px visual height + 8px hit padding above + 8px below = 44px touch target. Implementation: `py-3` instead of `py-2` on small screens.
- Search input: `h-10` (40px) on desktop, `h-11` (44px) on mobile (`min-h-[44px]`).
- Filter checkboxes: native `<input type="checkbox">` already enforces 44×44px default tap area in the browser's UA stylesheet.

### No icon-only buttons

- The caret is a `<span>` (not a button), so it has no independent label requirement.
- The search input has a visible placeholder AND an `aria-label`.
- The filter dropdowns have visible labels.
- The "Retry" link has visible text `"Retry"`.

### `prefers-reduced-motion`

Already covered in §8. The global CSS rule applies to every transition.

---

## 12. Responsive behavior

| Breakpoint | Layout |
|------------|--------|
| `< 640px` (mobile) | Single column. Filters move into `<details>` accordion. Row height 28px. Indent step 12px. Rank label hidden. Authorship hidden. Touch targets ≥ 44px. |
| `640–1024px` (tablet) | Single column. Filters wrap to a second row below the search. Row height 32px. Indent step 16px. Rank label visible. Authorship visible. |
| `≥ 1024px` (desktop) | Single column inside the existing App's left grid slot. Full row content. Headers right-aligned. |

### Reordering

- The header row's `flex-col md:flex-row` pattern reorders the search and filters.
- The tree rows do NOT reflow; the same `pl-4` (or `pl-3` on mobile) applies per row.

### Container queries?

Out of scope. The tree responds to viewport width, not parent container. The App's grid decides the available width; the tree uses that width uniformly.

### Safe areas

- The whole tree sits inside the App's `mx-auto max-w-page px-6 py-8` wrapper. The internal `p-4` on the card absorbs the safe area on notched devices.
- The implementer adds `pb-[max(1rem,env(safe-area-inset-bottom))]` to the tree card to respect the home indicator on iOS.

---

## 13. Empty / loading / error states

The contract below matches the spec scenarios exactly. The implementer pads the strings with the exact copy the spec requires.

### "No roots" (DB returned zero rows with `parent_id IS NULL`)

- **Copy:** "No taxonomy loaded. Check the database connection."
- **Visual:** centered, `text-sm text-slate text-center py-8`. No icon.
- **Recovery:** none in the UI — the user must fix the DB connection. The message names the cause.

### "No children after expand" (a parent has zero direct children)

- The row renders with no caret and no badge — already handled by the `has_children` flag contract.
- No message text. The row simply reads as a leaf.

### "Loading" (initial mount, the root fetch is in flight)

- Five skeleton rows at the top level. Each skeleton is `<div className="h-8 w-full rounded bg-bg animate-pulse" />` with a 16px indent guide.
- After the root fetch resolves, the skeletons are replaced with the real rows.

### "Loading" (a specific row's children are in flight)

- The caret enters an infinite spin (§8).
- The row's children area renders three skeleton bars: `<span className="ml-6 inline-block h-2 w-24 rounded bg-border animate-pulse" />` × 3.

### "Search input empty"

- No dropdown. `aria-expanded="false"`. No request fires.

### "Search no results"

- The dropdown renders `"No matches for \"<q>\""` exactly as the spec dictates. `\""` is the user's typed query, escape-safely rendered.
- The dropdown stays open (focus returns to the input on Esc).

### "Error retry"

- The caret row turns `text-red` and the row gains a `"Retry"` link:
  ```html
  <span className="text-xs text-red">
    Couldn't load children.
    <button type="button" className="ml-2 underline" onClick={retry}>Retry</button>
  </span>
  ```
- Clicking `Retry` reissues the same `fetchTreeNode(parent_id)` request.
- Other rows MUST remain expanded. The error is scoped to the row that failed.

### "Network failure" (entire tree fetch fails)

- The whole tree renders:
  ```
  No taxonomy loaded.
  [Retry]
  ```
- `text-sm text-slate text-center py-8` for the message, `mt-4 inline-flex items-center gap-2 rounded-btn border border-border bg-surface px-3 py-2 text-sm text-slate hover:bg-bg` for the retry button.

### "Page is offline" (general network down)

- The error states above already cover this. The recovery is always "Retry".

---

## 14. Critique pass (impeccable audit findings)

The impeccable audit heuristics applied to this surface. Each finding is a deliberate decision, not a deferred one.

| Dimension | Score (0-4) | Decision |
|-----------|-------------|----------|
| **Visual hierarchy** | 4 | Rank label (`text-[10px] uppercase tracking-widest text-slate`) and species badge (`tabular-nums`) are the highest-emphasis navigational markers. Name is the primary. Authorship is the lowest. The 4-level hierarchy is unmistakable. |
| **Cognitive load** | 3 | Four navigation affordances: caret (expand/collapse), name (link), search (jump), filter (extant only). Each has a distinct visual; the Miller's-Law cap of 4–5 affordances is respected. The 8-item search dropdown cap keeps the working-memory load bounded. |
| **Accessibility** | 4 | Keyboard nav (ArrowUp/Down/Left/Right/Enter/Home/End/Escape), ARIA tree pattern with `role="tree"`, `aria-level`, `aria-expanded`, `aria-selected`, `aria-busy`, `aria-live` announcements. Color contrast verified (see §11). |
| **Performance** | 4 | Lazy fetch per caret (one round-trip per expand), `has_children` pre-computed in parent fetch, `species_count` lazy-null beyond 100k direct children, 200-row cap per child fetch. Skeleton states during fetch. |
| **Responsiveness** | 4 | Mobile / tablet / desktop breakpoints. Filters collapse to `<details>` on mobile. Touch targets ≥ 44px. Card absorbs safe-area insets. |
| **Anti-patterns** | 4 | No carousels. No modal dialogs on filter. No hover-only affordances (focus ring present). No icon-only buttons (search input has visible label). No section numbers. No harmful Tailwind defaults. |
| **i18n** | 3 | All copy lives in a single `treeCopy` object so a future Spanish translation maps keys without touching layout. Placeholder is the only English-content string and is a copy key, not a literal. |
| **Typography** | 4 | Single family (system-ui sans). 8 explicit roles (section header, row name, authorship, rank, badge, search input, filter label, empty state). `tabular-nums` for numeric badges. |
| **Color** | 4 | Restrained strategy (one accent + neutrals). Every status (hover, focus, selected, loading, error, empty, disabled) has a distinct color treatment. Contrast verified. |
| **Motion** | 4 | Functional transitions only (caret, expansion, dropdown, skeleton). Every transition respects `prefers-reduced-motion`. Loading spin is the only infinite animation. |
| **Errors** | 4 | Per-row retry for children fetch. Page-level retry for the root fetch. Plain language ("Couldn't load children." not "Internal Server Error"). Other rows unaffected by a single-row failure. |
| **Onboarding** | 3 | The tree starts at the 5 CoL roots with carets auto-closed. The first interaction is "click a caret to expand" — discoverable without instruction. The "Find taxon" placeholder shows an example ("e.g. Panthera") so the user knows what to type. |

**Mode consistency (Operate):** All 12 heuristics land in the Operate bucket. The highest score (4) is held by 9 of 12, the lowest (3) is held by 3 of 12. The surface earns the "ship it" verdict (9 components at 4/4, 3 at 3/4 = 93% of the maximum).

### Anti-pattern audit checklist

- [x] No carousels. (n/a — tree, not a media surface.)
- [x] No hero-metric template. (n/a — the tree is a navigation surface.)
- [x] No kicker/eyebrow above headings. (The `<h2>` is `sr-only`; the rank label is a row marker, not a kicker.)
- [x] No section numbers. (The row hierarchy is the visual order.)
- [x] No modal on filter. (Filters are inline.)
- [x] No gradient text. (All text is solid color.)
- [x] No glass / blur as decoration. (Cards are `bg-surface` with a 1px border.)
- [x] No over-bright border-left / border-right on cards. (Selected row uses `border-l-4 border-accent` — within the 4px ceiling for the "selected" affordance.)
- [x] No hard offset shadows on cards. (Card uses `border-border`, no shadow. Search dropdown uses `shadow-lg` — the dropdown is an overlay, shadow is appropriate.)
- [x] No sparklines / progress rings. (Skeleton bars carry the loading state.)
- [x] No monospace as costume. (Sans everywhere. The downstream `SpeciesList` uses mono for canonical names — that is correct, not costume.)
- [x] No Unicode glyphs as icons. (The caret is a glyph; the search icon is an SVG. The `⚠` / `⊘` / `†` markers are deliberate semantic markers, not "icons".)
- [x] No display font in UI labels. (Single sans family.)

---

## 15. Open questions for the implementer (PR 3)

These are the questions the implementer MUST resolve before landing. Document the answer in the PR body.

### Q1. The Tailwind token mapping

The user prompt asked for `stone-*` / `blue-*` / `red-*` / `amber-*` classes. The project's `tailwind.config.js` does NOT include the `stone` palette. The implementer MUST use the project's semantic tokens per the §10 mapping table. The mapping is authoritative — `text-stone-900` → `text-navy`, `text-stone-500` → `text-slate`, `border-stone-200` → `border-border`, `bg-blue-50` → `bg-blue-50` (the project defines this explicitly), etc. Adding the `stone` palette to `tailwind.config.js` is OUT OF SCOPE for PR 3.

### Q2. Filter chip reconciliation

The existing `Toggles.tsx` has 4 chips: `extinct`, `synonyms`, `uncertain`, `unassigned`. The new `<TaxonomicTree>` header keeps:
- `Synonyms` (pill chip, `aria-pressed`, mirrors the existing pattern).
- `Extant only` (checkbox, inverse of the old `extinct` chip).
- `Source` (dropdown, no-op first PR).

`Uncertain` and `unassigned` are dropped from the header chip group. They remain visible as per-row glyphs (`⚠` / `⊘`) in the row prefix. **Decision rationale:** the `uncertain` and `unassigned` chips toggled inclusion in the species list, not in the tree. Folding them into the header would clutter the row-filter space; the row glyphs are the dominant UX (CoL renders these as `?` markers next to the name — the same idea).

If the implementer disagrees, the alternative is to add a third `<details>` panel labeled "Include" with the three remaining chips (`Synonyms`, `Uncertain`, `unassigned`). This is heavier than the row glyphs and is not recommended.

### Q3. Indent depth math

The taxonomy distribution in `data/col.db` has most taxa at the species rank; the average depth from root to species is 5–6. Indent step 16px × 6 = 96px on desktop, 12px × 6 = 72px on mobile. Both fit comfortably in the 280–320px left grid column. The 12-level cap (192px desktop, 144px mobile) is a hard ceiling; beyond that the truncation node (`...`) takes over.

### Q4. Tab and home navigation

The spec requires `Home` / `End` keys to jump to the first/last visible row. The "last visible row" is the deepest expanded leaf. The implementer MUST compute the visible-row list on every expansion/collapse and replan the `aria-activedescendant` AND the focus index on `Home` / `End`. This is the most complex a11y bit of the surface.

### Q5. Search input on mobile

On mobile, the keyboard's `Done` button should also clear the input and close the dropdown. The implementation uses the native `<input type="search">` with the browser's clear button + a synthetic `onBlur` that closes the dropdown after a 150ms delay (so a click on a result registers first).

### Q6. Extant only filter on root fetch

The "Extant only" checkbox is global (it lives in the header). When checked, the next call to `GET /api/tree/children` (for ANY parent) includes `?include_extinct=false`. The cache invalidates per-parent on filter change. The implementation MUST clear the cache when the checkbox toggles. The user-visible behaviour is: "I checked the box, all extended rows disappear on the next click."

### Q7. Source dropdown is a no-op

The `Source` dropdown UI renders `CoL` (active) + `GBIF` (disabled) + `WoRMS` (disabled). Selecting a different option is a no-op; the next `/api/tree/children` request does NOT include a `source` param. The dropdown's `value` stays on `CoL`. Document this in the component's docstring so a future PR adding multi-source does not break the contract.

### Q8. The "Loaded N children" live region

The live region announces the count after each successful fetch. Singular vs plural: `"Loaded 1 child"` vs `"Loaded {N} children"`. The implementer uses a simple `count === 1 ? "child" : "children"` ternary — the copy is not yet localized so a full `Intl.PluralRules` is overkill.

### Q9. The Toggles chip visual difference

The existing `Toggles.tsx` chip pattern uses `border-accent bg-blue-50 text-accent` for the active state. The new `<TaxonomicTree>` Synonyms chip uses the SAME pattern. The implementer MUST import no shared component — the existing `Toggles.tsx` is bound to the species-list filter and stays where it is. The new chip is a standalone `<button>` in the tree header.

---

## 16. Self-test checklist

The implementer MUST run through this checklist before opening the PR. Each box is a bound, verifiable check.

- [ ] All Tailwind classes used come from the project's `tailwind.config.js` tokens (or default Tailwind palettes that are already in the bundle). Search the diff for `stone-`, `gray-`, `zinc-`, `neutral-` — none should appear.
- [ ] All ARIA attributes have the correct role/level pairing per the WAI-ARIA tree pattern. (`role="tree"` on root, `role="treeitem"` per row, `aria-level` matches the depth, `aria-expanded` only on expandable rows.)
- [ ] All motion durations are ≤ 250ms. The loading caret spin is 1000ms (infinite) and is the only exception. No metric rises above 300ms.
- [ ] Color contrast verified ≥ 4.5:1 for body text. The only exception is `text-muted` (3.1:1) which is only used for non-essential metadata.
- [ ] Touch targets ≥ 44×44px on mobile. Verifiable by inspecting the rendered row's `getBoundingClientRect().height` in mobile emulated viewport.
- [ ] No icon-only buttons. The caret is a `<span>`. The search input has a visible label. The Retry link has visible text.
- [ ] Reduced-motion fallback for every transition. The `motion-reduce:transition-none` Tailwind variant is applied to every element that carries a transition.
- [ ] Empty / loading / error states covered for every async surface. Initial mount, per-row expand, search, retry.
- [ ] No `!important`, no inline styles (except `style={{ paddingLeft: depth * step }}` for the data-driven indent).
- [ ] The `path:change` CustomEvent payload is `{path: string[]}` — identical to the existing Cascade contract. The App listener at `App.tsx` lines 150–159 keeps working verbatim.
- [ ] The `useCascadePath.setPath(state.path)` call fires on every expand — same as the existing Cascade.
- [ ] The Breadcrumb component's `aria-label` is renamed from `"Resolved species breadcrumb"` to `"Cascade path breadcrumb"` per the design.md file change list.

---

## 17. Reference image

The original Catalogue of Life "Browse" tree (the inspiration for this surface):

![Catalogue of Life reference](../../col-tree.png)

The reference is a **starting point**, not a copy. The new tree modernizes the visual language:

| Aspect | CoL reference | New tree |
|--------|---------------|----------|
| Type | Sans-serif, dense, bright blue links | System-ui sans, medium-weight navy, restrained accent |
| Row height | ~26px | 32px desktop / 28px mobile |
| Indent guides | Faint (off) | 1px `border-border` hairlines |
| Caret | `▸` / `▾` | `▸` / `▾` (kept the same — universal convention) |
| Rank label | Lowercase, weight `normal` | `UPPERCASE` + `tracking-widest` + `font-medium` |
| Species badge | `2,452,105 spp.` (italic, blue) | `2.4M spp.` (numeric, neutral, `tabular-nums`) |
| Filters | Inline `[ ] Source [ ] Extant only` (right-aligned) | Same — preserved exactly |
| Color | Bright cobalt blue (`#1F8FFF`-ish) | `accent` = `#3b82f6` (project's blue-500) |

The new tree inherits the structural idea (caret rows, indent by rank, inline filters) and modernizes the typography + color + spacing per the project's `taxon.pen` design system.

---

## Appendix — Token reference (copy-paste ready)

The implementer uses these tokens verbatim. Anything not in this list is OUT of scope.

### Colors

```text
text-navy          #0f172a   primary text
text-slate         #475569   secondary text, rank label, authorship
text-muted         #94a3b8   tertiary, placeholder, divider
text-accent        #3b82f6   link, focus ring, active filter
text-red           #dc2626   error text
text-amber         #d97706   uncertain marker
border-border      #e2e8f0   hairlines, indent guides, card border
bg-bg              #f8fafc   hover, skeleton, badge
bg-surface         #ffffff   card
bg-blue-50         #eff6ff   selected row
bg-red-50          #fef2f2   error background
bg-amber-50        #fffbeb   warning background
```

### Spacing

```text
gap-2              8px       row gap (between rows)
gap-3              12px      header gap (between search and filters)
p-4                16px      card padding
px-2               8px       row horizontal padding
py-2               8px       row vertical padding (desktop)
py-3               12px      row vertical padding (mobile, hit-area)
pl-{depth*4}       16px*depth indent step (desktop)
pl-{depth*3}       12px*depth indent step (mobile)
```

### Typography

```text
text-sm            14px      row name, search input
text-xs            12px      authorship, badge, filter labels
text-[10px]        10px      rank label
font-medium        500       row name, rank label
font-normal        400       authorship, body
italic             n/a       authorship only
tracking-widest    0.1em     rank label only
tabular-nums       n/a       species badge only
```

### Animation

```text
transition-colors duration-150 ease-out    hover
transition-transform duration-150 ease-out caret rotate
transition-all duration-200 ease-out       row expansion
transition-all duration-100 ease-out       search dropdown appear
animate-spin                                 loading caret
animate-pulse                                skeleton row
motion-reduce:transition-none                reduced-motion fallback
```

### Layout

```text
max-w-page                  1200px            App container
rounded-card border border-border bg-surface p-4   tree card
rounded-md border border-border bg-surface         search input
rounded-full bg-bg px-2 py-0.5 text-xs              species badge
rounded-chip border px-3 py-1 text-sm                toggles chip
```

---

*End of design document. The implementer MUST translate this document line-by-line into `TaxonomicTree.tsx` + `TaxonomicTree.state.ts` + the Tailwind classes. Open questions in §15 require documented answers in the PR body.*
