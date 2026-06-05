import asyncio
import os
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from bullmq import Queue

from kanade.db import is_downloaded

app = Flask(__name__)
CORS(app)

# ── OpenAPI Spec ──────────────────────────────────────────────────

OPENAPI_SPEC = {
    "openapi": "3.1.0",
    "info": {
        "title": "Kanade API",
        "description": "Apple Music download queue server",
        "version": "0.1.0",
    },
    "paths": {
        "/api/queues": {
            "post": {
                "summary": "Create a download job",
                "description": "Add an Apple Music album to the download queue.",
                "operationId": "createJob",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "description": "Provide exactly one of album_id or artist_id.",
                                "properties": {
                                    "album_id": {
                                        "type": "integer",
                                        "description": "Apple Music album ID. Mutually exclusive with artist_id.",
                                        "example": 1869843536,
                                    },
                                    "artist_id": {
                                        "type": "integer",
                                        "description": "Apple Music artist ID. Mutually exclusive with album_id.",
                                        "example": 909253,
                                    },
                                    "options": {
                                        "type": "object",
                                        "properties": {
                                            "overwrite": {
                                                "type": "boolean",
                                                "default": False,
                                                "description": "Overwrite existing files and bypass the duplicate-skip check",
                                            }
                                        },
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Job created, or skipped because the target is already downloaded",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "string"},
                                                "name": {"type": "string"},
                                                "data": {
                                                    "type": "object",
                                                    "properties": {
                                                        "url": {"type": "string"},
                                                        "media_type": {
                                                            "type": "string",
                                                            "enum": ["album", "artist"],
                                                        },
                                                        "media_id": {"type": "integer"},
                                                        "overwrite": {
                                                            "type": "boolean"
                                                        },
                                                    },
                                                },
                                                "timestamp": {"type": "integer"},
                                            },
                                        },
                                        {
                                            "type": "object",
                                            "properties": {
                                                "status": {
                                                    "type": "string",
                                                    "example": "skipped",
                                                },
                                                "reason": {
                                                    "type": "string",
                                                    "example": "already downloaded",
                                                },
                                                "media_type": {
                                                    "type": "string",
                                                    "enum": ["album", "artist"],
                                                },
                                                "media_id": {"type": "integer"},
                                                "url": {"type": "string"},
                                            },
                                        },
                                    ]
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Validation error",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"error": {"type": "string"}},
                                }
                            }
                        },
                    },
                },
            }
        },
        "/health": {
            "get": {
                "summary": "Health check",
                "operationId": "healthCheck",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"}
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    },
}

SCALAR_HTML = """<!doctype html>
<html>
<head>
    <title>Kanade API – Scalar</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body>
    <script id="api-reference" data-url="/openapi.json"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>
"""


@app.route("/openapi.json")
def openapi_spec():
    return jsonify(OPENAPI_SPEC)


@app.route("/docs")
def scalar_docs():
    return Response(SCALAR_HTML, content_type="text/html")


async def add_job(name: str, data: dict):
    queue = Queue(
        "kanade",
        {
            "connection": {
                "host": os.getenv("REDIS_HOST", "redis"),
                "port": int(os.getenv("REDIS_PORT", "6379")),
            }
        },
    )
    job = await queue.add(name, data)
    return {
        "id": job.id,
        "name": job.name,
        "data": job.data,
        "timestamp": job.timestamp,
    }


def enqueue(name: str, data: dict):
    return asyncio.run(add_job(name, data))


@app.route("/api/queues", methods=["POST"])
def create_job():
    data = request.get_json() or {}

    album_id = data.get("album_id")
    artist_id = data.get("artist_id")
    options = data.get("options")

    if album_id is None and artist_id is None:
        return jsonify(
            {"error": "exactly one of album_id or artist_id is required"}
        ), 400

    if album_id is not None and artist_id is not None:
        return jsonify({"error": "album_id and artist_id are mutually exclusive"}), 400

    if album_id is not None:
        media_type = "album"
        raw_id = album_id
    else:
        media_type = "artist"
        raw_id = artist_id

    try:
        media_id = int(raw_id)
    except (TypeError, ValueError):
        return jsonify({"error": f"{media_type}_id must be an integer"}), 400

    if options is None:
        overwrite = False
    elif isinstance(options, dict):
        overwrite = options.get("overwrite", False)
    else:
        return jsonify({"error": "options must be an object"}), 400

    if isinstance(overwrite, str):
        overwrite = overwrite.lower() in ["true", "1", "yes", "on"]
    else:
        overwrite = bool(overwrite)

    url = f"https://music.apple.com/jp/{media_type}/{media_id}"

    if not overwrite and is_downloaded(media_type, media_id):
        return jsonify(
            {
                "status": "skipped",
                "reason": "already downloaded",
                "media_type": media_type,
                "media_id": media_id,
                "url": url,
            }
        )

    job_info = enqueue(
        "process",
        {
            "url": url,
            "media_type": media_type,
            "media_id": media_id,
            "overwrite": overwrite,
        },
    )
    return jsonify(job_info)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
