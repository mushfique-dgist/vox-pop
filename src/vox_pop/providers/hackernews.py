"""HackerNews provider via the Algolia Search API.

Tier 1 — completely free, no auth, no rate-limit issues.
Supports time filtering for perspective searches.
Docs: https://hn.algolia.com/api
"""

from __future__ import annotations

from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    safe_int,
    strip_html,
)

_BASE = "https://hn.algolia.com/api/v1"
_ITEM_URL = "https://news.ycombinator.com/item?id={}"
_TIMEOUT = 15.0


class HackerNewsProvider(Provider):
    """Search HackerNews stories and comments via Algolia."""

    name = "hackernews"
    supports_threads = True
    supports_time_filter = True

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        sort: str = "relevance",
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        endpoint = (
            f"{_BASE}/search" if sort == "relevance" else f"{_BASE}/search_by_date"
        )
        params: dict[str, Any] = {
            "query": query,
            "hitsPerPage": min(limit, 50),
            "tags": "(story,poll)",
        }

        # Apply time filter
        after, before = time_range.to_timestamps()
        filters: list[str] = []
        if after is not None:
            filters.append(f"created_at_i>{after}")
        if before is not None:
            filters.append(f"created_at_i<{before}")
        if filters:
            params["numericFilters"] = ",".join(filters)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(endpoint, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=str(exc),
                time_range=time_range.value,
            )

        results: list[OpinionResult] = []
        for hit in data.get("hits", []):
            obj_id = hit.get("objectID", "")
            text = hit.get("story_text") or hit.get("title", "")
            results.append(
                OpinionResult(
                    text=strip_html(text),
                    platform=self.name,
                    url=_ITEM_URL.format(obj_id),
                    author=hit.get("author", ""),
                    score=safe_int(hit.get("points")),
                    num_replies=safe_int(hit.get("num_comments")),
                    created_at=hit.get("created_at", ""),
                )
            )

        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=safe_int(data.get("nbHits")),
            time_range=time_range.value,
        )

    async def get_thread(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[OpinionResult]:
        """Fetch comments on a specific HN story."""
        params: dict[str, Any] = {
            "tags": f"comment,story_{thread_id}",
            "hitsPerPage": min(limit, 100),
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        return [
            OpinionResult(
                text=strip_html(hit.get("comment_text", "")),
                platform=self.name,
                url=_ITEM_URL.format(hit.get("objectID", "")),
                author=hit.get("author", ""),
                score=safe_int(hit.get("points")),
                created_at=hit.get("created_at", ""),
            )
            for hit in data.get("hits", [])
            if hit.get("comment_text")
        ]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{_BASE}/search", params={"query": "test", "hitsPerPage": 1},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
