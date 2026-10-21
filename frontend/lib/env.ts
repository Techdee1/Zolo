import { z } from "zod";

/**
 * Public, build-time settings. Only NEXT_PUBLIC_* values exist in the browser, so there is
 * nothing secret here by construction: keys, tokens and sessions never live in the client.
 * Values are read literally (process.env.NEXT_PUBLIC_X) so Next can inline them.
 */
const flag = z
  .enum(["true", "false"])
  .default("false")
  .transform((v) => v === "true");

/** Every API call goes to this path on our own origin; Next proxies it to the backend. */
export const API_BASE = "/api";

const schema = z.object({
  featureDemo: flag,
  featureCardGuard: flag,
  featureKitchenSink: flag,
  useMocks: flag,
});

export type Env = z.infer<typeof schema>;

export function parseEnv(raw: Record<string, string | undefined>): Env {
  return schema.parse({
    featureDemo: raw.NEXT_PUBLIC_FEATURE_DEMO || undefined,
    featureCardGuard: raw.NEXT_PUBLIC_FEATURE_CARD_GUARD || undefined,
    featureKitchenSink: raw.NEXT_PUBLIC_FEATURE_KITCHEN_SINK || undefined,
    useMocks: raw.NEXT_PUBLIC_USE_MOCKS || undefined,
  });
}

export const env: Env = parseEnv({
  NEXT_PUBLIC_FEATURE_DEMO: process.env.NEXT_PUBLIC_FEATURE_DEMO,
  NEXT_PUBLIC_FEATURE_CARD_GUARD: process.env.NEXT_PUBLIC_FEATURE_CARD_GUARD,
  NEXT_PUBLIC_FEATURE_KITCHEN_SINK: process.env.NEXT_PUBLIC_FEATURE_KITCHEN_SINK,
  NEXT_PUBLIC_USE_MOCKS: process.env.NEXT_PUBLIC_USE_MOCKS,
});
