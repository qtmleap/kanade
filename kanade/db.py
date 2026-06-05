import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


@contextmanager
def connect():
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        yield conn


def ensure_schema() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                media_type text NOT NULL,
                media_id bigint NOT NULL,
                url text NOT NULL,
                completed_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (media_type, media_id)
            )
            """
        )


def is_downloaded(media_type: str, media_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM downloads WHERE media_type = %s AND media_id = %s",
            (media_type, media_id),
        ).fetchone()
    return row is not None


def mark_downloaded(media_type: str, media_id: int, url: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO downloads (media_type, media_id, url)
            VALUES (%s, %s, %s)
            ON CONFLICT (media_type, media_id) DO NOTHING
            """,
            (media_type, media_id, url),
        )
