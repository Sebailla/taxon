# Lighthouse CI a11y setup (PR #21)

## What

Added Lighthouse CI as the third CI job for `taxon`. The
`lighthouse` job installs Chrome stable, builds `frontend/dist`,
and runs `lhci autorun` with one assertion:
`categories:accessibility >= 0.95`. Combined with the axe-core
regression tests in PR #20, the project now has two independent
a11y safety nets: axe-core runs against the rendered React tree in
jsdom, and Lighthouse runs against the actual built bundle served
by Chrome headless. Verified locally and on the CI runner:
a11y score is 1.0.

## How

### 1. Dep + npm scripts

`frontend/package.json`:

- `@lhci/cli@^0.14.0` added to `devDependencies`.
- `npm run lhci` wraps the `@lhci/cli` binary for direct use.
- `npm run lhci:autorun` runs `npm run build && lhci autorun` so
  the production bundle exists before LHCI starts collecting.

`CHROME_PATH` is intentionally NOT hardcoded in the npm scripts.
On CI it is set explicitly in the workflow step; on local dev it
is set in the developer's shell or `.env.local`. Hardcoding it
would break whichever platform does not have the path the script
expects.

### 2. lhci config (`frontend/.lighthouserc.json`)

- `staticDistDir: "./dist"` — LHCI spins up its own static
  server. Simpler than running a custom server and sufficient for
  the a11y audit.
- `numberOfRuns: 1` — a11y score is deterministic enough that one
  run is enough.
- `settings.preset: "desktop"` — matches the a11y audit the
  team uses locally.
- `skipAudits` — drop SEO + crawlability + bf-cache + structured
  data audits that do not apply to a single-page app without a
  marketing surface.
- `chromeFlags` — `--no-sandbox --headless=new --disable-gpu
  --disable-dev-shm-usage` for GitHub Actions Ubuntu runners.
- `assertions.categories:accessibility` — error severity, min
  score 0.95. One assertion is enough for this PR.
- `upload.target: temporary-public-storage` — report URL is
  printed in the GitHub Actions log without needing a separate
  LHCI server.

### 3. CI job (`.github/workflows/ci.yml`)

New `lighthouse` job runs in parallel with backend + frontend
(no `needs:` dependency because `lhci:autorun` rebuilds
internally). Steps:

1. Checkout.
2. Setup Node 20 with npm cache (`frontend/package-lock.json`).
3. `npm ci` in `frontend/`.
4. `browser-actions/setup-chrome@v2` with `chrome-version: stable`.
5. `npm run build` in `frontend/`.
6. `npm run lhci:autorun` in `frontend/` with `CHROME_PATH:
   /usr/bin/google-chrome`.

### 4. Gitignore hygiene

- `.gitignore` (root): `.lighthouseci/` — LHCI's report output
  directory.
- `frontend/.gitignore`: `*.tsbuildinfo` — incremental build
  cache files emitted by `tsc -b` that were polluting `git
  status` after every `npm run build` since PR #20 was merged.

## Where

- `.github/workflows/ci.yml` — new `lighthouse` job.
- `frontend/.lighthouserc.json` — LHCI configuration.
- `frontend/package.json` — `@lhci/cli` dep + `lhci` /
  `lhci:autorun` scripts.
- `frontend/package-lock.json` — lockfile update.
- `frontend/.gitignore` — ignore `*.tsbuildinfo`.
- `.gitignore` — ignore `.lighthouseci/`.

## Why

