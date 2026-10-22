/**
 * The backend's data shapes, named. Everything here is derived from `schema.d.ts`, which is
 * generated from backend/openapi.json (`pnpm gen:api`), so a backend change surfaces as a type
 * error here instead of a bug on a customer's phone.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type RequestOut = Schemas["RequestOut"];
export type RequestState = RequestOut["state"];
export type AgentRequestOut = Schemas["AgentRequestOut"];
export type ReadbackOut = Schemas["ReadbackOut"];
export type ActivityOut = Schemas["ActivityOut"];
export type ActivityItemOut = Schemas["ActivityItemOut"];
export type SessionOut = Schemas["SessionOut"];
export type PasskeyOut = Schemas["PasskeyOut"];
export type TimelineOut = Schemas["TimelineOut"];
export type TimelineEventOut = Schemas["TimelineEventOut"];
export type Problem = Schemas["Problem"];
export type ErrorCode = Schemas["ErrorCode"];

/** States a request can be in, as the API names them. */
export const REQUEST_STATES = [
  "CREATED",
  "READ_BACK",
  "APPROVED",
  "SUBMITTED",
  "SETTLED",
  "DECLINED",
  "EXPIRED",
  "FAILED",
] as const satisfies readonly RequestState[];
