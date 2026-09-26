from pathlib import Path

from factory.database import Database
from factory.service_lock import _lock_key, singleton_service_lock


def test_lock_key_is_stable_and_postgres_safe():
    key1 = _lock_key("telegram-polling")
    key2 = _lock_key("telegram-polling")
    assert key1 == key2
    assert 0 <= key1 < 2**63


def test_sqlite_singleton_lock(tmp_path):
    db = Database(Path(tmp_path) / "factory.db")
    with singleton_service_lock(db, "test-service", wait_seconds=0):
        # The lock is held for the entire service lifetime.
        assert (Path(tmp_path) / ".test-service.lock").exists()
