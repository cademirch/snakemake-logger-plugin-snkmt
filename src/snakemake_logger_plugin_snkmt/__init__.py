from snakemake_interface_logger_plugins.base import LogHandlerBase
from snakemake_interface_logger_plugins.settings import LogHandlerSettingsBase
from snakemake_logger_plugin_snkmt.log_handler import sqliteLogHandler
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class LogHandlerSettings(LogHandlerSettingsBase):
    db: Optional[Path] = field(
        default=None,
        metadata={
            "help": "Set absolute path for database file. ",
            "env_var": False,
            "required": False,
        },
    )


class LogHandler(LogHandlerBase, sqliteLogHandler):
    def __post_init__(self) -> None:
        sqliteLogHandler.__init__(
            self,
            self.common_settings,
            db_path=self.settings.db,  # type: ignore
        )

    @property
    def writes_to_stream(self) -> bool:
        """
        Whether this plugin writes to stderr/stdout
        """
        return False

    @property
    def writes_to_file(self) -> bool:
        """
        Whether this plugin writes to a file
        """
        return False

    @property
    def has_filter(self) -> bool:
        """
        Whether this plugin attaches its own filter
        """
        return True

    @property
    def has_formatter(self) -> bool:
        """
        Whether this plugin attaches its own formatter
        """
        return True

    @property
    def needs_rulegraph(self) -> bool:
        """
        Whether this plugin requires the DAG rulegraph.
        """
        return True
