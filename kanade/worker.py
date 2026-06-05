import asyncio
import os
import re
import subprocess
from bullmq import Worker
from kanade.db import mark_downloaded
from kanade.tasks import run_gamdl

# ANSI カラーコードを除去する正規表現
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def get_redis_connection():
    return {
        "host": os.getenv("REDIS_HOST", "redis"),
        "port": int(os.getenv("REDIS_PORT", "6379")),
    }


async def handler(job, token):
    """ジョブを処理するハンドラー"""
    url = job.data.get("url")

    if not url:
        await job.log("Error: url is missing")
        return {"status": "error", "message": "url is required"}

    prefix = f"[job:{job.id}]"
    print(f"{prefix} Starting gamdl for {url}", flush=True)
    await job.log(f"Starting gamdl for {url}")

    try:
        for line in run_gamdl(url):
            clean = strip_ansi(line)
            if clean:
                print(f"{prefix} {clean}", flush=True)
                await job.log(clean)

        media_type = job.data.get("media_type")
        media_id = job.data.get("media_id")
        if media_type is not None and media_id is not None:
            mark_downloaded(media_type, int(media_id), url)
            await job.log(f"Marked {media_type}:{media_id} as downloaded")
        else:
            await job.log(
                "Skipping download mark because media_type/media_id are missing"
            )

        print(f"{prefix} Completed successfully", flush=True)
        await job.log("Completed successfully")
        return {"status": "completed", "url": url}

    except subprocess.CalledProcessError as e:
        msg = f"Failed with exit code {e.returncode}"
        print(f"{prefix} {msg}", flush=True)
        await job.log(msg)
        raise e
    except Exception as e:
        msg = f"Error: {str(e)}"
        print(f"{prefix} {msg}", flush=True)
        await job.log(msg)
        raise e


async def main():
    # kept bound so the worker is not garbage-collected while the loop runs
    _worker = Worker("kanade", handler, {"connection": get_redis_connection()})

    print("Worker started, waiting for jobs...", flush=True)

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
