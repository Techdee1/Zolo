# Contributing

## Setup

See the [README](README.md#run-it-locally). You need Docker (Postgres), `uv`, and Node 24 with pnpm.

## Before you open a pull request

1. `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
2. `cd frontend && pnpm check` (types, lint, format, unit tests). For UI changes also
   `pnpm build:e2e && pnpm e2e`.
3. If you changed an API response or request, regenerate the contract and the types:
   `cd backend && uv run python -m zolo.api.export_openapi > openapi.json && cd ../frontend && pnpm gen:api`.
4. If the frontend now differs from a PRD, add a row to [`docs/PRD_DEVIATIONS.md`](docs/PRD_DEVIATIONS.md).

## Rules that are not negotiable

- **Accessibility:** WCAG 2.2 AA, axe with zero violations in light, dark and reduced motion, 48px targets, no
  custom PIN pad, never ask for a PIN or card number.
- **Money is integer kobo.** No floats.
- **Only the consent module changes request state or calls the bank.**
- **No secrets in the repository.** `.env` files are gitignored; examples contain no values.
- **Write the test with the change** and, for security-critical code, break the behaviour once to see the
  test fail.

## Commits and pull requests

Conventional commits: `feat(scope): ...`, `fix: ...`, `docs: ...`, `test: ...`, plus `a11y: ...`. The PR title is
checked in CI. Use the pull request template (screenshots in light and dark, reduced motion checked).
