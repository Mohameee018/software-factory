from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager


def _lock_key(name: str) -> int:
    # Stable 63-bit PostgreSQL advisory-lock key.
    raw = hashlib.sha256(name.encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, "big", signed=False) & ((1 << 63) - 1)


@contextmanager
def singleton_service_lock(db, name: str, wait_seconds: int = 90):
    """Hold a process/service singleton lock for the lifetime of a service.

    PostgreSQL uses an advisory lock, which is shared across Railway deployments.
    SQLite uses an OS file lock, which is shared by processes using the same volume.
    """
    url = getattr(db, "database_url", "")
    if url:
        import psycopg

        conn = psycopg.connect(url, connect_timeout=15)
        deadline = time.monotonic() + wait_seconds
        acquired = False
        key = _lock_key(name)
        while time.monotonic() < deadline:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
                acquired = bool(cur.fetchone()[0])
            if acquired:
                break
            time.sleep(2)
        if not acquired:
            conn.close()
            raise RuntimeError(
                f"Another {name} instance is already running; "
                f"singleton lock was not acquired within {wait_seconds}s."
            )
        try:
            yield
        finally:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (key,))
                conn.commit()
            finally:
                conn.close()

    # SQLite/local development fallback.
    import fcntl
    from pathlib import Path

    lock_root = Path(getattr(db, "path", "/tmp")).parent
    lock_root.mkdir(parents=True, exist_ok=True)
    handle = (lock_root / f".{name}.lock").open("a+")
    try:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"Another {name} instance is already running; "
                        f"singleton lock was not acquired within {wait_seconds}s."
                    )
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
