import { describe, expect, expectTypeOf, it } from "vitest";
import {
  REQUEST_STATES,
  type AgentRequestOut,
  type ErrorCode,
  type ReadbackOut,
  type RequestOut,
  type RequestState,
} from "@/lib/api/types";

// These are COMPILE-TIME checks (run by `pnpm typecheck`). If the backend adds, renames or
// removes something the frontend relies on, typecheck fails until the frontend is updated.
describe("the backend contract, as the frontend sees it", () => {
  it("knows every request state, and a new backend state breaks the build", () => {
    expectTypeOf<RequestState>().toEqualTypeOf<
      | "CREATED"
      | "READ_BACK"
      | "APPROVED"
      | "SUBMITTED"
      | "SETTLED"
      | "DECLINED"
      | "EXPIRED"
      | "FAILED"
    >();
    expect(new Set(REQUEST_STATES).size).toBe(8);
  });

  it("money is an integer number of kobo, carried as a number (never a string or float type)", () => {
    expectTypeOf<RequestOut["amount_kobo"]>().toEqualTypeOf<number>();
    expectTypeOf<ReadbackOut["amount_kobo"]>().toEqualTypeOf<number>();
  });

  it("a new request carries exactly what the agent screen needs", () => {
    expectTypeOf<keyof AgentRequestOut>().toEqualTypeOf<
      "id" | "claim_code" | "qr_payload" | "expires_at" | "payee_name"
    >();
  });

  it("readback languages are only the ones the backend can voice", () => {
    expectTypeOf<ReadbackOut["lang"]>().toEqualTypeOf<"en" | "pcm">();
  });

  it("the error codes the screens handle exist in the contract", () => {
    expectTypeOf<
      | "INTENT_CHANGED"
      | "ALREADY_USED"
      | "REQUEST_EXPIRED"
      | "CODE_NOT_FOUND"
      | "STATE_CONFLICT"
      | "SIGNATURE_INVALID"
      | "LIMIT_EXCEEDED"
    >().toExtend<ErrorCode>();
  });
});
