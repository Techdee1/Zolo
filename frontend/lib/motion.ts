/**
 * Spring settings, mirrored from styles/tokens.css (a unit test fails if they drift).
 *
 * Springs are described the way Apple does: a damping ratio (1.0 = critically damped, no
 * overshoot; lower bounces) and a response time in seconds. `response` is NOT a duration: a spring
 * has no fixed duration, it settles. Default to damping 1.0; add bounce only for gestures that
 * carried momentum (a flick), which nothing here does yet.
 */
export const SPRING = {
  /** Move, reposition, appear. */
  default: { damping: 1, response: 0.4 },
  /** Sheets and drawers. */
  sheet: { damping: 0.8, response: 0.3 },
} as const;

export const PRESS_SCALE = 0.97;

/** Reduced motion: a quick fade, never a slide, a spring or a shake. */
export const FADE_SECONDS = 0.15;

/**
 * Convert Apple's (damping ratio, response) into the stiffness, damping and mass that `motion`
 * (Framer Motion) takes. With mass 1: response = 2π/ω₀ and ω₀ = √stiffness, so
 * stiffness = (2π/response)², and damping = 2·ratio·√stiffness.
 */
export function toSpring({ damping, response }: { damping: number; response: number }) {
  const stiffness = (2 * Math.PI) ** 2 / response ** 2;
  return {
    type: "spring" as const,
    stiffness,
    damping: 2 * damping * Math.sqrt(stiffness),
    mass: 1,
  };
}
