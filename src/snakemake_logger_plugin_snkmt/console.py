from typing import List, Tuple
from rich import print
from rich.console import Console
from rich.table import Table
from rich import box

console = Console(stderr=True, width=150)


class OptionsTable(Table):
    def __init__(
        self, rows: List[Tuple[str, str]], detail_style="", value_style="", **kwargs
    ):
        super().__init__(
            show_header=False,
            pad_edge=False,
            show_edge=False,
            padding=(0, 0),
            box=box.SIMPLE,
            **kwargs,
        )
        self.add_column("detail", justify="left", style=detail_style, no_wrap=True)
        self.add_column("value", justify="left", style=value_style)
        for row in rows:
            self.add_row(*row)
