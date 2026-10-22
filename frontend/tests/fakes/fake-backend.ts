/**
 * A faithful stand-in for the Zolo API (Phase 1), as ONE pure function: `fake.handle(req)`.
 * The MSW handlers (unit tests) and the e2e fake server both call it, so they cannot disagree.
 *
 * It mirrors backend/openapi.json: the same paths, status codes and error codes, the same
 * state machine (CREATED, READ_BACK, APPROVED, SUBMITTED, SETTLED, DECLINED, EXPIRED, FAILED),
 * the same rules (an agent cannot claim, a tampered request fails with INTENT_CHANGED). It does NOT
 * verify WebAuthn signatures: that is the backend's job, and step 6 runs against the real backend.
 */
import { nairaWords } from "../../lib/format/words";
import { formatNaira } from "../../lib/format/money";

export type FakeRequest = {
  method: string;
  path: string; // no /api prefix, no query string
  query?: Record<string, string>;
  headers?: Record<string, string | undefined>; // lower-case names
  body?: unknown;
};
export type FakeResponse = { status: number; headers: Record<string, string>; body: unknown };

type State =
  | "CREATED"
  | "READ_BACK"
  | "APPROVED"
  | "SUBMITTED"
  | "SETTLED"
  | "DECLINED"
  | "EXPIRED"
  | "FAILED";
type Role = "customer" | "agent";
type Row = {
  id: string;
  agentId: string;
  customerId: string | null;
  payee: string;
  amount: number;
  originalAmount: number;
  state: State;
  code: string;
  expiresAt: number;
  failure: string | null;
  tampered: boolean;
  challenged: boolean;
  createdAt: number;
  events: Array<{ at: number; event: string; actor: string; details: Record<string, unknown> }>;
};

export const DEMO_TOKEN = "demo-token-1234";
export const MOCK_OTP = "123456";
export const CUSTOMER = {
  id: "00000000-0000-4000-8000-000000000001",
  phone: "+2348011111111",
  name: "Amaka Obi",
};
export const AGENT = {
  id: "00000000-0000-4000-8000-000000000002",
  phone: "+2348022222222",
  name: "Bisi Ventures",
};

/** What the next approval does, so tests can walk every result state. */
export type ApprovalOutcome =
  | "SETTLED"
  | "SUBMITTED"
  | "FAILED"
  | "LIMIT_EXCEEDED"
  | "RISK_BLOCKED"
  | "BANK_REJECTED"
  | "SIGNATURE_INVALID";

export type FakeOptions = {
  now?: () => number;
  /** Readback audio URL to return, or null for "not pre-rendered". */
  audioUrl?: string | null;
  ttlMs?: number;
};

