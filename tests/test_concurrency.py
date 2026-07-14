"""Concurrency tests: several Snakemake instances writing the same DB.

When two Snakemake runs log to the same SQLite file, one holds the write lock
while the other tries to write. SQLite defaults to a busy timeout of 0, so the
second write fails immediately with "database is locked". The handler sets
``PRAGMA busy_timeout`` so the write waits for the lock instead.
"""

import sqlite3
import tempfile
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from snkmt.core.models.workflow import Workflow
from snkmt.types.enums import Status

from snakemake_logger_plugin_snkmt.log_handler import sqliteLogHandler


@pytest.fixture
def db_path():
    """Path to a fresh SQLite database file in a temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp, "snkmt.db").resolve()


def _make_handler(db_path):
    """A handler wired to ``db_path`` with a minimal settings stub."""
    settings = SimpleNamespace(dryrun=False)
    return sqliteLogHandler(common_settings=settings, db_path=str(db_path))


class _LockHolder:
    """Hold SQLite's write lock on ``db_path``, then auto-release after a delay.

    Uses a raw sqlite3 connection with ``BEGIN IMMEDIATE`` to take the RESERVED
    lock, mimicking another Snakemake instance mid-write. The lock is released
    automatically ``hold_seconds`` after acquisition (from the holder's own
    thread), so a writer blocking on it in the main thread proceeds once the
    delay elapses rather than deadlocking.
    """

    def __init__(self, db_path, hold_seconds):
        self.db_path = db_path
        self.hold_seconds = hold_seconds
        self._acquired = threading.Event()
        self._thread = threading.Thread(target=self._run)

    def _run(self):
        conn = sqlite3.connect(str(self.db_path), timeout=60, isolation_level=None)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA user_version = 1")  # a write, so the lock is held
        self._acquired.set()
        # Hold, then release. A concurrent writer with busy_timeout set blocks
        # here and succeeds; one without it has already failed instantly.
        threading.Event().wait(self.hold_seconds)
        conn.commit()
        conn.close()

    def __enter__(self):
        self._thread.start()
        assert self._acquired.wait(timeout=10), "lock was never acquired"
        return self

    def __exit__(self, *_exc):
        self._thread.join(timeout=30)


def test_busy_timeout_pragma_is_set(db_path):
    """Every connection from the handler engine has the busy timeout applied."""
    handler = _make_handler(db_path)
    try:
        with handler.db_manager.engine.connect() as conn:
            (timeout,) = conn.execute(text("PRAGMA busy_timeout")).one()
        assert timeout == sqliteLogHandler.SQLITE_BUSY_TIMEOUT_MS
    finally:
        handler.close()


def test_write_lock_reproduces_database_locked(db_path):
    """Without a busy timeout, a held write lock triggers the original error."""
    # Create the schema via the handler, then talk to the same file through a
    # plain engine with the default busy_timeout of 0 (i.e. the unpatched path).
    handler = _make_handler(db_path)
    handler.close()

    raw_engine = create_engine(f"sqlite:///{db_path}")
    # Hold long enough that the unpatched write cannot possibly succeed within
    # its (zero) timeout; it must fail immediately rather than wait this out.
    with _LockHolder(db_path, hold_seconds=2.0):
        with pytest.raises(Exception) as excinfo:
            with raw_engine.connect() as conn:
                conn.execute(text("PRAGMA busy_timeout = 0"))
                conn.execute(
                    text(
                        "INSERT INTO workflows (id, started_at, updated_at, "
                        "status, dryrun, total_job_count, jobs_finished) "
                        "VALUES (:id, datetime('now'), datetime('now'), "
                        "'RUNNING', 0, 0, 0)"
                    ),
                    {"id": uuid.uuid4().hex},
                )
                conn.commit()
    assert "database is locked" in str(excinfo.value).lower()
    raw_engine.dispose()


def test_handler_waits_out_concurrent_write_lock(db_path):
    """With the busy timeout set, the handler's write waits and then succeeds."""
    handler = _make_handler(db_path)
    workflow_uuid = uuid.uuid4()
    try:
        # Hold the write lock from another "instance" for a beat, then write
        # through the handler's session. busy_timeout makes the write block
        # until the holder releases, instead of raising "database is locked".
        with _LockHolder(db_path, hold_seconds=1.0):
            with handler.session_scope() as session:
                session.add(
                    Workflow(id=workflow_uuid, dryrun=False, status=Status.RUNNING)
                )

        # session_scope swallows DB errors via handleError, so assert the row
        # actually landed rather than merely that no exception propagated.
        with handler.db_manager.engine.connect() as conn:
            (count,) = conn.execute(
                text("SELECT count(*) FROM workflows WHERE id = :id"),
                {"id": workflow_uuid.hex},
            ).one()
        assert count == 1, "workflow was not persisted despite the busy timeout"
    finally:
        handler.close()
