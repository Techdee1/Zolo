/**
 * What the screens remember between pages, kept in this tab only (sessionStorage), never in
 * localStorage and never secret. The session itself is an HttpOnly cookie that scripts cannot see;
 * this is only "who did I sign in as" for greeting text, and the agent's claim code, which the API
 * returns once at creation and never again.
 */
import { z } from "zod";

const hint = z.object({ role: z.enum(["customer", "agent"]), name: z.string() });
export type SessionHint = z.infer<typeof hint>;

const agentRequest = z.object({
  id: z.string(),
  claim_code: z.string().nullable(),
  qr_payload: z.string(),
  expires_at: z.string(),
  payee_name: z.string(),
});
export type StoredAgentRequest = z.infer<typeof agentRequest>;

function read<T>(key: string, schema: z.ZodType<T>): T | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    const parsed = schema.safeParse(raw ? JSON.parse(raw) : null);
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
function write(key: string, value: unknown) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode or storage off: the screens work without it.
  }
}

export const getSessionHint = () => read("zolo.session", hint);
export const setSessionHint = (value: SessionHint) => write("zolo.session", value);

export const getAgentRequest = (id: string) => {
  const stored = read(`zolo.agent-request.${id}`, agentRequest);
  return stored?.id === id ? stored : null;
};
export const setAgentRequest = (value: StoredAgentRequest) => {
  write(`zolo.agent-request.${value.id}`, value);
  setLastRequestId(value.id);
};

/** The demo console prefills with the request you touched last. */
export const getLastRequestId = () => read("zolo.last-request", z.string());
export const setLastRequestId = (id: string) => write("zolo.last-request", id);

/** Only ever follow a path on this site, so a crafted `?next=` cannot send anyone elsewhere. */
export function safeNext(next: string | undefined, fallback = "/"): string {
  return next && /^\/(?!\/)[\w\-/.?=&%]*$/.test(next) ? next : fallback;
}
