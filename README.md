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

## Quick Start

### Prerequisites

- Python 3.12+
- Redis
- PostgreSQL
- A running [wrapper-v2](https://github.com/glomatico/wrapper-v2) instance (authenticated with an Apple ID)
- gamdl native dependencies: `N_m3u8DL-RE`, `mp4decrypt`, `MP4Box`, `amdecrypt`, `ffmpeg`

### Run locally

```bash
# Install dependencies
uv sync

# Start the server (API + worker)
uv run python main.py serve
```

The API server starts on `http://localhost:5000`. On startup both the API and worker
ensure the PostgreSQL `downloads` table exists, so a reachable `DATABASE_URL` is required.

### Configuration

Kanade ships two annotated templates. Copy them and edit in place — both `config.ini` and
`.env` are gitignored so your local edits stay out of version control.

```bash
cp config.example.ini config.ini   # gamdl + wrapper options
cp .env.example .env               # wrapper-v2 Apple ID for the compose stack
```

The Kanade-specific knobs worth knowing about:

- `use_wrapper` / `wrapper_url` — route account, playback and decryption through wrapper-v2
  (required for ALAC / lossless without a local `.wvd` file).
- `artist_auto_select = all-albums` — required so artist URLs resolve non-interactively in
  the worker. Without it gamdl raises an interactive prompt that hangs the queue. Valid
  values: `main-albums`, `compilation-albums`, `live-albums`, `singles-eps`, `all-albums`,
  `top-songs`, `music-videos`.
- `cookies_path` — Netscape-format cookies exported from a logged-in Apple Music web
  session. The [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
  Chrome extension works; export from `music.apple.com` and drop the file at the path
  configured here (`./cookies.txt` by default, mounted read-only into the container).

[`config.example.ini`](./config.example.ini) documents every supported key inline. See
also the [gamdl documentation](https://github.com/glomatico/gamdl) for upstream details.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `DATABASE_URL` | — | PostgreSQL DSN, e.g. `postgresql://kanade:kanade@postgres:5432/kanade` (required) |
| `ENV` | — | Set to `production` to use gunicorn |
| `USERNAME` | — | Apple ID for the wrapper-v2 sidecar (compose only; read from `.env`) |
| `PASSWORD` | — | App-specific password for `USERNAME` (compose only; read from `.env`) |

## API

Interactive API documentation is available at `/docs` (Scalar UI).

### `POST /api/queues`

Queue an album or an artist for download. Provide **exactly one** of `album_id` or
`artist_id`.

```bash
# album
curl -X POST http://localhost:5000/api/queues \
  -H "Content-Type: application/json" \
  -d '{"album_id": 1869843536}'

# artist (downloads all albums, per artist_auto_select)
curl -X POST http://localhost:5000/api/queues \
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

## Docker

### Build

```bash
docker buildx build -t kanade .
```

### Run

```bash
docker run --rm -it \
  -e REDIS_HOST=redis \
  -e DATABASE_URL=postgresql://kanade:kanade@postgres:5432/kanade \
  -v ./cookies.txt:/app/cookies.txt:ro \
  -v ./config.ini:/app/config.ini:ro \
  -p 5000:5000 \
  kanade serve
```

Pre-built images are published to `ghcr.io/qtmleap/kanade` on each `vX.Y.Z` tag.

## Development

The dev container includes all native dependencies pre-built. Open the project in VS Code
with the Dev Containers extension.

### Services (compose)

| Service | Host port → container | Description |
|---|---|---|
| `kanade` / `app` | 15100 → 5000 | Kanade API + worker |
| `dashboard` | 13100 → 3000 | Bull Board (queue dashboard) |
| `redis` | 6379 | Redis queue backend |
| `postgres` | 5432 (internal) | Duplicate-skip store |
| `wrapper` | — | wrapper-v2 (Apple Music auth + decryption) |

### VS Code Tasks

| Task | Description |
|---|---|
| `docker: build` | Build multi-arch Docker image |
| `docker: push` | Push image to registry |
| `version: bump` | Bump version in `pyproject.toml` |
| `release: deploy` | Bump → build → push |
