import asyncio
import os
import re
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from bullmq import Queue

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
                                "required": ["album_id"],
                                "properties": {
                                    "album_id": {
                                        "type": "integer",
                                        "description": "Apple Music album ID",
                                        "example": 1869843536,
                                    },
                                    "options": {
                                        "type": "object",
                                        "properties": {
                                            "overwrite": {
                                                "type": "boolean",
                                                "default": False,
                                                "description": "Overwrite existing files",
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
                        "description": "Job created successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "name": {"type": "string"},
                                        "data": {
                                            "type": "object",
                                            "properties": {
                                                "url": {"type": "string"}
                                            },
                                        },
                                        "timestamp": {"type": "integer"},
                                    },
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
                                    "properties": {
                                        "error": {"type": "string"}
                                    },
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


@app.route('/openapi.json')
def openapi_spec():
    return jsonify(OPENAPI_SPEC)


@app.route('/docs')
def scalar_docs():
    return Response(SCALAR_HTML, content_type='text/html')

async def add_job(name: str, data: dict):
    queue = Queue("gamdl", {
      "connection": {
        "host": os.getenv("REDIS_HOST", "redis"),
        "port": int(os.getenv("REDIS_PORT", "6379"))
      }
    })
    job = await queue.add(name, data)
    return {
        "id": job.id,
        "name": job.name,
        "data": job.data,
        "timestamp": job.timestamp
    }

def enqueue(name: str, data: dict):
    return asyncio.run(add_job(name, data))

@app.route('/api/queues', methods=['POST'])
def create_job():
    data = request.get_json() or {}

    album_id = data.get('album_id')
    options = data.get('options')

    if album_id is None:
        return jsonify({"error": "album_id is required"}), 400

    try:
        album_id = int(album_id)
    except (TypeError, ValueError):
        return jsonify({"error": "album_id must be an integer"}), 400

    if options is None:
        overwrite = False
    elif isinstance(options, dict):
        overwrite = options.get('overwrite', False)
    else:
        return jsonify({"error": "options must be an object"}), 400

    if isinstance(overwrite, str):
        overwrite = overwrite.lower() in ['true', '1', 'yes', 'on']
    else:
        overwrite = bool(overwrite)

    job_info = enqueue("process", {"url": f"https://music.apple.com/jp/album/{album_id}" })
    return jsonify(job_info)

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
