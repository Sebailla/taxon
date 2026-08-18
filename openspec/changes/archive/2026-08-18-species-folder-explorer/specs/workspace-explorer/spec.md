# Spec: workspace-explorer

## Purpose

The `workspace-explorer` capability renders an embedded iframe for the currently-active search source so the user can read each result without leaving the SPA context. The iframe is bound to an `activeLink` record held by the `workspaceStore` Zustand store; the `activeLink` is set when the user clicks a `SpeciesLinks` cell (keeping the existing `target="_blank"` open-in-new-tab behaviour). The iframe carries a deliberate sandbox attribute set and a graceful-degradation fallback card for sources that refuse embedding (X-Frame-Options / CSP rejections are common for Wikipedia, Scholar, BHL). Closes sub-feature D of issue #68.

## Requirements

### Requirement: Iframe Sandbox Attributes Match the Working Set

The system MUST render an `<iframe>` whose `sandbox` attribute is exactly `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads`. The attribute MUST NOT include `allow-top-navigation` (iframe must not navigate the SPA) and MUST NOT include `allow-modals`. The `src` MUST equal the active link's URL when an active link is set, and MUST be empty (or unrendered) when no active link is set.

#### Scenario: Iframe sandbox matches the exact attribute set

- GIVEN the `activeLink` is `{species: "Panthera tigris", source: "Wikipedia", url: "..."}`
- WHEN the `<ExplorerPanel>` mounts
- THEN the rendered `<iframe>` has `sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`
- AND the iframe's `src` equals the active link's URL
- AND the iframe has no `allow-top-navigation` flag

#### Scenario: No active link shows empty state

- GIVEN no `activeLink` is set in the store
- WHEN the `<ExplorerPanel>` mounts
- THEN the panel renders a placeholder ("Pick a source to embed")
- AND no iframe is rendered (or the iframe has empty `src` with a placeholder overlay)

### Requirement: Active Link State Resolves on Species-Link Click

The system MUST update `workspaceStore.activeLink` when the user clicks a `SpeciesLinks` cell whose link belongs to a species. The active link MUST be `{speciesId, source, url}` where `url` is the substituted URL. The click handler MUST keep the existing `target="_blank"` anchor behaviour — clicking opens a new tab AND populates the iframe.

#### Scenario: Species-link click populates active link

- GIVEN the species-links panel renders a `Wikipedia` cell for `Panthera tigris`
- WHEN the user clicks the cell
- THEN `useWorkspace.getState().activeLink` equals `{speciesId: <id>, source: "Wikipedia", url: "<substituted URL>"}`
- AND the browser opens a new tab via `target="_blank"`
- AND the iframe src updates to the same URL

### Requirement: Per-Taxon Breadcrumb-Links Panel Does NOT Activate Iframe

The system MUST NOT set `activeLink` from the per-taxon breadcrumb-links panel (the `taxon-links` endpoint for breadcrumb segments, no epithet). The breadcrumb-links panel keeps its existing `target="_blank"` behaviour but does not populate the explorer panel; the iframe stays in its previous state or the empty state.

#### Scenario: Breadcrumb-link click does not populate active link

- GIVEN the breadcrumb-links panel renders a `Wikipedia` cell for `Animalia`
- WHEN the user clicks the cell
- THEN `useWorkspace.getState().activeLink` is unchanged (or remains null)
- AND the browser opens a new tab via `target="_blank"`
- AND the iframe state is unchanged

### Requirement: X-Frame-Options / CSP Rejection Shows Fallback Card

The system MUST render a fallback card in place of the iframe when the active source refuses embedding. The fallback MUST be triggered by the iframe's `onError` event and MUST render: the source name, a one-line message explaining the source refuses embedding, and an obvious `<a href={url} target="_blank" rel="noopener noreferrer">Open in new tab</a>` button. The fallback `<a>` MUST be a regular anchor rendered outside the iframe so popup-blocker state does not affect reach.

#### Scenario: Source rejects embedding shows fallback

- GIVEN the `activeLink` is `Wikipedia` for `Panthera tigris`
- WHEN the iframe fires `onError` (because `en.wikipedia.org` sends `X-Frame-Options: SAMEORIGIN`)
- THEN the placeholder card replaces the iframe
- AND the card shows "Wikipedia — this source refuses embedding"
- AND the card contains an `<a target="_blank" rel="noopener noreferrer" href={url}>Open in new tab</a>` button
- AND the button is reachable with keyboard focus (axe-core: 0 violations)

#### Scenario: Fallback is never hidden

- GIVEN the fallback card is rendered
- WHEN the user inspects the panel
- THEN the "Open in new tab" button is visible (opacity ≥ 1, no `display: none`, no `visibility: hidden`)
- AND the button is the first tab stop inside the card

### Requirement: Aria Label Names the Embedded Source

The system MUST set `aria-label="Embedded search result for {genus} {epithet} ({source})"` on the iframe so screen readers announce the embedded context. The label MUST update when the active link changes.

#### Scenario: Aria label updates on active link change

- GIVEN the `activeLink` is `Wikipedia` for `Panthera tigris`
- WHEN the `<ExplorerPanel>` renders
- THEN the iframe has `aria-label="Embedded search result for Panthera tigris (Wikipedia)"`

#### Scenario: Aria label swaps on source change

- GIVEN the `activeLink` is `Wikipedia` for `Panthera tigris`
- WHEN the user clicks a `Google` link for the same species
- THEN the iframe's `aria-label` updates to `"Embedded search result for Panthera tigris (Google)"`
- AND the iframe's `src` updates to the `Google` URL

### Requirement: Mounts in Right Column Below Breadcrumb / Species Links

The system MUST mount `<ExplorerPanel>` inside `App.tsx`'s right column, below the `<SpeciesLinks>` and `<Breadcrumb>` blocks. The panel MUST be `sticky top-0` so it stays visible while the user scrolls the dispatch grid. The mounting MUST NOT move the existing `<Breadcrumb>` / `<SpeciesLinks>` rendering.

#### Scenario: Panel renders below species links

- GIVEN the user resolves a species
- WHEN the SPA mounts
- THEN the right column shows `<Breadcrumb>` at the top, `<SpeciesLinks>` below it, `<ExplorerPanel>` below the links
- AND the panel has `class="sticky top-0"`

## Out of Scope

- Persistent iframe state across SPA reloads — active link is session-scoped; reloading the SPA starts the empty state until the user clicks a link.
- Cross-origin drag-and-drop interception — the iframe's default browser download flow handles `Content-Disposition: attachment`; the SPA does not intercept downloads.
- Auto-marking a source visited when the user clicks the link inside the iframe — the click handler explicitly toggles via `link-visited`; auto-detect is a separate slice.
- Custom iframe sizing presets per source — the iframe uses a single responsive height; per-source presets defer to a follow-up.
- Recording embedded-page scroll position or form state — the iframe is stateless from the SPA's perspective.
- Mobile-specific iframe UX (Safari ITP, requestDesktopWebsite) — falls under the desktop-browser scope of the existing SPA.
