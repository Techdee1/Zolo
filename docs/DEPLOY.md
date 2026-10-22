# Deploying Zolo

This is a **demo deployment**: mock login (a fixed code), a mock bank, and the demo console. It is meant
for a stage demo and for judges to try, not for real money. Everything runs on one machine with Docker.

## What runs

| Container | What | Public? |
| --- | --- | --- |
| `caddy` | HTTPS, and the only thing reachable from outside (ports 80 and 443) | yes |
| `web` | The Next.js app: landing page, screens, and a proxy that sends `/api/*` to the API | no |
| `api` | The FastAPI backend (migrations run on start) | no |
| `postgres` | The database | no |

The browser only ever talks to one address. That is why **passkeys are bound to that address**: the
domain you pick is the RP ID, and a passkey made on another domain (or on a tunnel) will not work.

## Backend on Heroku, frontend on Vercel

The web app can live on Vercel and the API on Heroku. The Vercel app proxies `/api/*` to the API, so the
browser still talks to one address (the Vercel one) and **passkeys belong to the Vercel host**.

**Heroku** (one app, one Basic dyno, one Heroku Postgres Essential-0; container stack). `backend/heroku.yml`
builds the same Dockerfile and runs migrations and the first seed in the release phase. Config vars:

| Var | Value |
| --- | --- |
| `DATABASE_URL` | set by the Postgres add-on (a plain `postgres://` URL is accepted) |
| `DATABASE_SSL` | `require` (Heroku Postgres only accepts SSL) |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `4`, `2` (Essential-0 allows 20 connections; the release phase needs one) |
| `SESSION_SECRET`, `DEMO_TOKEN` | generated |
| `RP_ID`, `ORIGIN`, `CORS_ORIGINS` | the Vercel host, e.g. `zolo-coral.vercel.app` and `https://zolo-coral.vercel.app` |
| `COOKIE_SECURE`, `TRUST_FORWARDED_FOR`, `DEMO_MODE`, `ENV` | `true`, `true`, `true`, `prod` |
| `AUDIO_CACHE_DIR` | `/tmp/audio` (Heroku's disk is ephemeral; the clips are copied there from the image at every start) |
| `TTS_LIVE_ENABLED` | `false` (the live path is never used) |
| `YARNGPT_API_KEY`, `AUDIO_PRERENDER_ON_CREATE`, `AUDIO_DAILY_RENDER_CAP` | the key; `true`; `60`. When an agent creates a request the API renders the English and Pidgin clip in the background **only if no shipped or cached clip matches**, never blocking the request. At most 60 renders start per UTC day (counted in memory); when the cap or the provider's quota is reached it stops and the customer simply gets the text. The log shows counts only |

Deploy from the repository root with `git subtree push --prefix backend heroku main` (the app root is
`backend/`). At every start the API logs one line, `audio clips present: en 53/74, pcm 48/58, ...`, so a
missing clip is visible. **Vercel:** set `BACKEND_URL` to the Heroku app's `https://<app>.herokuapp.com`
and redeploy; set `NEXT_PUBLIC_FEATURE_DEMO=true` (a build-time setting) if you want `/demo`.

## On Render (the quick way)

`render.yaml` at the repo root describes everything: a Postgres database, the API as a **private**
service (only the web app can reach it), the web app as the public service, and a 1 GB disk for the
voice clips. Render gives it an HTTPS address and renews the certificate.

1. **Put the code where Render can read it.** Render deploys from a branch of a GitHub repo. Use
   `main` once this branch is merged, or pick `frontend-phase-1` in step 3.
2. **Sign in at render.com** and connect your GitHub account.
3. **New > Blueprint**, choose the repo and the branch. Render reads `render.yaml` and shows what it
   will create: `zolo-db`, `zolo-api`, `zolo-web`. It asks for the values marked `sync: false`.
4. **Fill in the prompts.** First decide the public address. The web service is called `zolo-web`, so
   its address is normally `https://zolo-web.onrender.com` (if the name is taken, Render adds a
   suffix: use whatever it shows for `zolo-web`). Then:

   | Variable | Value |
   | --- | --- |
   | `RP_ID` | `zolo-web.onrender.com` (the host only: no `https://`, no slash) |
   | `ORIGIN` | `https://zolo-web.onrender.com` |
   | `CORS_ORIGINS` | `https://zolo-web.onrender.com` |
   | `YARNGPT_API_KEY` | your key |

   `SESSION_SECRET` and `DEMO_TOKEN` are generated for you. Read the demo token afterwards under
   `zolo-api` > Environment.
5. **Apply.** The first build takes several minutes. When both services are live, open the web
   address: the landing page, then "Try the demo".
6. **If the address turned out different** from the one you typed, fix `RP_ID`, `ORIGIN` and
   `CORS_ORIGINS` on `zolo-api` (Environment) and let it redeploy. Until they match, passkeys fail.
7. **Do the real-phone run on that address** ([REAL_DEVICE_TEST.md](REAL_DEVICE_TEST.md)).

What it costs (check Render's pricing page; plans change): two Starter services, a small Postgres and
a 1 GB disk is roughly **US$20 a month**, billed by the hour, so deleting it after the event stops the
bill. A private service and a disk need a paid plan; the free web tier sleeps after 15 minutes idle
(a 30 to 60 second wake-up), which is a bad surprise on stage. The small free database expires after
30 days.

If you would rather watch the logs: each service has a **Logs** tab. The API logs one JSON line per
request with reason codes only.

## On Render, free plan

`render.free.yaml` is the same app on Render's free plans. It works, with trade-offs you should know
before putting it in front of judges:

| Limit of the free plan | What it means for Zolo |
| --- | --- |
| Web services **sleep after 15 minutes without traffic** and take roughly 30 to 60 seconds to wake | The first visit after a quiet spell is slow, and because the web app wakes the API too, it can take a minute or two. **Open the site and sign in a few minutes before you present**, and keep it warm. |
| **No private services** | The API is a normal public web service and the web app calls it by its public address. Browsers still only talk to the web app, so nothing about passkeys changes. |
| **No persistent disk** | Voice clips live on the instance's own storage and are **lost when it restarts or redeploys**. They are re-rendered on demand (credits) the next time that amount is asked for. |
| **The free database expires after 30 days** | Fine for an event; for anything longer, upgrade it. |
| 750 free instance hours a month, shared | Two services kept awake all month would use them up. Fine for a few days of demo. |
| 512 MB memory per service | Enough for this app. |

Steps are the same as the paid version, with these differences:

1. In **New > Blueprint**, set the **Blueprint file path** to `render.free.yaml`.
2. It asks for one more value: `BACKEND_URL` on `zolo-web` is the API's public address,
   **`https://zolo-api.onrender.com`** (use the address Render shows for `zolo-api`).
   `RP_ID`, `ORIGIN` and `CORS_ORIGINS` are still the **web** service's address, as in the table above.
3. Deploy `zolo-api` first if you can: `zolo-web` needs its address.

You can switch to the paid file later without losing anything but the audio clips: create the
Blueprint from `render.yaml` instead (it moves the API to a private service and adds the disk).

## What you need (your own server)

- A small Linux machine (1 vCPU and 2 GB is enough) with Docker and the Compose plugin.
  Any provider works: a DigitalOcean droplet, Hetzner, AWS Lightsail, a Google Cloud VM.
- A domain name with an **A record** pointing at the machine's IP, and ports 80 and 443 open.
  (No domain yet? A name like `zolo.<your-ip-with-dashes>.sslip.io` resolves to your IP and Caddy can
  get a certificate for it. Fine for a demo; a real domain is better.)
- A YarnGPT API key for the voice (optional: without it, the screen reader reads the request).

## First deploy

```bash
git clone <the repo> && cd Zolo
cp deploy/.env.example deploy/.env
# edit deploy/.env: SITE_ADDRESS / SITE_HOST / SITE_ORIGIN, and generate the three secrets:
#   openssl rand -hex 32     (SESSION_SECRET, DEMO_TOKEN, POSTGRES_PASSWORD)
docker compose -f deploy/compose.yml --env-file deploy/.env up -d --build
```

The API migrates the database and seeds the demo people on its first start (and only then: a restart
keeps requests and balances).

Open `https://<your domain>`. The first request takes a few seconds while Caddy gets the certificate.
Then check:

```bash
curl -s https://<your domain>/api/readyz        # {"status":"ok","database":true,"seed":true}
```

`POST /api/demo/reset` (the demo console's "Reset the demo") puts people,
balances and requests back to the start and **keeps registered passkeys**.

## The voice: how the audio works

The readback sentence ("Bisi Ventures is asking for fifteen thousand naira. One five, zero zero zero.
Do you want to approve?") is built by the backend. Its audio is a YarnGPT clip stored as a file, named
by a hash of *provider, language, voice and the exact words*. The readback endpoint only **looks up**
that file, never renders it: rendering takes 3 to 7 seconds and must never sit on the approval path.

- **Languages.** English, Pidgin, Yoruba, Hausa and Igbo are all accepted (`?lang=en|pcm|yo|ha|ig`).
  English and Pidgin always return their text, with audio when a clip exists. **Yoruba, Hausa and Igbo
  return in that language only when a recording of the exact sentence exists**; otherwise the English
  readback comes back with `fallback_from` set to the language asked for (never an error), and the app
  shows a short note. Which sentences have recordings is decided by the clip set below.
- **Amounts.** Any amount can have a voice, in two ways that work together:
  1. **On request (the default in this setup).** With `AUDIO_PRERENDER_ON_CREATE=true`, the moment an
     agent creates a request the backend renders the English and Pidgin readbacks in the background.
     The customer takes several seconds to claim and open it, and the readback also waits up to 4
     seconds for a clip that is nearly done. If a render is late or fails, the customer gets the text
     and the screen reader reads it, exactly as before. The same sentence is rendered once, ever.
  2. **The clip set** (below) so the demo amounts have a voice in every language from the first listen.
- **Clips that ship with the code.** `backend/audio_seed/` holds the clip set. At every start the
  container copies any that are missing onto the audio disk (it never overwrites). This is what keeps
  the demo amounts spoken on a host with no disk (the free Render plan), where the cache starts empty
  after every restart. The set (about 160 clips, mono mp3 at 40 kbps) is:
  the demo script lines and voice replies; the fixed status lines (paid, declined, expired,
  processing); and the readback for every seeded agent at N2,000, N5,000, N10,000, N15,000, N20,000
  and N50,000 in English, with N5,000 and N15,000 only for the other four languages. English and
  Pidgin are rendered in the primary voice (`idera`) and a backup (`jude`); Yoruba, Hausa and Igbo in
  `idera`. To switch to the backup voice, set `TTS_VOICE_EN=jude` and `TTS_VOICE_PCM=jude`. To rebuild
  or refresh the set, on a machine with a working YarnGPT key:
  ```bash
  cd backend
  uv run python -m zolo.tools.render_clips --dry-run             # exact counts and voices, no credits
  uv run python -m zolo.tools.render_clips                       # render what is missing (credits)
  uv run python -m zolo.tools.render_clips --export audio_seed   # copy the set into the folder
  git add audio_seed && git commit -m "feat: ship the clip set"
  ```
  It renders one clip at a time, skips anything already cached, waits out the provider's rate limit,
  and stops at once if the quota runs out. A test checks nothing but the set ships.
- **Where the clips live.** On the `audio` Docker volume (`/data/audio`), so they survive restarts and
  redeploys. The files are named by a hash and hold audio only, no readable payment details.
- **Cost.** One YarnGPT job per new sentence: at most two per new request (English and Pidgin), and
  only when that amount and payee have not been spoken before. Agents are limited to 10 requests a
  minute, which caps the spend.
- **A new agent or payee name** is a new sentence, so it is rendered on first use (or add the name to
  the seed and run `prerender_amounts` again).

## Updating

```bash
git pull
docker compose -f deploy/compose.yml --env-file deploy/.env up -d --build
```

Migrations run when the API starts. Volumes (database, audio, certificates) are kept.

## Operating it

- **Logs:** `docker compose -f deploy/compose.yml logs -f api web caddy`. The API logs one JSON line per
  request with reason codes only, never payment details or the readback words.
- **Demo console:** `https://<your domain>/demo`, with the `DEMO_TOKEN` from `deploy/.env`.
- **Backups:** the database is the `pgdata` volume. For a demo, `POST /api/demo/reset` is the backup.
- **Stopping:** `docker compose -f deploy/compose.yml down` keeps data; add `-v` to delete it.

## Before you rely on it

- **Do the real-phone run again on the deployed address** ([REAL_DEVICE_TEST.md](REAL_DEVICE_TEST.md)).
  A passkey made anywhere else (localhost, a tunnel) does not carry over.
- **This is not production.** `DEMO_MODE=true` turns on the fixed-code login and the demo endpoints
  (guarded by the demo token). The bank is a mock. Do not point it at real accounts.
- **Keep `deploy/.env` private.** It holds the session secret, the demo token, the database password
  and the voice key. It is gitignored.
