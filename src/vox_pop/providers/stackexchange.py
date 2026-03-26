"""Stack Exchange provider via the official API.

Tier 1 — free, 300 requests/day without a key, 10,000/day with a
free registered key. Covers 180+ communities.
Supports time filtering for perspective searches.

Docs: https://api.stackexchange.com/docs
"""

from __future__ import annotations

from typing import Any

import httpx

import html as html_mod

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    TopicProfile,
    optimize_query,
    safe_int,
    score_route,
    strip_html,
)

_BASE = "https://api.stackexchange.com/2.3"
_TIMEOUT = 15.0

SITE_PROFILES: list[TopicProfile] = [
    TopicProfile("stackoverflow", [
        "programming", "code", "coding", "software", "developer",
        "python", "javascript", "typescript", "java", "c++", "c#",
        "rust", "go", "golang", "ruby", "php", "swift", "kotlin",
        "react", "angular", "vue", "node", "django", "flask",
        "api", "database", "sql", "git", "docker", "kubernetes",
        "bug", "error", "exception", "debug",
        "algorithm", "data structure", "regex",
    ]),
    TopicProfile("serverfault", [
        "server", "sysadmin", "system admin", "devops", "nginx",
        "apache", "dns", "ssl", "networking",
    ]),
    TopicProfile("unix", [
        "linux", "unix", "bash", "shell", "terminal", "command line",
        "ubuntu", "debian", "fedora", "arch linux",
    ]),
    TopicProfile("askubuntu", ["ubuntu", "apt", "snap", "gnome"]),
    TopicProfile("superuser", [
        "computer", "pc", "windows", "mac", "hardware", "bios",
        "driver", "disk", "partition", "keyboard", "mouse", "monitor",
        "headphone", "speaker", "usb", "bluetooth", "wifi",
        "laptop", "desktop",
    ]),
    TopicProfile("hardwarerecs", [
        "recommend", "recommendation", "best", "which",
        "keyboard", "mouse", "monitor", "laptop", "headphone",
        "hardware", "device", "gadget", "peripheral",
    ]),
    TopicProfile("fitness", [
        "fitness", "gym", "workout", "exercise", "muscle",
        "weight loss", "bodybuilding", "nutrition",
    ]),
    TopicProfile("health", [
        "health", "medical", "symptom", "disease", "vitamin",
    ]),
    TopicProfile("cooking", [
        "cooking", "recipe", "baking", "food", "kitchen", "ingredient",
    ]),
    TopicProfile("travel", [
        "travel", "flight", "visa", "passport", "airport",
    ]),
    TopicProfile("money", [
        "money", "finance", "tax", "investment", "budget", "saving",
        "retirement", "mortgage", "insurance",
    ]),
    TopicProfile("security", [
        "security", "cybersecurity", "encryption", "vulnerability",
        "password", "authentication", "hacking",
    ]),
    TopicProfile("math", [
        "math", "mathematics", "calculus", "algebra", "statistics",
        "probability", "geometry", "proof",
    ]),
    TopicProfile("physics", ["physics", "quantum", "mechanics", "relativity"]),
    TopicProfile("gaming", [
        "gaming", "video game", "game", "steam", "achievement",
    ]),
    TopicProfile("workplace", [
        "workplace", "career", "job", "office", "manager",
        "coworker", "promotion", "salary negotiation",
    ]),
    TopicProfile("diy", [
        "diy", "home improvement", "woodworking", "plumbing", "electrical",
    ]),
    TopicProfile("photo", [
        "photography", "photo", "camera", "exposure", "lighting",
    ]),
]


class StackExchangeProvider(Provider):
    """Search across Stack Exchange sites."""

    name = "stackexchange"
    supports_time_filter = True
    supports_threads = True

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

        # When routing is confident, search up to 3 targeted sites.
        # When falling back, cast a wider net across more sites.
        max_sites = 3 if len(sites) <= 5 else 6
        for site in sites[:max_sites]:
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
                author=html_mod.unescape(ans.get("owner", {}).get("display_name", "")),
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
        # Optimize long queries — SE's search API works best with 5-10 terms
        search_q = optimize_query(query, max_terms=8)

        params: dict[str, Any] = {
            "order": "desc",
            "sort": "relevance",
            "q": search_q,
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
            resp = await client.get(f"{_BASE}/search/excerpts", params=params)
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

            # search/excerpts returns both questions and answers
            title = strip_html(item.get("title", ""))
            excerpt = strip_html(item.get("excerpt", ""))
            text = f"{title}\n{excerpt}".strip() if excerpt else title

            question_id = item.get("question_id", "")
            link = f"https://{site}.stackexchange.com/q/{question_id}" if question_id else ""
            if site == "stackoverflow":
                link = f"https://stackoverflow.com/q/{question_id}" if question_id else ""

            results.append(
                OpinionResult(
                    text=text,
                    platform=f"stackexchange/{site}",
                    url=link,
                    author="",
                    score=safe_int(item.get("score")),
                    num_replies=safe_int(item.get("answer_count", 0)),
                    created_at=created_at,
                    metadata={
                        "is_answered": item.get("is_answered", False),
                        "view_count": safe_int(item.get("view_count")),
                        "tags": item.get("tags", []),
                    },
                )
            )

        return results

    # Broad fallback: search the most popular SE sites when routing
    # can't confidently pick. This ensures niche queries (math, physics,
    # cooking, etc.) still find results even without keyword matches.
    _FALLBACK_SITES = [
        "stackoverflow", "superuser", "math",
        "serverfault", "unix", "fitness",
        "money", "cooking", "travel", "workplace",
        "security", "gaming", "diy", "physics",
    ]

    @staticmethod
    def _route_sites(query: str) -> list[str]:
        """Score query against SE site profiles, return best matches."""
        sites = score_route(query, SITE_PROFILES, min_score=0.5, max_results=3)
        return sites if sites else StackExchangeProvider._FALLBACK_SITES

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{_BASE}/info", params={"site": "stackoverflow"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
