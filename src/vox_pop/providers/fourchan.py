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
from datetime import datetime, timezone
from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    TopicProfile,
    extract_query_keywords,
    safe_int,
    score_route,
    strip_html,
)

_BASE = "https://a.4cdn.org"
_THREAD_URL = "https://boards.4chan.org/{board}/thread/{no}"
_TIMEOUT = 15.0

# Board profiles: each board has a rich keyword set.
# Multi-word phrases score higher, enabling context disambiguation.
# "keyboard piano" routes to /mu/, "mechanical keyboard" routes to /g/.
BOARD_PROFILES: list[TopicProfile] = [
    TopicProfile("g", [
        "tech", "technology", "programming", "software", "computer", "laptop",
        "phone", "smartphone", "headphone", "earbuds", "speaker", "monitor",
        "mechanical keyboard", "keyboard", "mouse", "gpu", "cpu", "pc",
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "linux", "windows", "mac", "macos", "android", "ios",
        "app", "browser", "server", "cloud", "database", "api",
        "rust", "python", "javascript", "golang", "c++",
        "open source", "privacy", "vpn", "security",
    ]),
    TopicProfile("fit", [
        "fitness", "gym", "workout", "exercise", "lifting", "bodybuilding",
        "weight loss", "lose weight", "bulk", "bulking", "cutting", "cut",
        "muscle", "strength", "cardio", "running", "jogging", "marathon",
        "protein", "creatine", "supplement", "diet", "calorie",
        "skincare", "skin care", "acne", "face", "bloat", "mewing",
        "posture", "flexibility", "stretching", "yoga",
        "body fat", "lean", "abs", "chest", "squat", "deadlift", "bench press",
    ]),
    TopicProfile("ck", [
        "cooking", "food", "recipe", "baking", "meal prep",
        "kitchen", "restaurant", "chef", "cuisine",
        "diet", "nutrition", "eating",
    ]),
    TopicProfile("trv", [
        "travel", "traveling", "backpacking", "tourism", "flight",
        "hotel", "hostel", "country", "abroad", "expat", "visa",
    ]),
    TopicProfile("sci", [
        "science", "physics", "chemistry", "biology", "math", "mathematics",
        "research", "quantum", "space", "astronomy",
    ]),
    TopicProfile("biz", [
        "business", "finance", "investing", "investment", "stock", "stocks",
        "crypto", "cryptocurrency", "bitcoin", "ethereum", "trading",
        "startup", "entrepreneur", "money", "salary", "passive income",
    ]),
    TopicProfile("fa", [
        "fashion", "style", "clothing", "outfit", "sneaker", "shoes",
        "streetwear", "wardrobe", "designer",
    ]),
    TopicProfile("adv", [
        "advice", "career", "career advice", "relationship", "dating",
        "life advice", "help", "decision",
    ]),
    TopicProfile("a", [
        "anime", "manga", "otaku", "waifu", "seasonal anime",
    ]),
    TopicProfile("v", [
        "gaming", "video game", "game", "playstation", "xbox", "nintendo",
        "steam", "pc gaming", "esports",
    ]),
    TopicProfile("mu", [
        "music", "album", "song", "band", "guitar", "piano",
        "keyboard piano", "instrument", "vinyl", "hip hop", "rock",
        "playlist", "concert",
    ]),
    TopicProfile("tv", [
        "film", "movie", "cinema", "tv show", "television", "series",
        "director", "actor", "netflix", "streaming",
    ]),
    TopicProfile("diy", ["diy", "woodworking", "home improvement", "project"]),
    TopicProfile("o", ["auto", "car", "vehicle", "driving", "engine", "motorcycle"]),
    TopicProfile("p", ["photography", "camera", "photo", "lens", "dslr"]),
    TopicProfile("pol", ["politics", "political", "election", "government", "policy"]),
    TopicProfile("int", [
        "country", "city", "move to", "living in", "culture",
        "language", "europe", "asia", "america", "international",
        "expat", "immigrant", "immigration",
    ]),
    TopicProfile("r9k", [
        "lonely", "social", "anxiety", "introvert", "neet",
    ]),
]

# Broad boards searched when no specific route matches.
# 4chan's catalog is small enough that the real filtering happens
# locally via keyword matching — casting a wider net costs almost
# nothing (one HTTP request per board) and prevents false negatives.
_FALLBACK_BOARDS = ["g", "adv", "int", "pol"]

# 4chan asks for max 1 request/second.
_rate_lock = asyncio.Lock()


class FourChanProvider(Provider):
    """Search 4chan boards via catalog filtering."""

    name = "4chan"
    supports_time_filter = False  # Catalog is inherently current-only
    supports_threads = True

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        boards: list[str] | None = None,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        if not boards:
            boards = self._route_boards(query)

        # If no confident match, search general-purpose boards.
        # The local keyword filter in _search_board is the real
        # quality gate — routing just picks which catalogs to fetch.
        if not boards:
            boards = _FALLBACK_BOARDS

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
                    created_at=self._format_time(post.get("time")),
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

        query_words = extract_query_keywords(query)
        if not query_words:
            # All stop words — use raw words as last resort
            query_words = set(query.lower().split())
        results: list[OpinionResult] = []

        for page in catalog:
            for thread in page.get("threads", []):
                subject = strip_html(thread.get("sub", ""))
                comment = strip_html(thread.get("com", ""))
                haystack = f"{subject} {comment}".lower()

                # Require at least half the meaningful query words to match
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
                        created_at=self._format_time(thread.get("time")),
                    )
                )
                if len(results) >= limit:
                    return results

        return results

    @staticmethod
    def _route_boards(query: str) -> list[str]:
        """Score query against board profiles and return best matches."""
        return score_route(query, BOARD_PROFILES, min_score=0.5, max_results=3)

    @staticmethod
    def _format_time(ts: Any) -> str:
        """Convert Unix timestamp to ISO date string."""
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return ""

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_BASE}/boards.json")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
