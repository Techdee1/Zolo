import { WebAuthnError } from "@simplewebauthn/browser";
import { describe, expect, it } from "vitest";
import { classifyPasskeyError } from "@/lib/passkeys";

/** The browser has many ways to say "no"; the screens only need to tell four apart. */
const webauthn = (code: string, cause?: Error) =>
  new WebAuthnError({ message: "x", code: code as never, cause: cause ?? new Error("x") });

describe("classifyPasskeyError", () => {
  it("cancelling or failing the fingerprint, face or lock prompt is 'cancelled'", () => {
    expect(classifyPasskeyError(Object.assign(new Error("x"), { name: "NotAllowedError" }))).toBe(
      "cancelled",
    );
    expect(classifyPasskeyError(webauthn("ERROR_CEREMONY_ABORTED"))).toBe("cancelled");
    expect(
      classifyPasskeyError(
        webauthn(
          "ERROR_PASSTHROUGH_SEE_CAUSE_PROPERTY",
          Object.assign(new Error("x"), { name: "NotAllowedError" }),
        ),
      ),
    ).toBe("cancelled");
  });

  it("a phone that already has the passkey is 'already'", () => {
    expect(classifyPasskeyError(webauthn("ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED"))).toBe(
      "already",
    );
    expect(classifyPasskeyError(Object.assign(new Error("x"), { name: "InvalidStateError" }))).toBe(
      "already",
    );
  });

  it("an authenticator that cannot do this is 'unsupported'", () => {
    expect(
      classifyPasskeyError(webauthn("ERROR_AUTHENTICATOR_NO_SUPPORTED_PUBKEYCREDPARAMS_ALG")),
    ).toBe("unsupported");
  });

  it("anything else, including a plain string, is 'other' and never crashes", () => {
    expect(classifyPasskeyError(new Error("boom"))).toBe("other");
    expect(classifyPasskeyError("nope")).toBe("other");
    expect(classifyPasskeyError(undefined)).toBe("other");
  });
});
