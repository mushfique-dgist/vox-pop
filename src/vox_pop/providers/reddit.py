"""Reddit provider with a multi-source fallback chain.

Tier 1 (Pullpush) → Tier 1 (Arctic Shift) → Tier 2 (Redlib).

All three sources are free and require zero authentication.
Supports time filtering for perspective searches.
Includes subreddit routing to reduce noise.

Pullpush:     Pushshift successor, full-text search, live-ish data.
Arctic Shift: Historical archive, query + subreddit required.
Redlib:       Privacy frontend, renders Reddit server-side as HTML.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    relevance_filter,
    safe_int,
    strip_html,
)

_TIMEOUT = 20.0
_POST_URL = "https://www.reddit.com{permalink}"

# ── Source endpoints ────────────────────────────────────────────

_PULLPUSH_POSTS = "https://api.pullpush.io/reddit/search/submission/"
_PULLPUSH_COMMENTS = "https://api.pullpush.io/reddit/search/comment/"

_ARCTIC_POSTS = "https://arctic-shift.photon-reddit.com/api/posts/search"

# Redlib instances ordered by observed reliability (March 2026).
_REDLIB_INSTANCES = [
    "https://redlib.catsarch.com",
    "https://redlib.zaggy.nl",
    "https://safereddit.com",
    "https://rl.bloat.cat",
]

# ── Subreddit routing by topic ──────────────────────────────────

SUBREDDIT_ROUTES: dict[str, list[str]] = {
    "programming": ["programming", "learnprogramming", "coding"],
    "python": ["Python", "learnpython"],
    "javascript": ["javascript", "webdev"],
    "rust": ["rust", "programming"],
    "go": ["golang", "programming"],
    "laptop": ["SuggestALaptop", "laptops", "buildapc"],
    "phone": ["PickAnAndroidForMe", "iphone", "smartphones"],
    "skincare": ["SkincareAddiction", "30PlusSkinCare"],
    "fitness": ["Fitness", "bodyweightfitness", "GYM"],
    "diet": ["nutrition", "EatCheapAndHealthy"],
    "travel": ["travel", "solotravel", "backpacking"],
    "study abroad": ["StudyInTheNetherlands", "studyAbroad"],
    "university": ["college", "ApplyingToCollege", "GradSchool"],
    "career": ["cscareerquestions", "careerguidance", "jobs"],
    "finance": ["personalfinance", "investing", "FinancialPlanning"],
    "crypto": ["CryptoCurrency", "Bitcoin", "ethereum"],
    "gaming": ["gaming", "pcgaming", "Games"],
    "relationship": ["relationships", "dating_advice"],
    "mental health": ["mentalhealth", "anxiety", "depression"],
    "cooking": ["Cooking", "EatCheapAndHealthy", "MealPrepSunday"],
    "fashion": ["malefashionadvice", "femalefashionadvice"],
    "tech": ["technology", "gadgets"],
    "ai": ["artificial", "MachineLearning", "LocalLLaMA", "ClaudeAI"],
    "startup": ["startups", "Entrepreneur", "SideProject"],
}


class RedditProvider(Provider):
    """Search Reddit via Pullpush → Arctic Shift → Redlib fallback."""

    name = "reddit"
    supports_time_filter = True

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str | None = None,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        # Auto-route to relevant subreddits if none specified
        subreddits = [subreddit] if subreddit else self._route_subreddits(query)

        all_results: list[OpinionResult] = []
        last_error: str | None = None

        for sub in subreddits[:3]:
            # Try Pullpush first (best for broad search)
            result = await self._pullpush_search(
                query, limit=limit, subreddit=sub, time_range=time_range,
            )
            if result.ok:
                all_results.extend(result.results)
                continue

            # Fall back to Arctic Shift (needs subreddit)
            if sub:
                result = await self._arctic_search(
                    query, limit=limit, subreddit=sub, time_range=time_range,
                )
                if result.ok:
                    all_results.extend(result.results)
                    continue

            last_error = result.error

        # If no subreddit-scoped results, try Pullpush without subreddit
        if not all_results and not subreddit:
            result = await self._pullpush_search(
                query, limit=limit, subreddit=None, time_range=time_range,
            )
            if result.ok:
                all_results = list(result.results)
            else:
                last_error = result.error

        # Post-filter for relevance to reduce Pullpush noise
        all_results = relevance_filter(all_results, query)

        # Sort by engagement
        all_results.sort(key=lambda r: r.score + r.num_replies, reverse=True)

        if all_results:
            return SearchResults(
                platform=self.name,
                query=query,
                results=all_results[:limit],
                total_found=len(all_results),
                time_range=time_range.value,
            )

        return SearchResults(
            platform=self.name,
            query=query,
            error=last_error or "No results found",
            time_range=time_range.value,
        )

    # ── Pullpush (primary) ──────────────────────────────────────

    async def _pullpush_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str | None = None,
        time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        params: dict[str, Any] = {"q": query, "size": min(limit * 2, 100)}
        if subreddit:
            params["subreddit"] = subreddit

        after, before = time_range.to_timestamps()
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_PULLPUSH_POSTS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=f"Pullpush: {exc}",
                time_range=time_range.value,
            )

        return self._parse_pushshift_response(data, query, time_range)

    # ── Arctic Shift (fallback 1) ───────────────────────────────

    async def _arctic_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str = "",
        time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        params: dict[str, Any] = {
            "query": query,
            "subreddit": subreddit,
            "limit": min(limit * 2, 100),
        }

        after, before = time_range.to_timestamps()
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_ARCTIC_POSTS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=f"Arctic Shift: {exc}",
                time_range=time_range.value,
            )

        posts = data.get("data") or []
        results = [self._post_to_result(p) for p in posts]
        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=len(results),
            time_range=time_range.value,
        )

    # ── Redlib (fallback 2) ─────────────────────────────────────

    async def _redlib_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str = "",
        time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        path = f"/r/{subreddit}/search?q={query}&restrict_sr=on&sort=relevance&t=all"

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            for base in _REDLIB_INSTANCES:
                try:
                    resp = await client.get(
                        base + path,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; vox-pop/0.1)"},
                    )
                    if resp.status_code != 200:
                        continue
                    body = resp.text
                    if "anubis" in body.lower() or "checking your browser" in body.lower():
                        continue
                    return self._parse_redlib_html(body, query, time_range)
                except httpx.HTTPError:
                    continue

        return SearchResults(
            platform=self.name,
            query=query,
            error="All Redlib instances failed",
            time_range=time_range.value,
        )

    # ── Shared parsers ──────────────────────────────────────────

    def _parse_pushshift_response(
        self, data: dict[str, Any], query: str, time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        posts = data.get("data") or []
        results = [self._post_to_result(p) for p in posts]
        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=len(results),
            time_range=time_range.value,
        )

    @staticmethod
    def _post_to_result(post: dict[str, Any]) -> OpinionResult:
        title = post.get("title", "")
        selftext = post.get("selftext") or ""
        text = f"{title}\n{selftext}".strip() if selftext else title
        permalink = post.get("permalink", "")
        url = _POST_URL.format(permalink=permalink) if permalink else ""
        # Convert Unix timestamp to ISO date
        created_utc = post.get("created_utc", "")
        if isinstance(created_utc, (int, float)) and created_utc > 0:
            from datetime import datetime, timezone
            created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            created_at = str(created_utc)
        return OpinionResult(
            text=strip_html(text),
            platform="reddit",
            url=url,
            author=post.get("author", "[deleted]"),
            score=safe_int(post.get("score")),
            num_replies=safe_int(post.get("num_comments")),
            created_at=created_at,
            metadata={
                "subreddit": post.get("subreddit", ""),
            },
        )

    @staticmethod
    def _parse_redlib_html(
        html_text: str, query: str, time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        results: list[OpinionResult] = []
        post_blocks = re.findall(
            r'<a\s+class="post_title"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            html_text,
        )
        for href, title in post_blocks:
            results.append(
                OpinionResult(
                    text=strip_html(title),
                    platform="reddit (via Redlib)",
                    url=f"https://www.reddit.com{href}" if href.startswith("/r/") else href,
                    author="",
                    score=0,
                )
            )

        return SearchResults(
            platform="reddit",
            query=query,
            results=results,
            total_found=len(results),
            time_range=time_range.value,
        )

    @staticmethod
    def _route_subreddits(query: str) -> list[str]:
        """Pick relevant subreddits from query keywords."""
        query_lower = query.lower()
        subs: list[str] = []
        for keyword, sub_list in SUBREDDIT_ROUTES.items():
            if keyword in query_lower:
                for s in sub_list:
                    if s not in subs:
                        subs.append(s)
        return subs if subs else []

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    _PULLPUSH_POSTS, params={"q": "test", "size": 1},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
