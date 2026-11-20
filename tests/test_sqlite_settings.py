"""Filesystem-aware SQLite PRAGMAs applied to the write engine."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from snakemake_logger_plugin_snkmt import log_handler
from snakemake_logger_plugin_snkmt.log_handler import (
    is_network_filesystem,
    sqliteLogHandler,
)


@pytest.fixture
def db_path():
    """Path to a fresh SQLite database file in a temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp, "snkmt.db").resolve()


def _make_handler(db_path):
    settings = SimpleNamespace(dryrun=False)
    return sqliteLogHandler(common_settings=settings, db_path=str(db_path))


def _pragma(handler, name):
    with handler.db_manager.engine.connect() as conn:
        return conn.execute(text(f"PRAGMA {name}")).scalar()


def test_network_filesystem_pragmas(db_path, monkeypatch):
    monkeypatch.setattr(log_handler, "is_network_filesystem", lambda path: True)
    handler = _make_handler(db_path)
    try:
        assert _pragma(handler, "journal_mode") == "persist"
        assert _pragma(handler, "synchronous") == 0
        assert _pragma(handler, "temp_store") == 2
        assert _pragma(handler, "cache_size") == -64000
        assert _pragma(handler, "busy_timeout") == 30000
    finally:
        handler.close()


def test_local_filesystem_pragmas(db_path, monkeypatch):
    monkeypatch.setattr(log_handler, "is_network_filesystem", lambda path: False)
    handler = _make_handler(db_path)
    try:
        assert _pragma(handler, "journal_mode") == "truncate"
        assert _pragma(handler, "synchronous") == 1
        assert _pragma(handler, "busy_timeout") == 30000
    finally:
        handler.close()


def test_is_network_filesystem_local_tmp(db_path):
    assert is_network_filesystem.__wrapped__(db_path) is False


@pytest.mark.parametrize("fstype", ["ceph", "fuse.ceph-fuse", "NFS4"])
def test_is_network_filesystem_detects_mount(db_path, monkeypatch, fstype):
    mounts = [
        SimpleNamespace(mountpoint="/", fstype="ext4"),
        SimpleNamespace(mountpoint=str(db_path.parent.parent), fstype=fstype),
    ]
    monkeypatch.setattr(log_handler.psutil, "disk_partitions", lambda all: mounts)
    assert is_network_filesystem.__wrapped__(db_path) is True


def test_is_network_filesystem_longest_mount_wins(db_path, monkeypatch):
    mounts = [
        SimpleNamespace(mountpoint=str(db_path.parent.parent), fstype="ceph"),
        SimpleNamespace(mountpoint=str(db_path.parent), fstype="ext4"),
    ]
    monkeypatch.setattr(log_handler.psutil, "disk_partitions", lambda all: mounts)
    assert is_network_filesystem.__wrapped__(db_path) is False
