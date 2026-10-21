/**
 * Runtime checks for everything the API sends back. The generated types (`schema.d.ts`) say what
 * the backend promises; these say what actually arrived. A response that does not match is
 * refused (ContractError) instead of being shown: the screen that states an amount must never
 * render a malformed one.
 *
 * `Same<>` assertions at the bottom fail the type-check if a schema here drifts from the generated
 * types, in either direction.
 */
import { z } from "zod";
import { REQUEST_STATES } from "./types";
import type {
  ActivityOut,
  AgentRequestOut,
  Problem,
  PasskeyOut,
  ReadbackOut,
  RequestOut,
  SessionOut,
  TimelineOut,
} from "./types";
import type { components } from "./schema";

/** Money is integer kobo. A float, a string or an unsafe integer is a contract error. */
const kobo = z.number().int().safe().nonnegative();
const id = z.string().min(1);
const timestamp = z.string().min(1);

export const errorCodeSchema = z.enum([
  "LIMIT_EXCEEDED",
  "CODE_NOT_FOUND",
  "REQUEST_EXPIRED",
  "STATE_CONFLICT",
  "INTENT_CHANGED",
  "SIGNATURE_INVALID",
  "ALREADY_USED",
  "UNAUTHENTICATED",
  "FORBIDDEN",
  "NOT_FOUND",
  "VALIDATION_ERROR",
  "RATE_LIMITED",
  "NAME_ENQUIRY_FAILED",
  "NO_PASSKEY",
  "PASSKEY_REGISTRATION_FAILED",
  "CHALLENGE_NOT_FOUND",
  "RISK_BLOCKED",
  "BANK_REJECTED",
  "INTERNAL_ERROR",
]);

export const problemSchema = z.object({
  type: z.string(),
  title: z.string(),
  status: z.number().int(),
  code: errorCodeSchema,
  detail: z.string(),
});

export const requestStateSchema = z.enum(REQUEST_STATES);

export const requestSchema = z.object({
  id,
  state: requestStateSchema,
  amount_kobo: kobo,
  payee_name: z.string(),
  expires_at: timestamp,
  claimed: z.boolean(),
  bank_reference: z.string().nullish(),
  failure_reason: z.string().nullish(),
});

export const agentRequestSchema = z.object({
  id,
  claim_code: z.string().nullable(),
  qr_payload: z.string(),
  expires_at: timestamp,
  payee_name: z.string(),
});

export const readbackSchema = z.object({
  text: z.string().min(1),
  lang: z.enum(["en", "pcm"]),
  amount_words: z.string().min(1),
  payee_name: z.string(),
  amount_kobo: kobo,
  expires_at: timestamp,
  audio_url: z.string().nullish(),
});

export const sessionSchema = z.object({
  role: z.enum(["customer", "agent"]),
  id,
  display_name: z.string(),
});

export const activitySchema = z.object({
  items: z.array(
    z.object({
      id,
      state: z.string(),
      amount_kobo: kobo,
      payee_name: z.string(),
      created_at: timestamp,
      line: z.string(),
    }),
  ),
});

export const passkeySchema = z.object({
  id,
  device_label: z.string().nullable(),
  replaced_previous: z.boolean(),
});

export const timelineSchema = z.object({
  request: requestSchema,
  events: z.array(
    z.object({
      id: z.number().int(),
      at: timestamp,
      event: z.string(),
      actor: z.string(),
      details: z.record(z.string(), z.unknown()),
    }),
  ),
});

export const demoResetSchema = z.object({
  customers: z.number().int(),
  agents: z.number().int(),
  accounts: z.number().int(),
  recipients: z.number().int(),
});

/** WebAuthn option and credential objects are handed to the browser as they are. */
export const jsonObjectSchema = z.record(z.string(), z.unknown());

// ── Drift alarms: these fail `pnpm typecheck` if a schema and the generated type disagree ──────
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
type Assert<T extends true> = T;
export type _Drift = [
  Assert<Same<z.infer<typeof problemSchema>, Problem>>,
  Assert<Same<z.infer<typeof requestSchema>, RequestOut>>,
  Assert<Same<z.infer<typeof agentRequestSchema>, AgentRequestOut>>,
  Assert<Same<z.infer<typeof readbackSchema>, ReadbackOut>>,
  Assert<Same<z.infer<typeof sessionSchema>, SessionOut>>,
  Assert<Same<z.infer<typeof activitySchema>, ActivityOut>>,
  Assert<Same<z.infer<typeof passkeySchema>, PasskeyOut>>,
  Assert<Same<z.infer<typeof timelineSchema>, TimelineOut>>,
  Assert<Same<z.infer<typeof demoResetSchema>, components["schemas"]["DemoResetOut"]>>,
];
