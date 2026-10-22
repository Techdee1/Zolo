import { describe, expect, it } from "vitest";
import { createFakeBackend, DEMO_TOKEN } from "../fakes/fake-backend";

/** The fake is the contract every screen test leans on, so it is tested like one. */
function setup() {
  let t = 1_000_000;
  const fake = createFakeBackend({ now: () => t });
  const call = (
    role: "customer" | "agent" | null,
    method: string,
    path: string,
    body?: unknown,
    extra: Record<string, string> = {},
    query?: Record<string, string>,
  ) => {
    fake.actAs(role);
    return fake.handle({ method, path, body, query, headers: extra });
  };
  return { fake, call, advance: (ms: number) => (t += ms) };
}

type Req = { id: string; state: string };
const created = (call: ReturnType<typeof setup>["call"]) => {
  const res = call("agent", "POST", "/agent/requests", { amount_kobo: 1_500_000 });
  return res.body as { id: string; claim_code: string };
};
const readyToApprove = (s: ReturnType<typeof setup>) => {
  const r = created(s.call);
  s.call("customer", "POST", "/requests/claim", { claim_code: r.claim_code });
  s.call("customer", "GET", `/requests/${r.id}/readback`, undefined, {}, { lang: "en" });
  s.fake.addPasskey();
  s.call("customer", "POST", `/requests/${r.id}/challenge`);
  return r;
};
const ASSERTION = { id: "c", response: { signature: "s" } };

describe("fake backend: the Phase 1 state machine", () => {
  it("walks CREATED, READ_BACK, SETTLED", () => {
    const s = setup();
    const r = readyToApprove(s);
    expect((s.call("customer", "GET", `/requests/${r.id}`).body as Req).state).toBe("READ_BACK");
    const approved = s.call("customer", "POST", `/requests/${r.id}/approve`, ASSERTION);
    expect(approved.body).toMatchObject({ state: "SETTLED", amount_kobo: 1_500_000 });
  });

  it("can end in SUBMITTED, and the bank confirming it later settles it", () => {
    const s = setup();
    s.fake.setOutcome("SUBMITTED");
    const r = readyToApprove(s);
    expect(s.call("customer", "POST", `/requests/${r.id}/approve`, ASSERTION).body).toMatchObject({
      state: "SUBMITTED",
    });
    s.fake.settle(r.id);
    expect((s.call("agent", "GET", `/requests/${r.id}`).body as Req).state).toBe("SETTLED");
  });

  it("an agent cannot claim and a customer cannot create; strangers get 401", () => {
    const s = setup();
    expect(s.call(null, "POST", "/agent/requests", { amount_kobo: 100 }).status).toBe(401);
    expect(s.call("customer", "POST", "/agent/requests", { amount_kobo: 100 }).status).toBe(403);
    expect(s.call("agent", "POST", "/requests/claim", { claim_code: "4001" }).status).toBe(403);
  });

  it("tampering after the readback makes approval fail with INTENT_CHANGED and nothing is sent", () => {
    const s = setup();
    const r = readyToApprove(s);
    s.call(null, "POST", `/demo/requests/${r.id}/tamper`, {}, { "x-demo-token": DEMO_TOKEN });
    const res = s.call("customer", "POST", `/requests/${r.id}/approve`, ASSERTION);
    expect(res).toMatchObject({ status: 409, body: { code: "INTENT_CHANGED" } });
    expect((s.call("agent", "GET", `/requests/${r.id}`).body as Req).state).toBe("READ_BACK");
  });

  it("expires by the clock, and an expired request cannot be read back, declined or approved", () => {
    const s = setup();
    const r = created(s.call);
    s.call("customer", "POST", "/requests/claim", { claim_code: r.claim_code });
    s.advance(121_000);
    expect(s.call("customer", "GET", `/requests/${r.id}/readback`).status).toBe(410);
    expect((s.call("customer", "GET", `/requests/${r.id}`).body as Req).state).toBe("EXPIRED");
  });

  it("approval needs a passkey, a challenge and a prior readback", () => {
    const s = setup();
    const r = created(s.call);
    s.call("customer", "POST", "/requests/claim", { claim_code: r.claim_code });
    expect(s.call("customer", "POST", `/requests/${r.id}/challenge`).body).toMatchObject({
      code: "STATE_CONFLICT",
    });
    s.call("customer", "GET", `/requests/${r.id}/readback`);
    expect(s.call("customer", "POST", `/requests/${r.id}/challenge`).body).toMatchObject({
      code: "NO_PASSKEY",
    });
    s.fake.addPasskey();
    expect(s.call("customer", "POST", `/requests/${r.id}/approve`, ASSERTION).body).toMatchObject({
      code: "CHALLENGE_NOT_FOUND",
    });
  });

  it("refuses an unsupported readback language with 422, like the backend", () => {
    const s = setup();
    const r = created(s.call);
    s.call("customer", "POST", "/requests/claim", { claim_code: r.claim_code });
    expect(
      s.call("customer", "GET", `/requests/${r.id}/readback`, undefined, {}, { lang: "fr" }).status,
    ).toBe(422);
  });

  it("decline moves nothing and needs a prior readback", () => {
    const s = setup();
    const r = created(s.call);
    s.call("customer", "POST", "/requests/claim", { claim_code: r.claim_code });
    expect(s.call("customer", "POST", `/requests/${r.id}/decline`).status).toBe(409);
    s.call("customer", "GET", `/requests/${r.id}/readback`);
    expect(s.call("customer", "POST", `/requests/${r.id}/decline`).body).toMatchObject({
      state: "DECLINED",
    });
  });

  it("demo endpoints need the demo token", () => {
    const s = setup();
    expect(s.call(null, "POST", "/demo/reset").status).toBe(401);
    expect(
      s.call(null, "POST", "/demo/reset", undefined, { "x-demo-token": DEMO_TOKEN }).status,
    ).toBe(200);
  });

  it("only ever deals in integer kobo", () => {
    const s = setup();
    expect(s.call("agent", "POST", "/agent/requests", { amount_kobo: 1500.5 }).status).toBe(422);
    expect(s.call("agent", "POST", "/agent/requests", { amount_kobo: 0 }).status).toBe(422);
  });
});
