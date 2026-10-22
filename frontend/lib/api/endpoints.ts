/**
 * Every call the app makes, one function each, typed from the contract. Screens import these and
 * nothing else; no screen builds a URL or reads a raw response.
 */
import { api } from "./client";
import {
  activitySchema,
  agentRequestSchema,
  demoResetSchema,
  jsonObjectSchema,
  passkeySchema,
  readbackSchema,
  requestSchema,
  sessionSchema,
  timelineSchema,
} from "./schemas";

type Opts = { signal?: AbortSignal };

/** The languages a readback can be asked for. Yoruba, Hausa and Igbo come back in English (with
 * `fallback_from` set) when their exact recording does not exist; anything else is a 422. */
export type ReadbackLang = "en" | "pcm" | "yo" | "ha" | "ig";

// ── Session (demo only: the backend has mock login, no real OTP yet) ─────────────────────────
export const mockLogin = (phone: string, otp: string) =>
  api("/auth/mock-login", sessionSchema, { body: { phone, otp } });

/** Customer-only, so the answer tells us who is signed in: 200 customer, 403 agent, 401 nobody. */
export const getActivity = (o: Opts = {}) => api("/me/activity", activitySchema, o);

// ── Agent ────────────────────────────────────────────────────────────────────────────────────
/** `idempotencyKey` is made once per tap, so a retry after a dropped connection cannot double-create. */
export const createAgentRequest = (amountKobo: number, idempotencyKey: string, o: Opts = {}) =>
  api("/agent/requests", agentRequestSchema, {
    ...o,
    body: { amount_kobo: amountKobo },
    headers: { "Idempotency-Key": idempotencyKey },
  });

// ── Requests ─────────────────────────────────────────────────────────────────────────────────
export const claimByCode = (claimCode: string) =>
  api("/requests/claim", requestSchema, { body: { claim_code: claimCode } });
export const claimByQr = (qrPayload: string) =>
  api("/requests/claim", requestSchema, { body: { qr_payload: qrPayload } });

export const getRequest = (id: string, o: Opts = {}) =>
  api(`/requests/${encodeURIComponent(id)}`, requestSchema, o);

/** Moves the request to READ_BACK on the server, so it is called once per visit to the screen. */
export const getReadback = (id: string, lang: ReadbackLang, o: Opts = {}) =>
  api(`/requests/${encodeURIComponent(id)}/readback`, readbackSchema, { ...o, query: { lang } });

export const getChallenge = (id: string) =>
  api(`/requests/${encodeURIComponent(id)}/challenge`, jsonObjectSchema, { method: "POST" });

/** The body IS the browser's PublicKeyCredential JSON, unwrapped. */
export const approve = (id: string, assertion: Record<string, unknown>) =>
  api(`/requests/${encodeURIComponent(id)}/approve`, requestSchema, { body: assertion });

export const decline = (id: string) =>
  api(`/requests/${encodeURIComponent(id)}/decline`, requestSchema, { method: "POST" });

// ── Passkeys ─────────────────────────────────────────────────────────────────────────────────
export const getRegisterOptions = () =>
  api("/passkeys/register/options", jsonObjectSchema, { method: "POST" });
export const verifyRegistration = (credential: Record<string, unknown>, deviceLabel?: string) =>
  api("/passkeys/register/verify", passkeySchema, {
    body: { credential, ...(deviceLabel ? { device_label: deviceLabel } : {}) },
  });

// ── Demo console: needs the operator's X-Demo-Token, typed in by the operator, never bundled ──
const demo = (token: string) => ({ "x-demo-token": token });
export const demoReset = (token: string) =>
  api("/demo/reset", demoResetSchema, { method: "POST", headers: demo(token) });
export const demoTamper = (token: string, id: string, amountKobo?: number) =>
  api(`/demo/requests/${encodeURIComponent(id)}/tamper`, requestSchema, {
    headers: demo(token),
    body: amountKobo === undefined ? {} : { amount_kobo: amountKobo },
  });
export const demoReplay = (token: string, id: string) =>
  api(`/demo/requests/${encodeURIComponent(id)}/replay`, requestSchema, {
    method: "POST",
    headers: demo(token),
  });
export const demoExpire = (token: string, id: string) =>
  api(`/demo/requests/${encodeURIComponent(id)}/expire`, requestSchema, {
    method: "POST",
    headers: demo(token),
  });
export const demoTimeline = (token: string, id: string, o: Opts = {}) =>
  api(`/demo/requests/${encodeURIComponent(id)}/timeline`, timelineSchema, {
    ...o,
    headers: demo(token),
  });
