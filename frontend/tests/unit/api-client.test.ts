import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  approve,
  claimByCode,
  createAgentRequest,
  getActivity,
  getReadback,
  getRequest,
  mockLogin,
} from "@/lib/api/endpoints";
import { ApiError, ContractError, NetworkError, isApiError } from "@/lib/api/client";
import { agentRequestSchema, readbackSchema, requestSchema } from "@/lib/api/schemas";
import { installFakeBackend } from "./fake-server";

const fake = installFakeBackend();

describe("the API client against the fake backend", () => {
  it("logs in, and a customer's activity is readable", async () => {
    const session = await mockLogin("+2348011111111", "123456");
    expect(session).toMatchObject({ role: "customer", display_name: "Amaka Obi" });
    fake.actAs("customer");
    expect(await getActivity()).toEqual({ items: [] });
  });

  it("turns a problem+json response into an ApiError with the machine code", async () => {
    await expect(mockLogin("+2348011111111", "000000")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      code: "UNAUTHENTICATED",
    });
    fake.actAs("agent");
    const err = await getActivity().catch((e: unknown) => e);
    expect(isApiError(err, "FORBIDDEN")).toBe(true);
    expect((err as ApiError).status).toBe(403);
  });

  it("sends the idempotency key, and the same key does not make a second request", async () => {
    fake.actAs("agent");
    const a = await createAgentRequest(1_500_000, "key-1");
    const b = await createAgentRequest(1_500_000, "key-1");
    const c = await createAgentRequest(1_500_000, "key-2");
    expect(b.id).toBe(a.id);
    expect(c.id).not.toBe(a.id);
    expect(a.claim_code).toMatch(/^\d{4}$/);
  });

  it("asks for the readback language in the query string", async () => {
    fake.actAs("agent");
    const made = await createAgentRequest(1_500_000, "k");
    fake.actAs("customer");
    await claimByCode(made.claim_code!);
    const en = await getReadback(made.id, "en");
    expect(en).toMatchObject({
      lang: "en",
      amount_kobo: 1_500_000,
      amount_words: "fifteen thousand naira",
    });
    expect((await getRequest(made.id)).state).toBe("READ_BACK");
  });

  it("refuses a response that is not the promised shape, instead of showing it", async () => {
    const server = setupServer(
      http.get("*/api/requests/x", () =>
        HttpResponse.json({
          id: "x",
          state: "SETTLED",
          amount_kobo: 15000.5,
          payee_name: "B",
          expires_at: "t",
          claimed: true,
        }),
      ),
      http.get("*/api/requests/y", () =>
        HttpResponse.json({
          id: "y",
          state: "PAID",
          amount_kobo: 1,
          payee_name: "B",
          expires_at: "t",
          claimed: true,
        }),
      ),
      http.get("*/api/requests/z", () => HttpResponse.error()),
      http.post("*/api/requests/claim", () =>
        HttpResponse.text("<html>bad gateway</html>", { status: 502 }),
      ),
    );
    server.listen({ onUnhandledFrame: "error" });
    try {
      await expect(getRequest("x")).rejects.toBeInstanceOf(ContractError); // a float amount
      await expect(getRequest("y")).rejects.toBeInstanceOf(ContractError); // an unknown state
      await expect(getRequest("z")).rejects.toBeInstanceOf(NetworkError);
      await expect(claimByCode("1234")).rejects.toMatchObject({
        status: 502,
        code: "INTERNAL_ERROR",
      });
    } finally {
      server.close();
    }
  });

  it("posts the assertion as the whole body, with no wrapper", async () => {
    let seen: unknown;
    const server = setupServer(
      http.post("*/api/requests/abc/approve", async ({ request }) => {
        seen = await request.json();
        return HttpResponse.json({
          id: "abc",
          state: "SUBMITTED",
          amount_kobo: 1,
          payee_name: "B",
          expires_at: "t",
          claimed: true,
        });
      }),
    );
    server.listen({ onUnhandledFrame: "error" });
    try {
      const out = await approve("abc", { id: "cred", response: { signature: "s" } });
      expect(seen).toEqual({ id: "cred", response: { signature: "s" } });
      expect(out.state).toBe("SUBMITTED");
    } finally {
      server.close();
    }
  });
});

describe("response schemas", () => {
  const req = {
    id: "1",
    state: "READ_BACK",
    amount_kobo: 100,
    payee_name: "B",
    expires_at: "t",
    claimed: true,
  };
  it("accept the real shape, with the optional fields absent or null", () => {
    expect(requestSchema.safeParse(req).success).toBe(true);
    expect(
      requestSchema.safeParse({ ...req, bank_reference: null, failure_reason: null }).success,
    ).toBe(true);
  });
  it("never accept money that is a float, a string, negative or unsafe", () => {
    for (const bad of [1.5, "100", -1, Number.MAX_SAFE_INTEGER + 1, null, NaN]) {
      expect(requestSchema.safeParse({ ...req, amount_kobo: bad }).success, String(bad)).toBe(
        false,
      );
    }
  });
  it("accept only the readback languages the backend speaks", () => {
    const rb = {
      text: "t",
      lang: "en",
      amount_words: "w",
      payee_name: "B",
      amount_kobo: 1,
      expires_at: "t",
    };
    expect(readbackSchema.safeParse(rb).success).toBe(true);
    expect(readbackSchema.safeParse({ ...rb, lang: "yo" }).success).toBe(false);
  });
  it("accept a claim code that may be null", () => {
    const a = { id: "1", qr_payload: "q", expires_at: "t", payee_name: "B" };
    expect(agentRequestSchema.safeParse({ ...a, claim_code: null }).success).toBe(true);
    expect(agentRequestSchema.safeParse(a).success).toBe(false);
  });
});
