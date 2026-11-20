import functools
import logging
import os
from contextlib import contextmanager
import psutil
from sqlalchemy import event
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional, Generator, Any
from logging import Handler, LogRecord
from datetime import datetime

from snakemake_interface_logger_plugins.common import LogEvent
from snakemake_interface_logger_plugins.settings import OutputSettingsLoggerInterface
from snkmt.core.db.session import Database
from snkmt.core.db.version import DatabaseVersionError
from snkmt.core.models.workflow import Workflow
from snkmt.core.models.error import Error
from snkmt.types.enums import Status


from snakemake_logger_plugin_snkmt.event_handlers import (
    EventHandler,
    WorkflowStartedHandler,
    JobInfoHandler,
    JobStartedHandler,
    JobFinishedHandler,
    JobErrorHandler,
    RuleGraphHandler,
    GroupInfoHandler,
    GroupErrorHandler,
    ErrorHandler,
    RunInfoHandler,
    ShellCmdHandler,
    ProgressHandler,
)


# Snakemake's list plus ceph-fuse, which Snakemake misses.
NETWORK_FS_TYPES = frozenset(
    {
        "afs",
        "beegfs",
        "ceph",
        "cifs",
        "fhgfs",
        "fuse.ceph-fuse",
        "fuse.juicefs",
        "fuse.sshfs",
        "glusterfs",
        "gpfs",
        "lustre",
        "nfs",
        "nfs3",
        "nfs4",
        "orangefs",
        "pvfs2",
        "smbfs",
    }
)


@functools.cache
def is_network_filesystem(path: Path | str) -> bool:
    """Whether ``path`` resides on a network filesystem (modelled on Snakemake)."""
    if os.name != "posix":
        return False
    try:
        path_obj = Path(path).resolve()
        best_match = max(
            (
                mount
                for mount in psutil.disk_partitions(all=True)
                if path_obj.is_relative_to(Path(mount.mountpoint).resolve())
            ),
            key=lambda part: len(Path(part.mountpoint).resolve().parts),
            default=None,
        )
        fstype = best_match.fstype if best_match else ""
        return fstype.casefold() in NETWORK_FS_TYPES
    except (PermissionError, OSError):
        return False


class sqliteLogHandler(Handler):
    """Log handler that stores Snakemake events in a SQLite database.

    This handler processes log records from Snakemake and uses
    event parsers and handlers to store them in a SQLite database.
    """

    # How long SQLite waits for a held lock to clear before raising "database
    # is locked". Generous, since single-row writes commit in milliseconds even
    # with many concurrent Snakemake instances.
    SQLITE_BUSY_TIMEOUT_MS = 30_000

    def __init__(
        self,
        common_settings: OutputSettingsLoggerInterface,
        db_path: Optional[str] = None,
    ):
        """Initialize the SQLite log handler.

        Args:
            db_path: Path to the SQLite database file. If None, a default path will be used.
        """
        super().__init__()

        self.db_manager = Database(db_path=db_path, auto_migrate=True, create_db=True)
        self._configure_sqlite(self.db_manager.engine)
        self.common_settings = common_settings

        self.event_handlers: dict[str, EventHandler] = {  # type: ignore
            LogEvent.WORKFLOW_STARTED.value: WorkflowStartedHandler(),
            LogEvent.JOB_INFO.value: JobInfoHandler(),
            LogEvent.JOB_STARTED.value: JobStartedHandler(),
            LogEvent.JOB_FINISHED.value: JobFinishedHandler(),
            LogEvent.JOB_ERROR.value: JobErrorHandler(),
            LogEvent.RULEGRAPH.value: RuleGraphHandler(),
            LogEvent.GROUP_INFO.value: GroupInfoHandler(),
            LogEvent.GROUP_ERROR.value: GroupErrorHandler(),
            LogEvent.ERROR.value: ErrorHandler(),
            LogEvent.RUN_INFO.value: RunInfoHandler(),
            LogEvent.SHELLCMD.value: ShellCmdHandler(),
            LogEvent.PROGRESS.value: ProgressHandler(),
        }

        self.context = {
            "current_workflow_id": None,
            "dryrun": self.common_settings.dryrun,
        }

    def _configure_sqlite(self, engine: Any) -> None:
        """Set concurrency and filesystem-aware PRAGMAs on every pooled connection.

        ``busy_timeout`` makes a writer wait for the lock; Python's sqlite3 defaults to only 5 s.
        The journal pragmas follow Snakemake's persistence db:
        the default DELETE journal creates, fsyncs and unlinks a file per commit,
        which is costly metadata traffic on network filesystems.

        WAL mode is intentionally not enabled:
        the database may live on a network filesystem (NFS/Lustre/GPFS),
        where WAL's shared-memory index is unreliable.
        """
        if is_network_filesystem(self.db_manager.db_path):
            pragmas = [
                "journal_mode=PERSIST",
                "synchronous=OFF",
                "temp_store=MEMORY",
                "cache_size=-64000",
            ]
        else:
            pragmas = ["journal_mode=TRUNCATE", "synchronous=NORMAL"]
        pragmas.append(f"busy_timeout={self.SQLITE_BUSY_TIMEOUT_MS}")

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            try:
                for pragma in pragmas:
                    cursor.execute(f"PRAGMA {pragma}")
            finally:
                cursor.close()

    @contextmanager
    def session_scope(self) -> Generator[Session, Any, Any]:
        """Provide a transactional scope around a series of operations."""
        session = self.db_manager.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.handleError(
                logging.LogRecord(
                    name="snkmtLogHandler",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg=f"Database error: {str(e)}",
                    args=(),
                    exc_info=None,
                )
            )
        finally:
            session.close()

    def emit(self, record: LogRecord) -> None:
        """Process a log record and store it in the database.

        Args:
            record: The log record to process.
        """
        try:
            event = getattr(record, "event", None)

            if not event:
                return

            event_value = event.value if hasattr(event, "value") else str(event).lower()

            handler = self.event_handlers.get(event_value)
            if not handler:
                return

            with self.session_scope() as session:
                handler.handle(record, session, self.context)

        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the handler and update the workflow status."""
        # if db needs migrations, alembic messes with logging config and context is not set so this fails
        try:
            if hasattr(self, "context") and self.context.get("current_workflow_id"):
                try:
                    with self.session_scope() as session:
                        workflow = (
                            session.query(Workflow)
                            .filter(Workflow.id == self.context["current_workflow_id"])
                            .first()
                        )
                        error = (
                            session.query(Error)
                            .filter(
                                Error.workflow_id == self.context["current_workflow_id"]
                            )
                            .first()
                        )

                        if workflow:
                            workflow.status = Status.UNKNOWN
                            workflow.end_time = datetime.utcnow()

                            if error:
                                workflow.status = Status.ERROR
                            elif workflow.progress >= 1:
                                workflow.status = Status.SUCCESS

                except Exception as e:
                    self.handleError(
                        logging.LogRecord(
                            name="snkmtLogHandler",
                            level=logging.ERROR,
                            pathname="",
                            lineno=0,
                            msg=f"Error closing workflow: {str(e)}",
                            args=(),
                            exc_info=None,
                        )
                    )
        except DatabaseVersionError:
            pass

        super().close()
