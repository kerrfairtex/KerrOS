"""
ports/database_port.py
======================
DatabasePort — stable interface for local relational or structured database access.
"""

from typing import Any, List, Protocol


class DatabasePort(Protocol):
    def execute(self, query: str, params: tuple | None = None) -> None:
        """Execute a write/schema query that doesn't return rows."""
        ...

    def fetch_all(self, query: str, params: tuple | None = None) -> List[dict[str, Any]]:
        """Execute a query and fetch all results as a list of dicts."""
        ...

    def fetch_one(self, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        """Execute a query and fetch the first result as a dict."""
        ...
