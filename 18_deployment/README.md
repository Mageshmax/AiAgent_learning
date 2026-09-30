# Lesson 18: Deploy the agent

The FastAPI chat from `chat_ui/fastapi_app/05_save_history/`, made safe to put on the internet.

| File | What it is |
|---|---|
| `server.py` | FastAPI app: access keys, per-user history, rate limit, `/health` |
| `agent.py` | The agent (tools + streaming loop); settings from env vars; API errors become `error` events |
| `static/index.html` | The chat page; asks for an access key once and sends it as `X-Access-Key` |
| `.env.example` | Every setting, with comments. Copy to `.env` |
| `Dockerfile`, `.dockerignore` | Build a container image |
| `Caddyfile` | HTTPS reverse proxy config |

## What changes when strangers can reach your app

| Risk | What this lesson does |
|---|---|
| Anyone with the URL spends your Claude credits | Every chat request needs an access key (`APP_ACCESS_KEYS`) |
| One user reads another's chat | History is stored per key: `data/<key hash>/<session>.json` |
| A script sends 1,000 messages a minute | Rate limit per key (`RATE_LIMIT_PER_MINUTE`), 429 after that |
| Huge or odd input | Message length limit; session ids checked with a pattern |
| Claude API is down or slow | Error becomes a red message in the chat; the server keeps running |
| Secrets leak through git | Keys only in `.env` / environment variables; `.env` is in `.gitignore` |
| Passwords/keys sent in plain text | HTTPS in front (Caddy), never plain `http://` on the internet |
| You can't tell what went wrong | Log lines per request and per Claude call, with `request_id` (lesson 16) |

## Step 1: Run it locally

```bash
cd 18_deployment
cp .env.example .env                                          # then edit .env
python -c "import secrets; print(secrets.token_urlsafe(24))"  # make an access key, put it in APP_ACCESS_KEYS
python server.py
```

Open http://127.0.0.1:8000, paste your access key, and chat.

Test the protection with curl:

```bash
curl http://127.0.0.1:8000/health                                    # {"status":"ok"}  (no key needed)
curl "http://127.0.0.1:8000/history?session_id=test"                 # 401: no key
curl -H "X-Access-Key: <your key>" "http://127.0.0.1:8000/history?session_id=test"   # []
```

## Step 2: Run it in Docker

Docker packs the app and its Python into one image that runs the same everywhere.
Install Docker first: https://docs.docker.com/engine/install/ubuntu/

```bash
cd 18_deployment
docker build -t claude-chat .
docker run -d --name claude-chat \
  --env-file .env \
  -p 127.0.0.1:8000:8000 \
  -v claude-chat-data:/data \
  --restart unless-stopped \
  claude-chat
docker logs -f claude-chat        # watch the logs (Ctrl+C to stop watching)
```

- `--env-file .env` passes your settings in. The `.env` file is **not** copied into the image (see `.dockerignore`).
- `-p 127.0.0.1:8000:8000` makes the app reachable only from this machine. Caddy (step 3) is the public door.
- `-v claude-chat-data:/data` keeps chat histories when you rebuild or restart the container.
- Update after a code change: `docker build -t claude-chat . && docker rm -f claude-chat`, then run the `docker run` command again.

## Step 3: Put it on a server with HTTPS

You need: a small Linux server (any cloud VM with Ubuntu, 1 GB RAM is enough) and a domain name.

1. **Point the domain at the server.** In your domain's DNS settings, add an `A` record, e.g. `chat.example.com`, pointing to the server's public IP.
2. **Open only the web ports.** On Ubuntu:
   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
   ```
3. **Copy the folder to the server** (from your computer): `scp -r 18_deployment user@SERVER_IP:~/`
   Then create `.env` **on the server** (don't copy your local one around).
4. **Start the app** with the Docker commands from step 2.
5. **Install Caddy** (https://caddyserver.com/docs/install), put your domain in `Caddyfile`, then:
   ```bash
   sudo cp Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
   ```
   Caddy gets a free HTTPS certificate and renews it automatically. Open `https://chat.example.com`.

Alternatives with less server work: platforms such as Render, Railway or Fly.io build the `Dockerfile` for you and give you HTTPS. Set the same environment variables in their dashboard and add a disk/volume mounted at `/data`.

## Before you share the link

- [ ] `.env` is not in git (`git status` must not show it)
- [ ] Every user has their own access key; delete a key from `APP_ACCESS_KEYS` to block that person
- [ ] Spending limit set in the Anthropic Console (Settings → Limits), so a bug can't cost a fortune
- [ ] HTTPS works, and port 8000 is **not** open to the internet (`-p 127.0.0.1:8000:8000`)
- [ ] You checked the logs after a few test chats

## Limits of this design (what to learn next)

- **One process.** Sessions and rate limits live in memory, so run one worker. To scale out, move them to Redis or Postgres.
- **Shared access keys** are simple but basic. Real apps use user accounts (e.g. OAuth "Sign in with Google") and store users in a database.
- **No per-user budget.** Combine lesson 8c's `UsageTracker` with the user id to cap spending per person.
