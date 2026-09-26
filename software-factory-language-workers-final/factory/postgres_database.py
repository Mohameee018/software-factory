from __future__ import annotations

import re
import time
from contextlib import contextmanager

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PostgreSQL support requires the 'psycopg[binary]' package") from exc

from factory.database import Database, SCHEMA


def _qmarks(sql: str) -> str:
    return sql.replace("?", "%s")


def _postgres_sql(sql: str) -> str:
    sql = _qmarks(sql)
    sql = sql.replace("BEGIN IMMEDIATE", "BEGIN")
    sql = re.sub(
        r"julianday\(([^)]+)\)",
        r"EXTRACT(EPOCH FROM CAST(\1 AS TIMESTAMPTZ)) / 86400.0",
        sql,
    )
    return sql


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        return self._cursor.execute(_postgres_sql(sql), params)

    def executescript(self, script):
        return self._cursor.execute(script)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount


class PostgresDatabase(Database):
    """PostgreSQL persistence backend implementing the existing Database contract."""

    def __init__(self, database_url: str):
        self.path = database_url
        self.database_url = database_url
        self.init()

    @contextmanager
    def conn(self):
        last_error = None
        for attempt in range(3):
            try:
                with psycopg.connect(self.database_url, connect_timeout=15) as raw:
                    raw.autocommit = False
                    cursor = raw.cursor()
                    wrapped = PostgresCursor(cursor)
                    try:
                        yield wrapped
                        raw.commit()
                    except Exception:
                        raw.rollback()
                        raise
                    finally:
                        cursor.close()
                return
            except psycopg.OperationalError as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        if last_error:
            raise last_error

    def init(self):
        schema = SCHEMA
        schema = schema.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY"
        )
        schema = schema.replace(
            "INTEGER PRIMARY KEY", "BIGINT PRIMARY KEY"
        )
        with self.conn() as c:
            c.executescript(schema)
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version BIGINT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
            c.execute("INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT(version) DO NOTHING")
            # PostgreSQL has no PRAGMA table_info; inspect the information schema.
            cols = {
                r[0]
                for r in c.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='jobs'"
                ).fetchall()
            }
            if "worker_type" not in cols:
                c.execute(
                    "ALTER TABLE jobs ADD COLUMN worker_type TEXT NOT NULL DEFAULT 'generic'"
                )
            if "resume_at" not in cols:
                c.execute("ALTER TABLE jobs ADD COLUMN resume_at TEXT")

    def finding(self, pid, finding, security=False):
        table = "security_findings" if security else "review_findings"
        with self.conn() as c:
            c.execute(
                f"INSERT INTO {table}(id,project_id,severity,status,data_json) "
                "VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,"
                "severity=excluded.severity,status=excluded.status,data_json=excluded.data_json",
                (
                    finding.id,
                    pid,
                    finding.severity.value,
                    finding.status,
                    finding.model_dump_json(),
                ),
            )

    def approval(self, approval):
        with self.conn() as c:
            c.execute(
                "INSERT INTO approvals(id,project_id,task_id,status,created_at,data_json) "
                "VALUES(%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,"
                "task_id=excluded.task_id,status=excluded.status,"
                "created_at=excluded.created_at,data_json=excluded.data_json",
                (
                    approval.id,
                    approval.project_id,
                    approval.task_id,
                    approval.status.value,
                    approval.created_at.isoformat(),
                    approval.model_dump_json(),
                ),
            )
