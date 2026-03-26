"""Lobste.rs provider via the public JSON API.

Tier 1 — zero auth, structured JSON by appending .json to any page.

Lobste.rs is a computing-focused link aggregation site (like HN)
with a tag-based organization system. Tags include: rust, python,
javascript, linux, security, ai, etc.

Search is HTML-only so we scrape it. Tag pages support .json natively.

Limitations:
  - Search returns ~25 results per page (HTML scraping).
  - Tag pages return ~25 recent stories.
  - Smaller community than HN — fewer but higher-signal results.
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
    strip_html,
)

_BASE = "https://lobste.rs"
_TIMEOUT = 15.0

# Regex patterns for scraping search results HTML.
_LINK_RE = re.compile(
    r'<a[^>]*class="u-url"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_SCORE_RE = re.compile(r'class="upvoter"[^>]*>(\d+)')
_COMMENTS_RE = re.compile(r'href="(/s/[^"]+)"[^>]*>\s*(\d+)\s*comment')
_BYLINE_RE = re.compile(r'class="u-author[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
_DATE_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')


class LobstersProvider(Provider):
    """Search Lobste.rs via HTML search + JSON tag pages."""

    name = "lobsters"
    supports_time_filter = False
    supports_threads = False

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        results = await self._search_html(query, limit=limit)

        return SearchResults(
            platform=self.name,
            query=query,
            results=results[:limit],
            total_found=len(results),
        )

    async def _search_html(self, query: str, *, limit: int = 25) -> list[OpinionResult]:
        """Scrape Lobste.rs HTML search results."""
        url = f"{_BASE}/search"
        params = {"q": query, "what": "stories", "order": "relevance"}

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (compatible; vox-pop/0.2)"},
            )
            resp.raise_for_status()
            html = resp.text

        return self._parse_stories_html(html, limit=limit)

    def _parse_stories_html(self, html: str, *, limit: int = 25) -> list[OpinionResult]:
        """Parse story entries from Lobste.rs HTML."""
        results: list[OpinionResult] = []

        # Split HTML into story blocks (class may include h-entry etc.)
        blocks = html.split('class="story_liner')

        for block in blocks[1:limit + 1]:  # Skip first split (before first story)
            # Extract title and link
            link_match = _LINK_RE.search(block)
            if not link_match:
                continue
            story_url = link_match.group(1)
            title = strip_html(link_match.group(2)).strip()
            if not title:
                continue

            score_match = _SCORE_RE.search(block)
            score = int(score_match.group(1)) if score_match else 0

            comments_match = _COMMENTS_RE.search(block)
            num_comments = int(comments_match.group(2)) if comments_match else 0
            story_path = comments_match.group(1) if comments_match else ""

            author_match = _BYLINE_RE.search(block)
            author = strip_html(author_match.group(1)).strip() if author_match else ""

            date_match = _DATE_RE.search(block)
            created_at = date_match.group(1)[:10] if date_match else ""

            lobste_url = f"{_BASE}{story_path}" if story_path else story_url

            results.append(
                OpinionResult(
                    text=title,
                    platform="lobsters",
                    url=lobste_url,
                    author=author,
                    score=score,
                    num_replies=num_comments,
                    created_at=created_at,
                )
            )

        return results

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_BASE}/newest.json")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
