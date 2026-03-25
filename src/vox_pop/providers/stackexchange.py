"""Stack Exchange provider via the official API.

Tier 1 — free, 300 requests/day without a key, 10,000/day with a
free registered key. Covers 180+ communities.
Supports time filtering for perspective searches.

Docs: https://api.stackexchange.com/docs
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

_BASE = "https://api.stackexchange.com/2.3"
_TIMEOUT = 15.0

SITE_ROUTES: dict[str, list[str]] = {
    "programming": ["stackoverflow"],
    "code": ["stackoverflow"],
    "python": ["stackoverflow"],
    "javascript": ["stackoverflow"],
    "rust": ["stackoverflow"],
    "go": ["stackoverflow"],
    "server": ["serverfault"],
    "linux": ["unix", "askubuntu"],
    "fitness": ["fitness"],
    "health": ["health"],
    "cooking": ["cooking"],
    "travel": ["travel"],
    "money": ["money"],
    "finance": ["money"],
    "security": ["security"],
    "math": ["math"],
    "science": ["physics", "chemistry", "biology"],
    "gaming": ["gaming"],
    "workplace": ["workplace"],
    "career": ["workplace"],
    "diy": ["diy"],
    "photo": ["photo"],
}


class StackExchangeProvider(Provider):
    """Search across Stack Exchange sites."""

    name = "stackexchange"
    supports_time_filter = True

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        sites: list[str] | None = None,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        if not sites:
            sites = self._route_sites(query)

        all_results: list[OpinionResult] = []
        errors: list[str] = []

        for site in sites[:3]:
            try:
                results = await self._search_site(
                    query, site, limit=limit, time_range=time_range,
                )
                all_results.extend(results)
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{site}: {exc}")

        if not all_results and errors:
            return SearchResults(
                platform=self.name,
                query=query,
                error="; ".join(errors),
                time_range=time_range.value,
            )

        all_results.sort(key=lambda r: r.score, reverse=True)

        return SearchResults(
            platform=self.name,
            query=query,
            results=all_results[:limit],
            total_found=len(all_results),
            time_range=time_range.value,
        )

    async def get_thread(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        site: str = "stackoverflow",
        **kwargs: Any,
    ) -> list[OpinionResult]:
        """Fetch answers for a Stack Exchange question."""
        params: dict[str, Any] = {
            "order": "desc",
            "sort": "votes",
            "site": site,
            "filter": "withbody",
            "pagesize": min(limit, 100),
        }
        if self._api_key:
            params["key"] = self._api_key

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE}/questions/{thread_id}/answers", params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            OpinionResult(
                text=strip_html(ans.get("body", "")),
                platform=f"stackexchange/{site}",
                url=ans.get("link", ""),
                author=ans.get("owner", {}).get("display_name", ""),
                score=safe_int(ans.get("score")),
                created_at=str(ans.get("creation_date", "")),
            )
            for ans in data.get("items", [])
        ]

    # ── Internal helpers ────────────────────────────────────────

    async def _search_site(
        self,
        query: str,
        site: str,
        *,
        limit: int = 10,
        time_range: TimeRange = TimeRange.ALL,
    ) -> list[OpinionResult]:
        params: dict[str, Any] = {
            "order": "desc",
            "sort": "relevance",
            "intitle": query,
            "site": site,
            "pagesize": min(limit, 100),
        }
        if self._api_key:
            params["key"] = self._api_key

        # Apply time filter
        after, before = time_range.to_timestamps()
        if after is not None:
            params["fromdate"] = after
        if before is not None:
            params["todate"] = before

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[OpinionResult] = []
        for item in data.get("items", []):
            created = item.get("creation_date", 0)
            if isinstance(created, (int, float)) and created > 0:
                from datetime import datetime, timezone
                created_at = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                created_at = str(created)

            results.append(
                OpinionResult(
                    text=strip_html(item.get("title", "")),
                    platform=f"stackexchange/{site}",
                    url=item.get("link", ""),
                    author=item.get("owner", {}).get("display_name", ""),
                    score=safe_int(item.get("score")),
                    num_replies=safe_int(item.get("answer_count")),
                    created_at=created_at,
                    metadata={
                        "is_answered": item.get("is_answered", False),
                        "view_count": safe_int(item.get("view_count")),
                        "tags": item.get("tags", []),
                    },
                )
            )

        return results

    @staticmethod
    def _route_sites(query: str) -> list[str]:
        query_lower = query.lower()
        sites: list[str] = []
        for keyword, site_list in SITE_ROUTES.items():
            if keyword in query_lower:
                for s in site_list:
                    if s not in sites:
                        sites.append(s)
        return sites if sites else ["stackoverflow"]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{_BASE}/info", params={"site": "stackoverflow"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
