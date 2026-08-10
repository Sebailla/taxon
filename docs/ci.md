# Continuous Integration

This project runs a single GitHub Actions workflow at
`.github/workflows/ci.yml`. The first successful run landed with the
addition of this file on `develop` (commit `6844345`).

## What it covers

A single `backend` job runs on every push to `develop` and every pull
request against `develop`, on a Python `3.11` / `3.12` matrix
(`fail-fast: false` so both surface independently). The job executes:

| Step | Command | Purpose |
| --- | --- | --- |
| ruff check | `ruff check .` | Linting |
| ruff format | `ruff format --check .` | Format compliance |
| mypy | `mypy taxon/` | Static type checking |
| pytest | `pytest taxon/tests/ -v` | Unit + integration tests |

Pip is cached across runs keyed on `pyproject.toml`. Concurrency
cancels in-progress runs on the same ref so a new push to a PR does
not waste CI minutes.

## What it does NOT cover yet

The workflow is intentionally scoped to the backend foundation. It
will grow as later PRs land:

- **Frontend** (vitest, eslint, vite build) — lands with PR 3 when the
  React/Vite/Tailwind project is added.
- **Release gate to `main`** — `develop` → `main` PRs stay manual per
  `AGENTS.md` §4, so no auto-deploy workflow exists.
- **PR validation** (`status:approved`, issue linkage, `type:*` labels)
  — the repo does not yet have the custom labels configured. Once
  they are added, a separate `pr-validation` workflow should gate
  PRs before the backend CI runs.

## Branch protection recommendation

To make CI the gate it is meant to be, enable branch protection on
`develop` with:

- "Require status checks to pass before merging" → select `backend (python 3.11)` and `backend (python 3.12)`.
- "Require pull request reviews before merging" → 1 reviewer minimum.
- "Do not allow bypassing the above settings".

`main` should remain unprotected for the manual `develop` → `main`
release PRs.

## Local parity

Run the same checks locally before pushing:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy taxon/
.venv/bin/pytest taxon/tests/ -v
```

If all four pass locally, the CI will pass on `develop` too.
