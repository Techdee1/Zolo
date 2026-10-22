/**
 * Focus moves to the h1 when the route CHANGES, not when the page first loads: on a fresh load the
 * browser starts at the top, the first Tab reaches the "Skip to main content" link, and a screen
 * reader reads the page title. Moving focus there too would skip the skip link.
 */
const state = { initial: true };

/** True exactly once per page load (the first heading to mount). */
export function takeInitialLoad(): boolean {
  const was = state.initial;
  state.initial = false;
  return was;
}

/** For tests, which simulate client-side navigation. */
export function markNavigated(): void {
  state.initial = false;
}
