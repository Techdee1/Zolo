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

## What you need

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

- **Languages.** The backend can speak **English and Pidgin** (`en`, `pcm`). Yoruba, Hausa and Igbo
  customers get the screens in their language and the readback in English, with a note saying so. The
  frontend never asks for a language the backend does not have.
- **Amounts.** Any amount can have a voice, in two ways that work together:
  1. **On request (the default in this setup).** With `AUDIO_PRERENDER_ON_CREATE=true`, the moment an
     agent creates a request the backend renders the English and Pidgin readbacks in the background.
     The customer takes several seconds to claim and open it, and the readback also waits up to 4
     seconds for a clip that is nearly done. If a render is late or fails, the customer gets the text
     and the screen reader reads it, exactly as before. The same sentence is rendered once, ever.
  2. **Warm the cache for common amounts** so even the first listen is instant:
     ```bash
     docker compose -f deploy/compose.yml --env-file deploy/.env run --rm api \
       python -m zolo.tools.prerender_amounts --dry-run        # count first
     docker compose -f deploy/compose.yml --env-file deploy/.env run --rm api \
       python -m zolo.tools.prerender_amounts                  # then render (spends credits)
     ```
     It covers every seeded agent in both languages for every ₦500 up to ₦10,000, every ₦1,000 up to
     ₦20,000, then every ₦5,000 up to ₦100,000 (about 180 clips), skipping any already stored. Re-run
     it any time: it only spends credits on new sentences.
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
