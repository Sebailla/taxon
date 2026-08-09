# AGENTS.md — Project Rules

This file overrides `~/.config/opencode/AGENTS.md` wherever they differ. Anything not covered here is inherited from the global.

---

## 1. Spanish mirror for documentation and artifacts

**Rule**: every artifact created in this project must have a Spanish mirror. An "artifact" is any file that fits one of the categories below.

**Categories that require a mirror:**

- Documentation (READMEs, guides, onboarding, runbooks).
- Architecture decisions and ADRs.
- Specifications (technical specs, API contracts, data models).
- Proposals and PRDs.
- OpenSpec artifacts (`openspec/changes/*`, `openspec/specs/*`, proposals, designs, tasks, specs, verification reports, archive reports).
- Test plans and test reports.
- Changelogs and release notes.

**Categories that do NOT require a mirror:**

- Project config files (`opencode.json`, `.gitignore`, `package.json`, lockfiles, CI configs).
- Source code (any language).
- Build outputs and generated files.
- Binary assets (images, fonts, compiled assets).
- Anything consumed by a machine rather than read by a human.

**Mirror rules:**

- Mirrors live in the `/documents-es` folder at the **project root** (lowercase, not `Documents-es` — case-sensitive on GitHub/Linux).
- The mirror is created **at the same time** as the original. Not as a follow-up.
- The mirror file keeps the same name as the original, adding the `-es` suffix before the extension when it adds clarity (e.g. `architecture.md` → `architecture-es.md`).
- The content is a **faithful translation** into neutral/professional Spanish. It is not rewritten or reinterpreted.
- Recommended structure inside `/documents-es`:
  - `/documents-es/architecture/` for architecture decisions
  - `/documents-es/specs/` for specifications
  - `/documents-es/proposals/` for proposals
  - `/documents-es/adr/` for Architecture Decision Records
  - `/documents-es/openspec/` for OpenSpec artifacts
  - If no category fits, it goes at the root of `/documents-es`.

When in doubt, apply the test: if a human reads it to understand the project, it goes to `/documents-es`. If a machine reads it to run, build, or parse it, it does not.

---

## 2. Learning notebook `/learn-es`

**Rule**: every time something is implemented, it gets documented in `/learn-es` (project root, lowercase).

### When to update

- **One entry per feature or closed PR**, not per individual commit.
- Written **after the PR is merged into `develop` with green CI** and **before** cleaning up the worktree.
- File naming: `/learn-es/YYYY-MM-DD-short-feature-name.md`
  - Example: `/learn-es/2026-08-08-autonomous-scientific-search.md`

### Required structure of each entry

Each learning file must have these sections in this order:

1. **What**: one or two sentences describing what was implemented.
2. **How**: the technical approach used (language, libraries, patterns, commands).
3. **Where**: main files and paths affected. Format `path/to/file` — short description.
4. **Why**: motivation, problem solved, decision taken.
5. **How it works**: how the feature operates in production or normal use. Concrete steps.
6. **Workflows**: workflows the feature touches or enables (CI, deploy, branching, tests).

If a section does not apply, omit it. Do not fill it with empty text.

### Proactive suggestions

The agent **must suggest** a candidate `/learn-es` entry when it observes something worth learning, even if the user did not ask. The valid triggers are:

- A non-obvious bug, gotcha, or edge case discovered.
- A pattern or convention established in the project.
- A trade-off or decision made and the reasoning behind it.
- A failure mode that would have been hard to recover from without context.

The suggestion is a conversational offer, not an automatic write. The user decides whether to commit it.

**Triggers that do NOT count** (do not suggest for these):

- Use of a standard library API or well-known syntax.
- Trivial refactors or mechanical renaming.
- Decisions already documented elsewhere in the repo.
- Anything that would not save a future agent time.

When in doubt, do not suggest. It is better to under-suggest than to spam.

### Language

Neutral/professional Spanish throughout. No voseo, no slang, no CAPS for emphasis.

---

## 3. Required gentle-ai skills

**Rule**: the following operations are always performed via the skills registered in `.atl/skill-registry.md`. Never by hand.

- **Conventional commits** — `type(scope): description` in imperative present.
  - Valid types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`.
  - Valid examples: `feat(api): add user endpoint`, `fix(auth): handle expired token`, `docs: update readme`.
  - Message in English. If the change is Spanish-only documentation, use `docs(es): ...`.
  - No "Co-Authored-By" or AI attribution in the commit body.
- **PRs** — opened via the `branch-pr` skill. Issue-first checks, honest body, clear scope.
- **Chained PRs / large slices (>400 lines)** — planned via the `chained-pr` skill. If `sdd-tasks` forecast shows risk, split before apply.
- **Worktrees** — when working on a feature, use a worktree. The `work-unit-commits` skill guides commit planning as reviewable units.
- **Branching and merging** — follow the rules in section 4 (`develop` branch).

If a skill is unavailable or does not apply to the specific case, document the reason in the PR body.

---

## 4. Branch and worktree policy

### Inviolable rule: `main` is production

- **`main` is production. Never commit directly to it. Never merge anything into `main` that has not passed through `develop` and green CI.**
- All integration happens in `develop`.

### Mandatory workflow

1. **Integration base**: `develop`.
2. **For each feature / fix / change**:
   - Create a worktree from `develop` with a descriptive name: `../<repo>-worktrees/<feature-name>`.
   - Work inside the worktree, not in the main checkout.
   - Commits follow conventional commits (see section 3).
   - Open the PR against `develop` (never against `main`).
3. **After the merge**:
   - Wait for CI to pass green.
   - If CI fails: the worktree is **kept alive**. The fix is made on the same branch as the PR, pushed, and CI is retried until it passes green. Only after green does the flow continue.
   - Once CI is green: create the corresponding `/learn-es` entry (see section 2).
   - Clean up the worktree (delete the folder and the local worktree branch).
4. **Release / production**:
   - When a set of features in `develop` is ready for production, open a `develop` → `main` PR following the same PR + CI flow.
   - That PR is the only legitimate way to touch `main`.

### If unsure which branch to use

**Stop and ask before any merge or new branch.** This rule admits no silent exceptions.

---

## 5. UI design workflow

**Rule**: any UI design work is performed **first** in Pencil MCP and audited under the `impeccable` skill before any implementation in code.

- Open or update the `.pen` file via the Pencil MCP tools (`get_app_state`, `execute`, `get_screenshot`, `export_nodes`, `export_html`).
- Run an `impeccable` review pass on the design to validate hierarchy, accessibility, typography, color, motion, and anti-patterns.
- Only after the design is reviewed and approved is it allowed to translate the design into code.
- `.pen` files are encrypted: only access them through Pencil MCP tools. Never with `Read` or `Grep`.

---

## 6. Inheritance from the global `AGENTS.md`

Anything not covered here is inherited from `~/.config/opencode/AGENTS.md`. When a local rule and a global rule conflict, **the local one wins**.

Global rules that apply and are preserved:

- Senior Architect persona (tone, language, emphasis).
- Engram: proactive persistent memory, `mem_save` after decisions/bugfixes, `mem_session_summary` on close.
- CodeGraph: for structural questions, `codegraph_explore` before broad Read/Grep.
- SDD workflow: if invoked, preflight, init guard, and attempt authority still apply.
- RDD kill switch: user-owned, never reactivated without explicit request.
- Bash: use `workdir`, not `cd ... && ...`. Glob/Grep/Read instead of find/grep/cat.
- Commits: no "Co-Authored-By" or AI attribution.
