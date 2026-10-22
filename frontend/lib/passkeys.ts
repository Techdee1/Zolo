/**
 * The browser's passkey prompts, behind two functions so screens never touch WebAuthn directly.
 * The challenge for approval is the request's intent hash (set by the backend), so a passkey
 * signature is bound to exactly the amount and payee that were read back.
 */
import {
  browserSupportsWebAuthn,
  platformAuthenticatorIsAvailable,
  startAuthentication,
  startRegistration,
  WebAuthnError,
} from "@simplewebauthn/browser";

export type PasskeyFailure = "cancelled" | "already" | "unsupported" | "other";

/** Sorts the browser's many WebAuthn errors into the few our screens say something specific about. */
export function classifyPasskeyError(e: unknown): PasskeyFailure {
  const name = e instanceof WebAuthnError ? (e.cause as Error | undefined)?.name : undefined;
  const code = e instanceof WebAuthnError ? e.code : undefined;
  const plain = e instanceof Error ? e.name : undefined;
  if (
    code === "ERROR_CEREMONY_ABORTED" ||
    name === "NotAllowedError" ||
    plain === "NotAllowedError"
  )
    return "cancelled";
  if (
    code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED" ||
    name === "InvalidStateError" ||
    plain === "InvalidStateError"
  )
    return "already";
  if (code?.startsWith("ERROR_AUTHENTICATOR_")) return "unsupported";
  return "other";
}

export async function passkeySupport(): Promise<"ok" | "unsupported" | "no-lock"> {
  if (!browserSupportsWebAuthn()) return "unsupported";
  return (await platformAuthenticatorIsAvailable()) ? "ok" : "no-lock";
}

export const createPasskey = (options: Record<string, unknown>) =>
  startRegistration({ optionsJSON: options as never }) as Promise<unknown> as Promise<
    Record<string, unknown>
  >;

export const signWithPasskey = (options: Record<string, unknown>) =>
  startAuthentication({ optionsJSON: options as never }) as Promise<unknown> as Promise<
    Record<string, unknown>
  >;
