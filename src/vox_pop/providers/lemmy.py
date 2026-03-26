"""Lemmy provider via the public REST API.

Tier 1 — zero auth, full-featured REST API.

Lemmy is a federated link aggregator (like Reddit). Multiple instances
exist (lemmy.ml, lemmy.world, etc.). We search the flagship instance
by default which federates content from across the network.

API docs: https://join-lemmy.org/api/

Limitations:
  - Search is instance-scoped (we search lemmy.world, the largest).
  - Results vary by instance federation state.
  - Rate limit: 1 req/sec for unauthenticated users.
"""

from __future__ import annotations

from datetime import datetime, timezone
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

_BASE = "https://lemmy.world/api/v3"
_TIMEOUT = 15.0

# Lemmy community routing profiles.
COMMUNITY_PROFILES: list[TopicProfile] = [
    TopicProfile("technology@lemmy.world", [
        "tech", "technology", "programming", "software", "hardware",
        "ai", "artificial intelligence", "machine learning",
        "linux", "open source", "privacy", "vpn", "security",
    ]),
    TopicProfile("linux@lemmy.ml", [
        "linux", "ubuntu", "fedora", "arch", "debian", "distro",
        "terminal", "command line", "bash", "shell",
    ]),
    TopicProfile("programming@programming.dev", [
        "programming", "code", "coding", "developer", "software",
        "python", "rust", "javascript", "typescript", "golang",
    ]),
    TopicProfile("fitness@lemmy.world", [
        "fitness", "gym", "workout", "exercise", "muscle",
        "weight loss", "bodybuilding", "running",
    ]),
    TopicProfile("gaming@lemmy.world", [
        "gaming", "game", "video game", "steam", "playstation",
        "xbox", "nintendo", "pc gaming",
    ]),
    TopicProfile("privacy@lemmy.ml", [
        "privacy", "surveillance", "encryption", "vpn",
        "data collection", "tracking",
    ]),
    TopicProfile("selfhosted@lemmy.world", [
        "self hosted", "selfhosted", "home server", "homelab",
        "docker", "server",
    ]),
    TopicProfile("science@lemmy.world", [
        "science", "physics", "chemistry", "biology", "research",
        "space", "astronomy",
    ]),
    TopicProfile("asklemmy@lemmy.ml", [
        "advice", "opinion", "help", "question", "recommend",
        "should I", "what do you think",
    ]),
    TopicProfile("world@lemmy.world", [
        "news", "world", "politics", "election", "government",
        "climate", "economy",
    ]),
]

_FALLBACK_COMMUNITIES = ["asklemmy@lemmy.ml", "technology@lemmy.world"]


class LemmyProvider(Provider):
    """Search Lemmy instances via the REST API."""

    name = "lemmy"
    supports_time_filter = False
    supports_threads = True

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        communities: list[str] | None = None,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        if not communities:
            communities = self._route_communities(query)

        all_results: list[OpinionResult] = []
        errors: list[str] = []

        # Search globally (Lemmy search is already cross-community)
        try:
            results = await self._search_api(query, limit=limit)
            all_results.extend(results)
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"lemmy.world: {exc}")

        if not all_results and errors:
            return SearchResults(
                platform=self.name,
                query=query,
                error="; ".join(errors),
            )

        # Sort by score
        all_results.sort(key=lambda r: r.score, reverse=True)

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
        **kwargs: Any,
    ) -> list[OpinionResult]:
        """Fetch comments for a Lemmy post."""
        params: dict[str, Any] = {
            "post_id": int(thread_id),
            "sort": "Top",
            "limit": min(limit, 50),
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/comment/list", params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[OpinionResult] = []
        for item in data.get("comments", []):
            comment = item.get("comment", {})
            counts = item.get("counts", {})
            creator = item.get("creator", {})
            text = comment.get("content", "")
            if not text or len(text) < 5:
                continue
            results.append(
                OpinionResult(
                    text=strip_html(text),
                    platform="lemmy",
                    url=comment.get("ap_id", ""),
                    author=creator.get("name", ""),
                    score=counts.get("score", 0),
                    created_at=self._format_time(comment.get("published")),
                )
            )

        return results[:limit]

    # ── Internal helpers ────────────────────────────────────────

    async def _search_api(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[OpinionResult]:
        """Search Lemmy via REST API."""
        params: dict[str, Any] = {
            "q": query,
            "type_": "Posts",
            "sort": "TopAll",
            "limit": min(limit, 50),
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[OpinionResult] = []
        for item in data.get("posts", []):
            post = item.get("post", {})
            counts = item.get("counts", {})
            creator = item.get("creator", {})
            community = item.get("community", {})

            title = post.get("name", "")
            body = post.get("body", "")
            text = f"{title}\n{body}".strip() if body else title
            if not text:
                continue

            comm_name = community.get("name", "")
            results.append(
                OpinionResult(
                    text=text[:1000],
                    platform=f"lemmy/{comm_name}" if comm_name else "lemmy",
                    url=post.get("ap_id", ""),
                    author=creator.get("name", ""),
                    score=counts.get("score", 0),
                    num_replies=counts.get("comments", 0),
                    created_at=self._format_time(post.get("published")),
                )
            )

        return results

    @staticmethod
    def _route_communities(query: str) -> list[str]:
        """Score query against community profiles."""
        return score_route(query, COMMUNITY_PROFILES, min_score=0.5, max_results=3)

    @staticmethod
    def _format_time(ts: str | None) -> str:
        """Convert ISO timestamp to date string."""
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return str(ts)[:10] if ts else ""

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_BASE}/site")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
