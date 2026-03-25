"""4chan provider via the official read-only JSON API.

Tier 1 — official API, maintained since 2012, zero auth.
Docs: https://github.com/4chan/4chan-API

Limitations:
  - No server-side full-text search. We fetch board catalogs and
    filter locally, so searches only cover *active* threads.
  - Rate limit: 1 request/second per the API docs. We respect this
    with a simple concurrency guard.

For historical/archived search, 4plebs or archived.moe could be
added as Tier 2 fallbacks in a future version.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    safe_int,
    strip_html,
)

_BASE = "https://a.4cdn.org"
_THREAD_URL = "https://boards.4chan.org/{board}/thread/{no}"
_TIMEOUT = 15.0

# Mapping from topic keywords to relevant boards.
# Used when no explicit board is given.
BOARD_ROUTES: dict[str, list[str]] = {
    "tech": ["g"],
    "programming": ["g"],
    "software": ["g"],
    "ai": ["g"],
    "fitness": ["fit"],
    "health": ["fit"],
    "diet": ["fit", "ck"],
    "skincare": ["fit"],
    "cooking": ["ck"],
    "food": ["ck"],
    "travel": ["trv"],
    "science": ["sci"],
    "math": ["sci"],
    "business": ["biz"],
    "finance": ["biz"],
    "crypto": ["biz"],
    "fashion": ["fa"],
    "advice": ["adv"],
    "career": ["adv"],
    "anime": ["a"],
    "gaming": ["v"],
    "music": ["mu"],
    "film": ["tv"],
    "diy": ["diy"],
    "auto": ["o"],
    "photography": ["p"],
    "politics": ["pol"],
}

# 4chan asks for max 1 request/second.
_rate_lock = asyncio.Lock()


class FourChanProvider(Provider):
    """Search 4chan boards via catalog filtering."""

    name = "4chan"

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        boards: list[str] | None = None,
        **kwargs: Any,
    ) -> SearchResults:
        if not boards:
            boards = self._route_boards(query)

        all_results: list[OpinionResult] = []
        errors: list[str] = []

        for board in boards[:3]:  # Cap at 3 boards to limit requests
            try:
                results = await self._search_board(query, board, limit=limit)
                all_results.extend(results)
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"/{board}/: {exc}")

        if not all_results and errors:
            return SearchResults(
                platform=self.name,
                query=query,
                error="; ".join(errors),
            )

        # Sort by reply count (most engaged threads first)
        all_results.sort(key=lambda r: r.num_replies, reverse=True)

        return SearchResults(
            platform=self.name,
            query=query,
            results=all_results[:limit],
            total_found=len(all_results),
        )

    async def get_thread(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        board: str = "g",
        **kwargs: Any,
    ) -> list[OpinionResult]:
        """Fetch all posts in a 4chan thread."""
        url = f"{_BASE}/{board}/thread/{thread_id}.json"

        async with _rate_lock:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

        results: list[OpinionResult] = []
        for post in data.get("posts", [])[:limit]:
            com = post.get("com", "")
            if not com:
                continue
            results.append(
                OpinionResult(
                    text=strip_html(com),
                    platform=f"4chan /{board}/",
                    url=_THREAD_URL.format(board=board, no=post.get("no", thread_id)),
                    author=post.get("name", "Anonymous"),
                    score=0,  # 4chan has no voting
                    num_replies=0,
                    created_at=str(post.get("time", "")),
                )
            )

        return results

    # ── Internal helpers ────────────────────────────────────────

    async def _search_board(
        self,
        query: str,
        board: str,
        *,
        limit: int = 10,
    ) -> list[OpinionResult]:
        """Fetch catalog for *board* and filter threads by *query*."""
        url = f"{_BASE}/{board}/catalog.json"

        async with _rate_lock:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                catalog = resp.json()

        query_words = set(query.lower().split())
        results: list[OpinionResult] = []

        for page in catalog:
            for thread in page.get("threads", []):
                subject = strip_html(thread.get("sub", ""))
                comment = strip_html(thread.get("com", ""))
                haystack = f"{subject} {comment}".lower()

                # Require at least half the query words to match
                matched = sum(1 for w in query_words if w in haystack)
                if matched < max(1, len(query_words) // 2):
                    continue

                text = f"{subject}\n{comment}".strip() if subject else comment
                results.append(
                    OpinionResult(
                        text=text[:1000],
                        platform=f"4chan /{board}/",
                        url=_THREAD_URL.format(board=board, no=thread["no"]),
                        author=thread.get("name", "Anonymous"),
                        score=0,
                        num_replies=safe_int(thread.get("replies")),
                        created_at=str(thread.get("time", "")),
                    )
                )
                if len(results) >= limit:
                    return results

        return results

    @staticmethod
    def _route_boards(query: str) -> list[str]:
        """Guess the most relevant boards from query keywords."""
        query_lower = query.lower()
        boards: list[str] = []
        for keyword, board_list in BOARD_ROUTES.items():
            if keyword in query_lower:
                for b in board_list:
                    if b not in boards:
                        boards.append(b)

        # Default to /g/ (tech) if nothing matched — our primary audience
        return boards if boards else ["g"]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_BASE}/boards.json")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
