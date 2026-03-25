"""Reddit provider with a multi-source fallback chain.

Tier 1 (Arctic Shift) → Tier 1 (Pullpush) → Tier 2 (Redlib).

All three sources are free and require zero authentication.

Arctic Shift: historical archive, query + subreddit required.
Pullpush:     Pushshift successor, full-text search, live-ish data.
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
    safe_int,
    strip_html,
)

_TIMEOUT = 20.0
_POST_URL = "https://www.reddit.com{permalink}"

# ── Source endpoints ────────────────────────────────────────────

_PULLPUSH_POSTS = "https://api.pullpush.io/reddit/search/submission/"
_PULLPUSH_COMMENTS = "https://api.pullpush.io/reddit/search/comment/"

_ARCTIC_POSTS = "https://arctic-shift.photon-reddit.com/api/posts/search"
_ARCTIC_COMMENTS = "https://arctic-shift.photon-reddit.com/api/comments/search"

# Redlib instances ordered by observed reliability (March 2026).
# These are tried sequentially — first success wins.
_REDLIB_INSTANCES = [
    "https://redlib.catsarch.com",
    "https://redlib.zaggy.nl",
    "https://safereddit.com",
    "https://rl.bloat.cat",
]


class RedditProvider(Provider):
    """Search Reddit via Pullpush → Arctic Shift → Redlib fallback."""

    name = "reddit"

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str | None = None,
        **kwargs: Any,
    ) -> SearchResults:
        # Try Pullpush first (supports full-text without subreddit)
        result = await self._pullpush_search(query, limit=limit, subreddit=subreddit)
        if result.ok:
            return result

        # Fall back to Arctic Shift (requires subreddit for query param)
        if subreddit:
            result = await self._arctic_search(query, limit=limit, subreddit=subreddit)
            if result.ok:
                return result

        # Last resort: Redlib scrape of subreddit search
        if subreddit:
            result = await self._redlib_search(query, limit=limit, subreddit=subreddit)
            if result.ok:
                return result

        # If nothing worked, return the first error (or a generic one)
        if result.error:
            return result
        return SearchResults(
            platform=self.name,
            query=query,
            error="All Reddit sources failed",
        )

    # ── Pullpush (primary) ──────────────────────────────────────

    async def _pullpush_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str | None = None,
    ) -> SearchResults:
        params: dict[str, Any] = {"q": query, "size": min(limit, 100)}
        if subreddit:
            params["subreddit"] = subreddit

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_PULLPUSH_POSTS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=f"Pullpush: {exc}",
            )

        return self._parse_pushshift_response(data, query)

    # ── Arctic Shift (fallback 1) ───────────────────────────────

    async def _arctic_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str = "",
    ) -> SearchResults:
        params: dict[str, Any] = {
            "query": query,
            "subreddit": subreddit,
            "limit": min(limit, 100),
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_ARCTIC_POSTS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=f"Arctic Shift: {exc}",
            )

        posts = data.get("data") or []
        results = [self._post_to_result(p) for p in posts]
        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=len(results),
        )

    # ── Redlib (fallback 2) ─────────────────────────────────────

    async def _redlib_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str = "",
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
                    # Check for bot challenges
                    if "anubis" in body.lower() or "checking your browser" in body.lower():
                        continue
                    return self._parse_redlib_html(body, query)
                except httpx.HTTPError:
                    continue

        return SearchResults(
            platform=self.name,
            query=query,
            error="All Redlib instances failed",
        )

    # ── Shared parsers ──────────────────────────────────────────

    def _parse_pushshift_response(
        self, data: dict[str, Any], query: str,
    ) -> SearchResults:
        posts = data.get("data") or []
        results = [self._post_to_result(p) for p in posts]
        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=len(results),
        )

    @staticmethod
    def _post_to_result(post: dict[str, Any]) -> OpinionResult:
        title = post.get("title", "")
        selftext = post.get("selftext") or ""
        text = f"{title}\n{selftext}".strip() if selftext else title
        permalink = post.get("permalink", "")
        url = _POST_URL.format(permalink=permalink) if permalink else ""
        return OpinionResult(
            text=strip_html(text),
            platform="reddit",
            url=url,
            author=post.get("author", "[deleted]"),
            score=safe_int(post.get("score")),
            num_replies=safe_int(post.get("num_comments")),
            created_at=str(post.get("created_utc", "")),
        )

    @staticmethod
    def _parse_redlib_html(html_text: str, query: str) -> SearchResults:
        """Very lightweight extraction from Redlib search results HTML.

        We intentionally avoid heavy parsing libraries (BeautifulSoup etc.)
        to keep the dependency footprint at zero beyond httpx.
        """
        results: list[OpinionResult] = []
        # Redlib wraps each post in <div class="post">...</div>
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
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    _PULLPUSH_POSTS, params={"q": "test", "size": 1},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
