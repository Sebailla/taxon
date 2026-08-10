# Integración Continua

Este proyecto ejecuta un único workflow de GitHub Actions en
`.github/workflows/ci.yml`. La primera corrida exitosa se incorporó con
el archivo en `develop` (commit `6844345`).

## Qué cubre

Un único job `backend` se ejecuta en cada push a `develop` y en cada
pull request contra `develop`, sobre una matrix de Python `3.11` /
`3.12` (`fail-fast: false` para que ambas versiones se reporten por
separado). El job corre:

| Paso | Comando | Propósito |
| --- | --- | --- |
| ruff check | `ruff check .` | Linting |
| ruff format | `ruff format --check .` | Cumplimiento de formato |
| mypy | `mypy taxon/` | Verificación estática de tipos |
| pytest | `pytest taxon/tests/ -v` | Tests unitarios + integración |

Pip se cachea entre corridas con clave basada en `pyproject.toml`. La
concurrencia cancela corridas en curso del mismo ref, de modo que un
push nuevo a un PR no desperdicia minutos de CI.

## Qué NO cubre todavía

El workflow está intencionalmente acotado a la base del backend.
Crecerá a medida que lleguen los PRs siguientes:

- **Frontend** (vitest, eslint, vite build) — se agrega con el PR 3,
  cuando se sume el proyecto React/Vite/Tailwind.
- **Release gate hacia `main`** — los PRs `develop` → `main` se hacen
  en forma manual según `AGENTS.md` §4, así que no hay workflow de
  auto-deploy.
- **Validación de PR** (`status:approved`, link a issue, labels
  `type:*`) — el repo todavía no tiene los labels custom
  configurados. Cuando se agreguen, un workflow separado `pr-validation`
  debe gatear los PRs antes de que corra el CI de backend.

## Recomendación de branch protection

Para que el CI sea realmente una compuerta, activar protección de
rama en `develop` con:

- "Require status checks to pass before merging" → seleccionar
  `backend (python 3.11)` y `backend (python 3.12)`.
- "Require pull request reviews before merging" → 1 revisor mínimo.
- "Do not allow bypassing the above settings".

`main` debe quedar sin protección para los PRs manuales de release
`develop` → `main`.

## Paridad local

Correr los mismos chequeos localmente antes de pushear:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy taxon/
.venv/bin/pytest taxon/tests/ -v
```

Si los cuatro pasan en local, el CI va a pasar en `develop`.
