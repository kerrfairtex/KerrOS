"""
ports/search_port.py
====================
SearchPort — stable interface for web search engines.
"""

from typing import Any, List, Protocol


class SearchPort(Protocol):
    def search(self, query: str, max_results: int = 5) -> List[dict[str, Any]]:
        """Perform a web search and return structured search result dictionaries."""
        ...
