# Kanade

Apple Music download queue server powered by [gamdl](https://github.com/glomatico/gamdl) and [BullMQ](https://docs.bullmq.io/).

Accepts download requests via REST API, queues them in Redis, and processes them with a background worker. Decryption goes through a [wrapper-v2](https://github.com/glomatico/wrapper-v2) sidecar, and completed targets are recorded in PostgreSQL so duplicate requests are skipped.

## Architecture

```mermaid
graph LR
    Client -->|POST /api/queues| API[Flask API]
    API -->|dedup check / skip| PG[(PostgreSQL)]
    API -->|enqueue| Redis[(Redis)]
    Redis -->|dequeue| Worker[BullMQ Worker]
    Worker -->|exec| gamdl
    gamdl -->|auth + FairPlay decrypt| Wrapper[wrapper-v2]
    Worker -->|mark downloaded| PG
```

## Quick Start (Docker Compose)

The included `compose.yaml` wires Kanade together with Redis, PostgreSQL, Bull Board, and a
wrapper-v2 sidecar — no host-side `uv` / Python / native deps required.

### 1. Prerequisites

- Docker 24+ with the `compose` plugin
- An active Apple Music subscription
- A wrapper-v2 image whose Apple-library `rootfs` you have already populated. wrapper-v2
  does **not** ship the Apple Music Android `.so` files; follow the
  [upstream README](https://github.com/glomatico/wrapper-v2) to extract them from an
  `.apk` / `.apkm` you provide, then point the `rootfs` volume in `compose.yaml` at the
  resulting tree.

### 2. Copy the templates

Both `config.ini` and `.env` are gitignored so your local edits stay out of version control.

```bash
cp config.example.ini config.ini   # gamdl + wrapper options
cp .env.example .env               # USERNAME / PASSWORD for the wrapper sidecar
```

Edit `.env` and set `USERNAME` / `PASSWORD` to an Apple ID + **app-specific password**
([account.apple.com](https://account.apple.com/) → Sign-In and Security → App-Specific
Passwords). Compose forwards them into the wrapper container as `WRAPPER_USERNAME` /
`WRAPPER_PASSWORD`; the sidecar signs in at startup and keeps a session cache in its
volume.

### 3. (Optional) Provide cookies for non-wrapper paths

When `use_wrapper = true` (the default), gamdl skips cookies entirely and goes through the
wrapper for everything. Cookies are only required if you want to disable the wrapper or
hit certain web-codec paths. To export them, use the
[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
Chrome extension on a logged-in `music.apple.com` tab and drop the file at `./cookies.txt`.

### 4. Bring the stack up

```bash
docker compose up -d                 # starts kanade, redis, postgres, wrapper, dashboard
docker compose logs -f kanade        # tail the API + worker
```

| URL | Service |
|---|---|
| <http://localhost:15100>        | Kanade API |
| <http://localhost:15100/docs>   | Scalar API docs |
| <http://localhost:13100>        | Bull Board (queue dashboard) |

### 5. Queue a download

```bash
curl -X POST http://localhost:15100/api/queues \
  -H "Content-Type: application/json" \
  -d '{"album_id": 1869843536}'
```

See the [API section](#api) for the full request / response shape.

## Configuration

`config.example.ini` documents every supported key inline. The Kanade-specific knobs worth
calling out:

- `use_wrapper = true` / `wrapper_url = http://wrapper:80` — route account, playback, and
  FairPlay decryption through the wrapper-v2 sidecar. Required for non-web codecs (ALAC,
  Atmos, AAC, AC-3, …) — wrapper-v2 reuses the Apple Music Android runtime to do the
  decryption that a `.wvd` Widevine device file can't.
- `artist_auto_select = all-albums` — required so artist URLs resolve non-interactively in
  the worker. Without it gamdl raises an interactive prompt that hangs the queue. Valid
  values: `main-albums`, `compilation-albums`, `live-albums`, `singles-eps`, `all-albums`,
  `top-songs`, `music-videos`.
- `song_codec_piority = alac` — note the upstream typo (`piority`, not `priority`). Common
  values: `alac`, `aac`, `aac-he`, `aac-web`, `aac-he-web`, `atmos`, `ac3`, `ask`. Web
  codecs work without the wrapper; everything else needs `use_wrapper = true`.
- `download_mode = nm3u8dlre` — `nm3u8dlre` (default, fastest) or `ytdlp`. The Kanade
  Docker image ships `N_m3u8DL-RE` on PATH so the default works out of the box.

See the [gamdl documentation](https://github.com/glomatico/gamdl) for the full option
reference.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `DATABASE_URL` | — | PostgreSQL DSN, e.g. `postgresql://kanade:kanade@postgres:5432/kanade` (required) |
| `ENV` | — | Set to `production` to use gunicorn |
| `USERNAME` | — | Apple ID forwarded to wrapper as `WRAPPER_USERNAME` (compose only; read from `.env`) |
| `PASSWORD` | — | App-specific password forwarded to wrapper as `WRAPPER_PASSWORD` (compose only; read from `.env`) |

## API

Interactive API documentation is available at `/docs` (Scalar UI).

### `POST /api/queues`

Queue an album or an artist for download. Provide **exactly one** of `album_id` or
`artist_id`.

```bash
# album
curl -X POST http://localhost:15100/api/queues \
  -H "Content-Type: application/json" \
  -d '{"album_id": 1869843536}'

# artist (downloads all albums, per artist_auto_select)
curl -X POST http://localhost:15100/api/queues \
  -H "Content-Type: application/json" \
  -d '{"artist_id": 909253}'
```

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `album_id` | `integer` | one of | Apple Music album ID (mutually exclusive with `artist_id`) |
| `artist_id` | `integer` | one of | Apple Music artist ID (mutually exclusive with `album_id`) |
| `options.overwrite` | `boolean` | — | Overwrite existing files and bypass the duplicate-skip check (default: `false`) |

**Response (queued):**

```json
{
  "id": "1",
  "name": "process",
  "data": {
    "url": "https://music.apple.com/jp/album/1869843536",
    "media_type": "album",
    "media_id": 1869843536,
    "overwrite": false
  },
  "timestamp": 1741430400000
}
```

**Response (already downloaded — skipped, not enqueued):**

```json
{
  "status": "skipped",
  "reason": "already downloaded",
  "media_type": "album",
  "media_id": 1869843536,
  "url": "https://music.apple.com/jp/album/1869843536"
}
```

A target is remembered by `(media_type, media_id)` after the worker finishes it. Send
`{"options": {"overwrite": true}}` to re-download a target that was already recorded.

### `GET /health`

Health check endpoint. Returns `{"status": "ok"}`.

### `GET /docs`

Scalar API documentation UI.

### `GET /openapi.json`

OpenAPI 3.1 specification.

## Compose services

| Service | Host port → container | Description |
|---|---|---|
| `kanade` | 15100 → 5000 | Kanade API + worker |
| `dashboard` | 13100 → 3000 | Bull Board (queue dashboard) |
| `redis` | — (internal) | BullMQ queue backend |
| `postgres` | — (internal) | Duplicate-skip store (`kanade` / `kanade` / `kanade`) |
| `wrapper` | — (internal, `:80`) | wrapper-v2 (Apple Music auth + FairPlay decryption) |

The `wrapper` service mounts a Docker volume named `rootfs` at `/app/rootfs`. Populate it
out-of-band with the Apple-library tree wrapper-v2 expects — see the
[wrapper-v2 README](https://github.com/glomatico/wrapper-v2) for the `extract-libs.sh` /
`stage-system.sh` workflow.

## Running without Compose

If you'd rather run Kanade against your own Redis / PostgreSQL / wrapper-v2, the published
image at `ghcr.io/qtmleap/kanade` (tagged on each `vX.Y.Z` release) handles the gamdl
runtime — `N_m3u8DL-RE`, `mp4decrypt`, `MP4Box`, `amdecrypt`, and `ffmpeg` are all baked
in. You provide:

- A reachable wrapper-v2 instance whose URL goes into `wrapper_url`.
- Redis (`REDIS_HOST` / `REDIS_PORT`).
- PostgreSQL (`DATABASE_URL`).

```bash
docker run --rm -it \
  -e REDIS_HOST=redis \
  -e DATABASE_URL=postgresql://kanade:kanade@postgres:5432/kanade \
  -v ./cookies.txt:/app/cookies.txt:ro \
  -v ./config.ini:/app/config.ini:ro \
  -v ./content:/app/content \
  -p 5000:5000 \
  ghcr.io/qtmleap/kanade:latest serve
```

Or run from source (requires Python 3.12+, plus the gamdl native deps on PATH):

```bash
uv sync
uv run python main.py serve
```

The API server starts on `http://localhost:5000`. Both the API and worker ensure the
PostgreSQL `downloads` table exists on startup, so a reachable `DATABASE_URL` is required.

## Development

The dev container includes all native dependencies pre-built. Open the project in VS Code
with the Dev Containers extension.

### VS Code Tasks

| Task | Description |
|---|---|
| `docker: build` | Build multi-arch Docker image |
| `docker: push` | Push image to registry |
| `version: bump` | Bump version in `pyproject.toml` |
| `release: deploy` | Bump → build → push |
