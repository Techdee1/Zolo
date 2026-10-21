## What and why

<!-- One or two sentences. Title format: `feat(scope): ...`, `fix: ...`, `a11y: ...` -->

## Frontend checklist

- [ ] Screenshots attached, **light and dark**
- [ ] **TalkBack checked** (yes / no): ______  (required for any change to a P0 screen)
- [ ] **Reduced motion checked** (`prefers-reduced-motion`): yes / no
- [ ] Keyboard-only run-through of the screen I changed
- [ ] axe reports zero violations on every P0 route (`pnpm e2e`)
- [ ] No amounts, names or account numbers in logs, URLs or analytics
- [ ] Money is integer kobo end to end (no floats)

## Backend

- [ ] Backend change? `backend/openapi.json` regenerated and the frontend types updated
