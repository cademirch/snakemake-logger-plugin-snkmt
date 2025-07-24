import logging
from contextlib import contextmanager
from sqlalchemy.orm import Session
from typing import Optional, Generator, Any
from logging import Handler, LogRecord
from datetime import datetime

from snakemake_interface_logger_plugins.common import LogEvent
from snakemake_interface_logger_plugins.settings import OutputSettingsLoggerInterface
from snkmt.db.session import Database
from snkmt.db.models.workflow import Workflow
from snkmt.db.models.error import Error
from snkmt.db.models.enums import Status
from snkmt.version import VERSION as snkmt_version
from importlib.metadata import version

from snakemake_logger_plugin_snkmt.event_handlers import (
    EventHandler,
)

from snakemake_logger_plugin_snkmt.console import OptionsTable, console


class sqliteLogHandler(Handler):
    """Log handler that stores Snakemake events in a SQLite database.

    This handler processes log records from Snakemake and uses
    event parsers and handlers to store them in a SQLite database.
    """

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

        self.db_manager = Database(db_path=db_path, auto_migrate=False, create_db=True)
        self.common_settings = common_settings

        self.event_handler = EventHandler(dryrun=common_settings.dryrun)

        snkmt_table = OptionsTable(
            [
                ("snkmt Version:", snkmt_version),
                ("Plugin Version:", version("snakemake_logger_plugin_snkmt")),
                ("Database:", self.db_manager.db_path),
            ],
            value_style="dim",
        )
        console.print("[bold]snkmt")
        console.print(snkmt_table)
        console.print("")
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
            event: Optional[LogEvent] = getattr(record, "event", None)

            if not event:
                return

            with self.session_scope() as session:
                self.event_handler.handle(event, record, session)

        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the handler and update the workflow status."""

        if self.event_handler.current_workflow_id:
            try:
                with self.session_scope() as session:
                    workflow = (
                        session.query(Workflow)
                        .filter(Workflow.id == self.event_handler.current_workflow_id)
                        .first()
                    )
                    error = (
                        session.query(Error)
                        .filter(
                            Error.workflow_id == self.event_handler.current_workflow_id
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

        super().close()
