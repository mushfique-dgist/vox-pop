"""Generic XenForo forum provider via HTML scraping.

Tier 2 — no API, scrape search results HTML.

XenForo is one of the most popular forum software platforms. This
provider works with any public XenForo 2 forum by scraping the
standard search endpoint.

Currently configured forums:
  - Head-Fi (head-fi.org) — audiophile/headphone community
  - AnandTech Forums (forums.anandtech.com) — tech hardware

Limitations:
  - HTML scraping — layout changes could break parsing.
  - Search results limited to ~25 per page.
  - Some forums may have Cloudflare protection (intermittent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    TopicProfile,
    score_route,
    strip_html,
)

_TIMEOUT = 15.0

# Regex patterns for XenForo 2 search results.
_TITLE_RE = re.compile(
    r'class="contentRow-title">\s*<a href="([^"]*)">(.*?)</a>',
    re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'class="contentRow-snippet">(.*?)</div>',
    re.DOTALL,
)
_AUTHOR_RE = re.compile(
    r'class="username[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_DATE_RE = re.compile(
    r'<time[^>]*datetime="([^"]*)"',
)
_REPLIES_RE = re.compile(
    r'Replies:\s*(\d+)',
)
_FORUM_RE = re.compile(
    r'Forum:\s*<a[^>]*>(.*?)</a>',
    re.DOTALL,
)


@dataclass
class ForumSite:
    """A configured XenForo forum instance."""

    id: str
    name: str
    base_url: str
    keywords: list[str]


# Configured forum instances.
FORUM_SITES: list[ForumSite] = [
    ForumSite(
        id="headfi",
        name="Head-Fi",
        base_url="https://www.head-fi.org",
        keywords=[
            "headphone", "headphones", "earbuds", "earphone", "iem",
            "audiophile", "dac", "amplifier", "amp", "hifi", "hi-fi",
            "over ear", "in ear", "open back", "closed back",
            "sennheiser", "beyerdynamic", "akg", "sony", "audio",
            "noise cancelling", "soundstage", "bass",
        ],
    ),
    ForumSite(
        id="anandtech",
        name="AnandTech",
        base_url="https://forums.anandtech.com",
        keywords=[
            "cpu", "gpu", "processor", "graphics card", "motherboard",
            "ram", "ssd", "nvme", "benchmark", "overclock",
            "intel", "amd", "nvidia", "ryzen", "geforce", "radeon",
            "pc build", "pc hardware", "computer hardware",
            "server", "workstation", "laptop", "monitor",
        ],
    ),
]

# Build TopicProfiles for routing.
FORUM_PROFILES: list[TopicProfile] = [
    TopicProfile(site.id, site.keywords)
    for site in FORUM_SITES
]

# Quick lookup by ID.
_SITE_BY_ID: dict[str, ForumSite] = {s.id: s for s in FORUM_SITES}


class XenForoProvider(Provider):
    """Search XenForo-based forums via HTML scraping."""

    name = "forums"
    supports_time_filter = False
    supports_threads = False

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        forum_ids: list[str] | None = None,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        if not forum_ids:
            forum_ids = self._route_forums(query)

        # If no confident match, search all configured forums.
        if not forum_ids:
            forum_ids = list(_SITE_BY_ID.keys())

        all_results: list[OpinionResult] = []
        errors: list[str] = []

        for fid in forum_ids[:3]:
            site = _SITE_BY_ID.get(fid)
            if not site:
                continue
            try:
                results = await self._search_forum(query, site, limit=limit)
                all_results.extend(results)
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{site.name}: {exc}")

        if not all_results and errors:
            return SearchResults(
                platform=self.name,
                query=query,
                error="; ".join(errors),
            )

        return SearchResults(
            platform=self.name,
            query=query,
            results=all_results[:limit],
            total_found=len(all_results),
        )

    # ── Internal helpers ────────────────────────────────────────

    async def _search_forum(
        self,
        query: str,
        site: ForumSite,
        *,
        limit: int = 15,
    ) -> list[OpinionResult]:
        """Scrape XenForo search results page."""
        url = f"{site.base_url}/search/search"
        params = {"keywords": query, "type": "post", "order": "relevance"}

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (compatible; vox-pop/0.2)"},
            )
            resp.raise_for_status()
            html = resp.text

        # Check for Cloudflare block
        if "Just a moment" in html[:500] or "challenge-platform" in html[:1000]:
            raise ValueError(f"{site.name} blocked by Cloudflare")

        return self._parse_results(html, site, limit=limit)

    def _parse_results(
        self, html: str, site: ForumSite, *, limit: int = 15
    ) -> list[OpinionResult]:
        """Parse XenForo search results from HTML."""
        # Split into result blocks
        blocks = re.split(r'data-author="', html)

        results: list[OpinionResult] = []
        for block in blocks[1:limit + 1]:
            # Extract author from split point
            author_end = block.find('"')
            author = block[:author_end] if author_end > 0 else ""

            title_match = _TITLE_RE.search(block)
            if not title_match:
                continue
            path = title_match.group(1)
            title = strip_html(title_match.group(2)).strip()

            snippet_match = _SNIPPET_RE.search(block)
            snippet = strip_html(snippet_match.group(1)).strip() if snippet_match else ""

            text = f"{title}\n{snippet}".strip() if snippet else title
            if not text or len(text) < 10:
                continue

            date_match = _DATE_RE.search(block)
            created_at = date_match.group(1)[:10] if date_match else ""

            replies_match = _REPLIES_RE.search(block)
            num_replies = int(replies_match.group(1)) if replies_match else 0

            forum_match = _FORUM_RE.search(block)
            subforum = strip_html(forum_match.group(1)).strip() if forum_match else ""

            result_url = f"{site.base_url}{path}" if path.startswith("/") else path
            platform_label = f"{site.name}/{subforum}" if subforum else site.name

            results.append(
                OpinionResult(
                    text=text[:1000],
                    platform=platform_label,
                    url=result_url,
                    author=author,
                    score=0,  # XenForo search doesn't expose votes
                    num_replies=num_replies,
                    created_at=created_at,
                )
            )

        return results

    @staticmethod
    def _route_forums(query: str) -> list[str]:
        """Score query against forum profiles."""
        return score_route(query, FORUM_PROFILES, min_score=0.5, max_results=3)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{FORUM_SITES[0].base_url}/",
                    headers={"User-Agent": "Mozilla/5.0 (compatible; vox-pop/0.2)"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
