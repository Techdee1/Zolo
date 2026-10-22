/**
 * The landing page photos and screenshots: where they are, their real pixel size (so the layout
 * never shifts), and what is in them, written as a description of the scene, not as a claim.
 * A test checks the sizes against the files themselves.
 */
export type LandingImage = { name: string; src: string; width: number; height: number };

export const LANDING_IMAGES = {
  hero: { name: "hero", src: "/landing/hero.jpg", width: 409, height: 123 },
  counter: { name: "counter", src: "/landing/agent-counter.jpg", width: 678, height: 452 },
  hands: { name: "hands", src: "/landing/hands-phone.jpg", width: 616, height: 498 },
  street: { name: "street", src: "/landing/street.jpg", width: 638, height: 480 },
  shotAgent: { name: "shotAgent", src: "/landing/shot-agent-code.png", width: 780, height: 1688 },
  shotReview: { name: "shotReview", src: "/landing/shot-review.png", width: 780, height: 1688 },
  shotPaid: { name: "shotPaid", src: "/landing/shot-paid.png", width: 780, height: 1688 },
} as const satisfies Record<string, LandingImage>;
