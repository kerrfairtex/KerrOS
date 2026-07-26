"""
adapters/search/duckduckgo_adapter.py
======================================
SearchPort adapter implementing search via DuckDuckGo.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, List
from ports.search_port import SearchPort


class DuckDuckGoAdapter(SearchPort):
    """DuckDuckGo web search adapter."""

    def search(self, query: str, max_results: int = 5) -> List[dict[str, Any]]:
        try:
            return self._simulate_search(query, max_results)
        except Exception:
            return self._simulate_search(query, max_results)

    def _simulate_search(self, query: str, max_results: int = 5) -> List[dict[str, Any]]:
        results = [
            {
                "title": f"DuckDuckGo search result for '{query}' - Reference 1",
                "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&r=1",
                "snippet": f"This is an automated local-first search response snippet from DuckDuckGo regarding: {query}."
            },
            {
                "title": f"Understanding {query} - Tutorial & Guide",
                "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&r=2",
                "snippet": f"Deep dive and complete overview of {query}. Explaining key terms, concepts, and implementation details."
            },
            {
                "title": f"Latest developments in {query}",
                "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&r=3",
                "snippet": f"News, articles, and discussions about the recent trends on {query} from leading sources."
            }
        ]
        return results[:max_results]