The hand-rolled a11y audit (`docs/audits/lighthouse-a11y.md`,
36/40 score) and the axe-core regression tests (PR #20) are
strong contracts, but neither runs against the production
bundle. Lighthouse CI closes that gap by auditing the actual
`vite build` output through Chrome headless, which catches
issues that only manifest in the built artefact (e.g. SVG
attributes stripped by the bundler, font loading failures,
hydration mismatches). The 0.95 assertion gives the team a
hard floor: any PR that drops the production-bundle a11y score
below 0.95 fails CI.

Combined with PR #20 the project now has overlapping coverage
that catches different failure modes — axe-core in jsdom
catches contract-level issues at unit-test speed, LHCI catches
build-environment issues at CI speed. The two verdicts are
expected to agree within ±2 points on any healthy PR, per the
issue #19 acceptance criteria.

## How it works

On every push to a PR targeting `develop`, GitHub Actions runs
four jobs in parallel:

- `backend (python 3.11)` — pytest + ruff + mypy.
- `backend (python 3.12)` — same matrix partner.
- `frontend (node 20)` — typecheck + Vitest + ESLint + vite
  build + upload `frontend/dist/` artifact.
- `lighthouse (a11y)` — installs Chrome stable, rebuilds the
  bundle (idempotent), runs `lhci autorun`. On success the LHCI
  upload step prints a `storage.googleapis.com/lighthouse-infrastructure.appspot.com`
  URL with the full report (Lighthouse's built-in axe-core
  rules, all category scores, and the assertion results).

If the a11y score drops below 0.95 the `lhci autorun` step exits
non-zero and the job fails, blocking merge. The report URL is
still available from the failed run's logs for triage.

## Workflows

- **CI** — three parallel jobs (backend matrix 3.11/3.12,
  frontend, lighthouse). The lighthouse job is the only one that
  touches Chrome; the existing jobs keep their Node 20 + Python
  matrix as-is.
- **Reviews** — small PR (~6 files, +3584 / -34 lines; most of
  the diff is `package-lock.json`). Four `work-unit-commits`
  slices (gitignore, dep + scripts, lhci config, CI job) keep
  the review surface tight.
- **Local developer workflow** — `cd frontend && npm ci &&
  CHROME_PATH=/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome
  npm run lhci:autorun` reproduces the CI audit on macOS.
  Report HTML opens at the end of the run.

## Lessons learned

- **`staticDistDir` and `startServerCommand` are mutually
  exclusive in LHCI's config.** When `staticDistDir` is set,
  LHCI ignores `startServerCommand` and runs its own server.
  The initial draft of this PR had both, plus a stub server
  and a Puppeteer hydration script. Pulling them out cut ~120
  lines of code with zero a11y coverage loss.
- **`@lhci/cli@0.14` does not autodetect Chrome on macOS.** The
  healthcheck reports "Chrome installation not found" even when
  Chrome is at the standard
  `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
  path. Setting `CHROME_PATH` explicitly fixes it. On the CI
  runner `browser-actions/setup-chrome` installs Chrome at
  `/usr/bin/google-chrome`, which is what the workflow uses.
- **`numberOfRuns: 1` is enough for a11y.** Lighthouse's a11y
  category uses deterministic axe-core rules; the score does
  not vary across runs. Bumping to 3 runs would triple the job
  duration (~3 min) for no signal.
- **`errors-in-console` is not a useful a11y assertion in this
  setup.** The static server returns 404 for `/api/kingdoms`,
  which logs a console error on every run. Adding that
  assertion would fail the job for environmental reasons.
  Revisit if/when the stub server is wired up.

## Out of scope (deliberate)

- **Stub server / Puppeteer hydration script.** Originally
  drafted as `scripts/lhci_stub_server.py` and
  `scripts/lhci_puppeteer.cjs`, then pulled before commit.
  See PR #21 body for the full reasoning. Preserved in the
  branch history if a future PR wants `errors-in-console` or
  `categories:best-practices` assertions.
- **`categories:best-practices` assertion.** Same reason.
- **`categories:performance` and `categories:seo` assertions.**
  The team has not yet audited the SPA's performance budget or
  SEO surface. Out of scope for this PR; revisit when those
  become product requirements.
- **`LHCI server` mode** (per-project reports dashboard).
  `temporary-public-storage` is enough for now.
