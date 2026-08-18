/** ExplorerPanel — renders the embedded iframe for the currently-active
search source.

The panel is bound to the workspace store's ``activeLink`` record. The
empty state ("Pick a source to embed") is rendered when no active link
is set; otherwise an ``<iframe>`` is rendered with the pinned sandbox
attribute set the spec mandates. If the iframe fires its native
``error`` event (the common case for sources that refuse embedding
via ``X-Frame-Options`` or CSP — Wikipedia, Scholar, BHL), the panel
hides the iframe and renders a fallback card with an obvious
``<a target="_blank" rel="noopener noreferrer">Open in new tab</a>``
so popup-blocker state does not affect reach.

The mobile peek-card (data-testid ``explorer-peek``) co-exists with
the iframe below the 640px breakpoint so the active link's source
name + an "Open in new tab" anchor are always reachable when the
column collapses.
*/

import { useEffect, useRef, useState } from "react";

import { useWorkspace } from "../store/workspace";
import { decodeSpeciesKey } from "../store/speciesKey";

const IFRAME_SANDBOX =
  "allow-same-origin allow-scripts allow-forms allow-popups allow-downloads";

/** Tailwind's ``sm`` breakpoint is 640px (per the v3.4 default). The
 *  collapse happens below that, so the test wired to the
 *  ``explorer-peek`` data-testid queries ``max-width: 639px`` to
 *  mirror the CSS ``sm:hidden`` behavior. */
const MOBILE_QUERY = "(max-width: 639px)";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    return window.matchMedia(query).matches;
  });
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent): void => setMatches(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [query]);
  return matches;
}

export function ExplorerPanel(): JSX.Element {
  const activeLink = useWorkspace((state) => state.activeLink);
  const [loadFailed, setLoadFailed] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const isMobile = useMediaQuery(MOBILE_QUERY);

  // Wire the iframe error event via raw ``addEventListener`` rather
  // than the React synthetic ``onError`` prop. React's synthetic
  // event delegation on iframe is unreliable for the ``error``
  // event in many browsers (the spec says the listener attaches at
  // the raw iframe element, not the synthetic dispatch root); using
  // the native listener matches what real browsers do anyway.
  useEffect(() => {
    const el = iframeRef.current;
    if (el === null) return;
    const handler = (): void => setLoadFailed(true);
    el.addEventListener("error", handler);
    return () => el.removeEventListener("error", handler);
  }, [activeLink?.url]);

  if (activeLink === null) {
    return (
      <section
        aria-label="Explorer panel"
        className="rounded-card border border-border bg-surface p-4"
      >
        <p className="text-sm text-slate">Pick a source to embed.</p>
      </section>
    );
  }

  const { genus, epithet } = decodeSpeciesKey(activeLink.speciesKey);
  const label = `Embedded search result for ${genus} ${epithet} (${activeLink.source})`;

  return (
    <section
      aria-label="Explorer panel"
      className="rounded-card border border-border bg-surface p-4"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="rounded-btn border border-border bg-surface px-2 py-0.5 text-xs text-navy">
          {activeLink.source}
        </span>
      </div>
      <div aria-live="polite" className="sr-only">
        {loadFailed ? `${activeLink.source} could not be embedded.` : `Loading ${activeLink.source}.`}
      </div>
      {isMobile ? (
        <div
          data-testid="explorer-peek"
          className="rounded-btn border border-border bg-surface p-3"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm text-navy">{activeLink.source}</span>
            <a
              href={activeLink.url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 rounded-btn border border-border bg-surface px-2 py-1 text-xs text-navy hover:underline"
            >
              Open in new tab
            </a>
          </div>
        </div>
      ) : null}
      <iframe
        ref={iframeRef}
        title={label}
        aria-label={label}
        src={activeLink.url}
        sandbox={IFRAME_SANDBOX}
        className="h-96 w-full rounded-btn border border-border"
        style={loadFailed ? { display: "none" } : undefined}
      />
      {loadFailed ? (
        <div
          data-testid="explorer-fallback"
          className="rounded-btn border border-border bg-surface p-4"
        >
          <p className="text-sm text-navy">
            <span className="font-medium">{activeLink.source}</span> — this
            source refuses embedding.
          </p>
          <a
            href={activeLink.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block rounded-btn border border-border bg-surface px-3 py-1 text-sm text-navy hover:underline"
          >
            Open in new tab
          </a>
        </div>
      ) : null}
    </section>
  );
}
