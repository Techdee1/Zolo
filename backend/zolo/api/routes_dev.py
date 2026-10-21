"""A bare-bones page for trying passkeys on a real phone before the real frontend exists.

Mounted ONLY when DEMO_MODE=true and kept out of the OpenAPI schema. It is served from the API's
own origin, so the RP ID and origin settings are the tunnel's host and https URL (see
docs/REAL_DEVICE_TEST.md). It is a test tool, not the product UI.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zolo passkey test</title>
<style>
 body{font:16px system-ui,sans-serif;max-width:34rem;margin:1rem auto;padding:0 1rem;color:#111;background:#fff}
 h1{font-size:1.2rem} fieldset{margin:1rem 0;border:1px solid #888;border-radius:.5rem}
 button,input{font:inherit;padding:.6rem;margin:.25rem 0;min-height:48px} button{width:100%}
 input{width:100%;box-sizing:border-box} pre{background:#f3f3f3;padding:.5rem;white-space:pre-wrap;word-break:break-word;min-height:6rem}
 .env{font-size:.85rem;color:#444}
</style></head><body>
<h1>Zolo passkey test</h1>
<p class="env" id="env"></p>

<fieldset><legend>1. Log in (mock)</legend>
 <label>Phone <input id="phone" value="+2348011111111" inputmode="tel"></label>
 <label>Code <input id="otp" value="123456" inputmode="numeric"></label>
 <button id="login">Log in</button>
 <p class="env">Customer: +2348011111111 &middot; Agent (Bisi Ventures): +2348022222222</p>
</fieldset>

<fieldset><legend>2a. Customer: register a passkey</legend>
 <button id="register">Create passkey on this phone</button>
</fieldset>

<fieldset><legend>2b. Agent: create a request</legend>
 <label>Amount in naira <input id="naira" value="15000" inputmode="numeric"></label>
 <button id="create">Create request</button>
</fieldset>

<fieldset><legend>3. Customer: claim, listen, approve</legend>
 <label>4-digit code <input id="code" inputmode="numeric" maxlength="4"></label>
 <button id="claim">Claim by code</button>
 <button id="readback">Read it back</button>
 <button id="approve">Approve with passkey</button>
 <button id="decline">Decline</button>
 <button id="status">Check status</button>
</fieldset>

<h2>Log</h2><pre id="log" aria-live="polite"></pre>

<script>
const $ = id => document.getElementById(id);
let requestId = null;
const log = (...a) => { $("log").textContent = a.map(x => typeof x === "string" ? x : JSON.stringify(x, null, 1)).join(" ") + "\n\n" + $("log").textContent; };
$("env").textContent = "origin: " + location.origin + "  |  host (must equal RP_ID): " + location.hostname;

const b64uToBuf = s => { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer; };
const bufToB64u = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function api(method, path, body) {
  const r = await fetch(path, { method, credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  let data = null; try { data = await r.json(); } catch (e) {}
  log(method + " " + path + " -> " + r.status + (data && data.code ? " " + data.code : ""), r.ok ? (data || "") : "");
  if (!r.ok) throw Object.assign(new Error(data && data.code || r.status), { data });
  return data;
}
const guard = fn => async () => { try { await fn(); } catch (e) { log("ERROR:", e.name + ": " + e.message); } };

$("login").onclick = guard(() => api("POST", "/auth/mock-login", { phone: $("phone").value, otp: $("otp").value }));

$("register").onclick = guard(async () => {
  if (!window.PublicKeyCredential) throw new Error("This browser has no WebAuthn (is the page on https?)");
  const o = await api("POST", "/passkeys/register/options");
  o.challenge = b64uToBuf(o.challenge); o.user.id = b64uToBuf(o.user.id);
  (o.excludeCredentials || []).forEach(c => c.id = b64uToBuf(c.id));
  const cred = await navigator.credentials.create({ publicKey: o });
  const json = { id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type, clientExtensionResults: cred.getClientExtensionResults(),
    authenticatorAttachment: cred.authenticatorAttachment || undefined,
    response: { clientDataJSON: bufToB64u(cred.response.clientDataJSON), attestationObject: bufToB64u(cred.response.attestationObject),
                transports: cred.response.getTransports ? cred.response.getTransports() : [] } };
  await api("POST", "/passkeys/register/verify", { credential: json, device_label: navigator.userAgent.slice(0, 50) });
});

$("create").onclick = guard(async () => {
  const r = await api("POST", "/agent/requests", { amount_kobo: Math.round(Number($("naira").value) * 100) });
  requestId = r.id; $("code").value = r.claim_code; log("READ THIS CODE TO THE CUSTOMER:", r.claim_code);
});

$("claim").onclick = guard(async () => { const r = await api("POST", "/requests/claim", { claim_code: $("code").value }); requestId = r.id; });
$("readback").onclick = guard(async () => {
  const r = await api("GET", "/requests/" + requestId + "/readback?lang=pcm");
  log("HEARD:", r.text);
  if ("speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(r.text));
});
$("approve").onclick = guard(async () => {
  const o = await api("POST", "/requests/" + requestId + "/challenge");
  o.challenge = b64uToBuf(o.challenge);
  (o.allowCredentials || []).forEach(c => c.id = b64uToBuf(c.id));
  const a = await navigator.credentials.get({ publicKey: o });
  const json = { id: a.id, rawId: bufToB64u(a.rawId), type: a.type, clientExtensionResults: a.getClientExtensionResults(),
    response: { authenticatorData: bufToB64u(a.response.authenticatorData), clientDataJSON: bufToB64u(a.response.clientDataJSON),
                signature: bufToB64u(a.response.signature), userHandle: a.response.userHandle ? bufToB64u(a.response.userHandle) : null } };
  await api("POST", "/requests/" + requestId + "/approve", json);
});
$("decline").onclick = guard(() => api("POST", "/requests/" + requestId + "/decline"));
$("status").onclick = guard(() => api("GET", "/requests/" + requestId));
</script></body></html>
"""


@router.get("/dev/passkey-test", response_class=HTMLResponse)
async def passkey_test_page() -> HTMLResponse:
    return HTMLResponse(
        PAGE,
        headers={
            # only this page's own inline script may run, and it may only talk to this origin
            "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'"
        },
    )