export function createFakeBackend(options: FakeOptions = {}) {
  const now = options.now ?? Date.now;
  const ttlMs = options.ttlMs ?? 120_000;
  let audioUrl = options.audioUrl ?? null;
  let nativeClips = false; // is there a recording of the sentence in Yoruba, Hausa and Igbo?
  let seq = 0;
  let sessions = new Map<string, { role: Role; id: string }>();
  let requests = new Map<string, Row>();
  const passkeys = new Map<string, string[]>(); // customer id -> credential ids (survives reset, like the backend)
  let nextOutcome: ApprovalOutcome = "SETTLED";
  let lastApproval: unknown = null;
  let forcedSession: string | null = null;
  // Phone-call approval: off (every /phone route is a 404) until a test turns it on.
  let phoneOn = false;
  let phoneEnrolled = false;
  const phoneCalls = new Map<string, { requestId: string; stage: "menu" | "pin" | "done" }>();
  const idempotent = new Map<string, unknown>();

  const json = (
    status: number,
    body: unknown,
    headers: Record<string, string> = {},
  ): FakeResponse => ({
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
    body,
  });
  const problem = (status: number, code: string, detail = ""): FakeResponse => ({
    status,
    headers: { "content-type": "application/problem+json", "cache-control": "no-store" },
    body: { type: "about:blank", title: code, status, code, detail },
  });
  const iso = (ms: number) => new Date(ms).toISOString();
  const uuid = () => {
    seq += 1;
    return `10000000-0000-4000-8000-${String(seq).padStart(12, "0")}`;
  };
  const b64url = (n: number) =>
    Buffer.from(Array.from({ length: n }, (_, i) => (i * 37 + seq * 11) % 256)).toString(
      "base64url",
    );

  const record = (r: Row, event: string, actor: string, details: Record<string, unknown> = {}) =>
    r.events.push({ at: now(), event, actor, details });

  const settleExpiry = (r: Row) => {
    const live: State[] = ["CREATED", "READ_BACK", "APPROVED"];
    if (live.includes(r.state) && now() >= r.expiresAt) {
      r.state = "EXPIRED";
      record(r, "request.expired", "system");
    }
  };
  const out = (r: Row) => ({
    id: r.id,
    state: r.state,
    amount_kobo: r.amount,
    payee_name: r.payee,
    expires_at: iso(r.expiresAt),
    claimed: r.customerId !== null,
    bank_reference: r.state === "SETTLED" ? `ZNB${r.id.slice(-6)}` : null,
    failure_reason: r.state === "FAILED" ? r.failure : null,
  });

  const who = (req: FakeRequest) => {
    const cookie = req.headers?.cookie ?? "";
    const token =
      forcedSession ??
      cookie
        .split(/;\s*/)
        .map((p) => p.split("="))
        .find(([k]) => k === "zolo_session")?.[1];
    return token ? (sessions.get(token) ?? null) : null;
  };

  const find = (id: string) => requests.get(id);

  function handle(req: FakeRequest): FakeResponse {
    const { method, path } = req;
    const body = (req.body ?? {}) as Record<string, unknown>;
    const me = who(req);
    const needs = (role?: Role): FakeResponse | null => {
      if (!me) return problem(401, "UNAUTHENTICATED", "Log in first");
      if (role && me.role !== role) return problem(403, "FORBIDDEN", `This is for ${role}s`);
      return null;
    };

    if (method === "GET" && path === "/healthz") return json(200, { status: "ok" });

    if (method === "POST" && path === "/auth/mock-login") {
      const phone = String(body.phone ?? "");
      const user =
        phone === CUSTOMER.phone
          ? { ...CUSTOMER, role: "customer" as const }
          : phone === AGENT.phone
            ? { ...AGENT, role: "agent" as const }
            : null;
      if (!user || body.otp !== MOCK_OTP)
        return problem(401, "UNAUTHENTICATED", "Wrong phone or code");
      const token = Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) =>
        b.toString(16).padStart(2, "0"),
      ).join("");
      sessions.set(token, { role: user.role, id: user.id });
      return json(
        200,
        { role: user.role, id: user.id, display_name: user.name },
        { "set-cookie": `zolo_session=${token}; Max-Age=43200; Path=/; HttpOnly; SameSite=Lax` },
      );
    }

    if (method === "GET" && path === "/me/activity") {
      const e = needs("customer");
      if (e) return e;
      const items = [...requests.values()]
        .filter(
          (r) =>
            r.customerId === me!.id &&
            ["SETTLED", "DECLINED", "FAILED", "EXPIRED"].includes(r.state),
        )
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, 20)
        .map((r) => ({
          id: r.id,
          state: r.state,
          amount_kobo: r.amount,
          payee_name: r.payee,
          created_at: iso(r.createdAt),
          line: `${r.state === "SETTLED" ? "Paid" : r.state === "DECLINED" ? "Declined" : "Not paid"} ${formatNaira(r.amount)} to ${r.payee}`,
        }));
      return json(200, { items });
    }

    if (method === "POST" && path === "/agent/requests") {
      const e = needs("agent");
      if (e) return e;
      const key = req.headers?.["idempotency-key"];
      if (key && idempotent.has(`${me!.id}:${key}`))
        return json(201, idempotent.get(`${me!.id}:${key}`));
      const amount = body.amount_kobo;
      if (
        typeof amount !== "number" ||
        !Number.isInteger(amount) ||
        amount <= 0 ||
        amount > 100_000_000
      )
        return problem(422, "VALIDATION_ERROR", "amount_kobo must be a positive whole number");
      seq += 1;
      const r: Row = {
        id: uuid(),
        agentId: me!.id,
        customerId: null,
        payee: AGENT.name,
        amount,
        originalAmount: amount,
        state: "CREATED",
        code: String(4000 + seq).padStart(4, "0"),
        expiresAt: now() + ttlMs,
        failure: null,
        tampered: false,
        challenged: false,
        createdAt: now(),
        events: [],
      };
      requests.set(r.id, r);
      record(r, "request.created", "agent");
      const res = {
        id: r.id,
        claim_code: r.code,
        qr_payload: `zolo://claim/${r.id}.${r.code}`,
        expires_at: iso(r.expiresAt),
        payee_name: r.payee,
      };
      if (key) idempotent.set(`${me!.id}:${key}`, res);
      return json(201, res);
    }

    if (method === "POST" && path === "/requests/claim") {
      const e = needs("customer");
      if (e) return e;
      const code =
        typeof body.claim_code === "string"
          ? body.claim_code
          : String(body.qr_payload ?? "")
              .split(".")
              .pop();
      if (!code || !/^\d{4}$/.test(code))
        return problem(422, "VALIDATION_ERROR", "no 4-digit code found");
      const r = [...requests.values()].find(
        (x) => x.code === code && ["CREATED", "READ_BACK", "EXPIRED"].includes(x.state),
      );
      if (!r) return problem(404, "CODE_NOT_FOUND");
      settleExpiry(r);
      if (r.state === "EXPIRED") return problem(410, "REQUEST_EXPIRED");
      if (r.customerId && r.customerId !== me!.id) return problem(404, "CODE_NOT_FOUND");
      r.customerId = me!.id;
      record(r, "request.claimed", "customer");
      return json(200, out(r));
    }

    const m = /^\/requests\/([^/]+)(?:\/(readback|challenge|approve|decline))?$/.exec(path);
    if (m) {
      const e = needs();
      if (e) return e;
      const r = find(m[1]!);
      const mine = r && (me!.role === "agent" ? r.agentId === me!.id : r.customerId === me!.id);
      if (!r || !mine) return problem(404, "NOT_FOUND");
      settleExpiry(r);
      const action = m[2];

      if (!action && method === "GET") return json(200, out(r));
      if (me!.role !== "customer") return problem(403, "FORBIDDEN");

      if (action === "readback" && method === "GET") {
        if (r.state === "EXPIRED") return problem(410, "REQUEST_EXPIRED");
        if (r.tampered) return problem(409, "INTENT_CHANGED");
        if (r.state !== "CREATED" && r.state !== "READ_BACK") return problem(409, "STATE_CONFLICT");
        const asked = req.query?.lang ?? "pcm";
        if (!["en", "pcm", "yo", "ha", "ig"].includes(asked))
          return problem(422, "VALIDATION_ERROR", "language must be en, pcm, yo, ha or ig");
        // Like the backend: Yoruba, Hausa and Igbo come back in that language only when a recording
        // of the exact sentence exists; otherwise the English readback, with `fallback_from` set.
        const native = ["yo", "ha", "ig"].includes(asked);
        const served = native && !nativeClips ? "en" : asked;
        const fallbackFrom = native && !nativeClips ? asked : null;
        const lang = served;
        r.state = "READ_BACK";
        record(r, "request.read_back", "customer", { lang });
        // Like the backend: `amount_words` has no "naira" (the template adds it), and the digits
        // are spoken again in groups of three from the right ("one five, zero zero zero").
        const words = nairaWords(r.amount);
        const NAMES = [
          "zero",
          "one",
          "two",
          "three",
          "four",
          "five",
          "six",
          "seven",
          "eight",
          "nine",
        ];
        const spokenDigits = String(r.amount / 100)
          .replace(/\B(?=(\d{3})+$)/g, ",")
          .split(",")
          .map((group) => [...group].map((d) => NAMES[Number(d)]).join(" "))
          .join(", ");
        const digits = spokenDigits.charAt(0).toUpperCase() + spokenDigits.slice(1);
        const text =
          lang === "pcm"
            ? `${r.payee} dey ask for ${words} naira. ${digits}. You wan approve?`
            : lang === "yo"
              ? `${r.payee} n bere fun ${words} naira. ${digits}. Se o fowo si i?`
              : lang === "ha"
                ? `${r.payee} yana neman naira ${words}. ${digits}. Kana amincewa?`
                : lang === "ig"
                  ? `${r.payee} na-arị naira ${words}. ${digits}. I kwenyere?`
                  : `${r.payee} is asking for ${words} naira. ${digits}. Do you want to approve?`;
        return json(200, {
          text,
          lang,
          fallback_from: fallbackFrom,
          amount_words: words,
          payee_name: r.payee,
          amount_kobo: r.amount,
          expires_at: iso(r.expiresAt),
          audio_url: audioUrl,
        });
      }

      if (action === "challenge" && method === "POST") {
        if (r.state === "EXPIRED") return problem(410, "REQUEST_EXPIRED");
        if (r.tampered) return problem(409, "INTENT_CHANGED");
        if (r.state !== "READ_BACK") return problem(409, "STATE_CONFLICT");
        const ids = passkeys.get(me!.id) ?? [];
        if (ids.length === 0) return problem(409, "NO_PASSKEY");
        r.challenged = true;
        return json(200, {
          challenge: b64url(32),
          rpId: "localhost",
          timeout: 60_000,
          userVerification: "required",
          allowCredentials: ids.map((id) => ({ id, type: "public-key" })),
        });
      }

      if (action === "approve" && method === "POST") {
        if (r.state === "EXPIRED") return problem(410, "REQUEST_EXPIRED");
        if (r.tampered) return problem(409, "INTENT_CHANGED");
        if (r.state !== "READ_BACK") return problem(409, "ALREADY_USED");
        if (!r.challenged) return problem(409, "CHALLENGE_NOT_FOUND");
        if (typeof body.id !== "string" || typeof body.response !== "object")
          return problem(422, "VALIDATION_ERROR");
        if (nextOutcome === "SIGNATURE_INVALID") return problem(401, "SIGNATURE_INVALID");
        if (nextOutcome === "LIMIT_EXCEEDED") return problem(422, "LIMIT_EXCEEDED");
        lastApproval = body;
        r.challenged = false;
        r.state = "APPROVED";
        record(r, "request.approved", "customer");
        if (nextOutcome === "RISK_BLOCKED" || nextOutcome === "BANK_REJECTED") {
          r.state = "FAILED";
          r.failure = nextOutcome;
          record(r, "request.failed", "system", { reason: nextOutcome });
        } else if (nextOutcome === "FAILED") {
          r.state = "FAILED";
          r.failure = "BANK_TIMEOUT";
        } else if (nextOutcome === "SUBMITTED") {
          r.state = "SUBMITTED";
          record(r, "request.submitted", "system");
        } else {
          r.state = "SETTLED";
          record(r, "request.settled", "system");
        }
        return json(200, out(r));
      }

      if (action === "decline" && method === "POST") {
        if (r.state === "EXPIRED") return problem(410, "REQUEST_EXPIRED");
        if (r.state !== "READ_BACK")
          return problem(409, "STATE_CONFLICT", "it must be read back first");
        r.state = "DECLINED";
        record(r, "request.declined", "customer");
        return json(200, out(r));
      }
    }

    if (path.startsWith("/phone/")) {
      // like the real backend, whose problem title says what is wrong
      const titled = (status: number, code: string, title: string): FakeResponse => {
        const p = problem(status, code);
        return { ...p, body: { ...(p.body as object), title } };
      };
      const e = needs("customer");
      if (e) return e;
      if (method === "GET" && path === "/phone/enrolment" && !phoneOn)
        return json(200, {
          enabled: false,
          enrolled: false,
          language: "en",
          phone_last4: "",
          locked: false,
          paused: false,
        });
      if (!phoneOn) return problem(404, "NOT_FOUND");
      const prompt = (key: string, text: string) => ({ key, text, audio_url: null });
      const view = (
        callId: string,
        stage: "menu" | "pin" | "done",
        prompts: ReturnType<typeof prompt>[],
        outcome: "approved" | "declined" | "ended" | null = null,
      ) =>
        json(200, {
          call_id: callId,
          stage,
          expects: stage === "menu" ? "choice" : stage === "pin" ? "pin" : "none",
          prompts,
          done: stage === "done",
          outcome,
          lang: "en",
        });
      if (method === "GET" && path === "/phone/enrolment")
        return json(200, {
          enabled: true,
          enrolled: phoneEnrolled,
          language: "en",
          phone_last4: phoneEnrolled ? "0142" : "",
          locked: false,
          paused: false,
        });
      if (method === "POST" && path === "/phone/enrol") {
        if (!/^[0-9]{4}$/.test(String(body.pin)) || body.pin === "1234")
          return titled(422, "VALIDATION_ERROR", "Choose a stronger PIN");
        phoneEnrolled = true;
        return json(200, {
          enabled: true,
          enrolled: true,
          language: body.language ?? "en",
          phone_last4: "0142",
          locked: false,
          paused: false,
        });
      }
      if (method === "POST" && path === "/phone/calls") {
        const r = find(String(body.request_id));
        if (!phoneEnrolled) return titled(409, "STATE_CONFLICT", "Set up phone approval first");
        if (!r || r.customerId !== me!.id) return problem(404, "NOT_FOUND");
        r.state = "READ_BACK";
        const id = uuid();
        phoneCalls.set(id, { requestId: r.id, stage: "menu" });
        return {
          ...view(id, "menu", [
            prompt("intro", "This is Zolo. Someone has asked for a payment from your account."),
            prompt("readback", `${r.payee} is asking for a payment.`),
            prompt("menu", "To approve, press 1. To decline, press 2. To hear it again, press 9."),
          ]),
          status: 201,
        };
      }
      const keys = /^\/phone\/calls\/([^/]+)\/keys$/.exec(path);
      if (method === "POST" && keys) {
        const call = phoneCalls.get(keys[1]!);
        const r = call && find(call.requestId);
        if (!call || !r) return problem(404, "NOT_FOUND");
        const digits = String(body.digits);
        if (call.stage === "menu") {
          if (digits === "1") {
            call.stage = "pin";
            return view(keys[1]!, "pin", [prompt("pin", "Enter your four digit Zolo PIN now.")]);
          }
          if (digits === "2") {
            call.stage = "done";
            r.state = "DECLINED";
            return view(
              keys[1]!,
              "done",
              [prompt("declined", "Declined. Nothing was sent.")],
              "declined",
            );
          }
          return view(keys[1]!, "menu", [prompt("menu", "To approve, press 1.")]);
        }
        call.stage = "done";
        if (digits !== "7391")
          return view(keys[1]!, "done", [prompt("wrong_pin", "That PIN was wrong.")], "ended");
        r.state = "SETTLED";
        return view(keys[1]!, "done", [prompt("approved", "Approved. Goodbye.")], "approved");
      }
      return problem(404, "NOT_FOUND");
    }

    if (method === "POST" && path === "/passkeys/register/options") {
      const e = needs("customer");
      if (e) return e;
      return json(200, {
        challenge: b64url(32),
        rp: { id: "localhost", name: "Zolo" },
        user: {
          id: Buffer.from(me!.id).toString("base64url"),
          name: CUSTOMER.phone,
          displayName: CUSTOMER.name,
        },
        pubKeyCredParams: [
          { type: "public-key", alg: -7 },
          { type: "public-key", alg: -257 },
        ],
        timeout: 60_000,
        attestation: "none",
        // Like the real backend: a phone that already has the passkey cannot make a second one.
        excludeCredentials: (passkeys.get(me!.id) ?? []).map((id) => ({ id, type: "public-key" })),
        authenticatorSelection: {
          residentKey: "required",
          userVerification: "required",
          authenticatorAttachment: "platform",
        },
      });
    }
    if (method === "POST" && path === "/passkeys/register/verify") {
      const e = needs("customer");
      if (e) return e;
      const credential = body.credential as { id?: unknown } | undefined;
      if (!credential || typeof credential.id !== "string")
        return problem(400, "PASSKEY_REGISTRATION_FAILED");
      const had = (passkeys.get(me!.id) ?? []).length > 0;
      passkeys.set(me!.id, [credential.id]);
      return json(201, {
        id: uuid(),
        device_label: (body.device_label as string | undefined) ?? null,
        replaced_previous: had,
      });
    }

    if (path.startsWith("/demo/")) {
      if ((req.headers?.["x-demo-token"] ?? "") !== DEMO_TOKEN)
        return problem(401, "UNAUTHENTICATED", "A valid demo token is required");
      if (method === "POST" && path === "/demo/reset") {
        requests = new Map();
        sessions = new Map(sessions);
        lastApproval = null;
        return json(200, { customers: 1, agents: 1, accounts: 2, recipients: 1 });
      }
      const d = /^\/demo\/requests\/([^/]+)\/(expire|replay|tamper|timeline)$/.exec(path);
      const r = d && find(d[1]!);
      if (!d || !r) return problem(404, "NOT_FOUND");
      if (d[2] === "timeline" && method === "GET") {
        settleExpiry(r);
        return json(200, {
          request: out(r),
          events: r.events.map((ev, i) => ({
            id: i + 1,
            at: iso(ev.at),
            event: ev.event,
            actor: ev.actor,
            details: ev.details,
          })),
        });
      }
      if (d[2] === "expire" && method === "POST") {
        r.expiresAt = now();
        settleExpiry(r);
        return json(200, out(r));
      }
      if (d[2] === "tamper" && method === "POST") {
        if (r.state !== "READ_BACK") return problem(409, "STATE_CONFLICT");
        r.amount = typeof body.amount_kobo === "number" ? body.amount_kobo : 5_100_000;
        r.tampered = true;
        record(r, "demo.tampered", "demo", { to: r.amount });
        return json(200, out(r));
      }
      if (d[2] === "replay" && method === "POST") {
        if (!lastApproval) return problem(409, "STATE_CONFLICT", "nothing to replay");
        record(r, "approval.replay_rejected", "demo");
        return problem(409, "ALREADY_USED");
      }
    }

    return problem(404, "NOT_FOUND");
  }

  /** Test controls: these are NOT part of the real API. */
  return {
    handle,
    /** Skip the cookie: every request acts as this user. For unit tests. */
    actAs(role: Role | null) {
      if (!role) {
        forcedSession = null;
        return;
      }
      forcedSession = `forced-${role}`;
      sessions.set(forcedSession, { role, id: role === "customer" ? CUSTOMER.id : AGENT.id });
    },
    setOutcome(o: ApprovalOutcome) {
      nextOutcome = o;
    },
    /** Turn phone-call approval on, enrolled or not. */
    setPhone(on: boolean, enrolled = false) {
      phoneOn = on;
      phoneEnrolled = enrolled;
    },
    setAudio(url: string | null) {
      audioUrl = url;
    },
    /** Pretend the Yoruba, Hausa and Igbo recordings exist (or not): the language is then served as asked. */
    setNativeClips(on: boolean) {
      nativeClips = on;
    },
    /** The bank confirms a SUBMITTED payment. */
    settle(id: string) {
      const r = find(id);
      if (r?.state === "SUBMITTED") {
        r.state = "SETTLED";
        record(r, "request.settled", "system");
      }
    },
    addPasskey(customerId: string = CUSTOMER.id, credentialId = "fake-credential") {
      passkeys.set(customerId, [credentialId]);
    },
    reset() {
      requests = new Map();
      sessions = new Map();
      passkeys.clear();
      idempotent.clear();
      nextOutcome = "SETTLED";
      nativeClips = false;
      forcedSession = null;
      lastApproval = null;
      phoneOn = false;
      phoneEnrolled = false;
      phoneCalls.clear();
    },
    get nativeClips() {
      return nativeClips;
    },
    get requests() {
      return requests;
    },
  };
}

export type FakeBackend = ReturnType<typeof createFakeBackend>;
