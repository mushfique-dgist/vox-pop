"""LessWrong provider via the public GraphQL API.

Tier 1 — zero auth, public GraphQL endpoint.

LessWrong is a community focused on rationality, AI safety, and
effective altruism. High-quality long-form posts with detailed
discussion.

API: https://www.lesswrong.com/graphql (interactive explorer at /graphiql)

Limitations:
  - Niche community: primarily AI, rationality, and philosophy.
  - Smaller volume than Reddit or HN, but very high signal.
  - No server-side full-text comment search (posts only).
"""

from __future__ import annotations

from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    strip_html,
)

_BASE = "https://www.lesswrong.com"
_TIMEOUT = 15.0

_SEARCH_QUERY = """
query SearchPosts($query: String!, $limit: Int) {
  posts(input: {terms: {query: $query, limit: $limit}}) {
    results {
      title
      slug
      baseScore
      commentCount
      postedAt
      user { displayName }
      contents { plaintextMainText }
    }
  }
}
"""

_POST_COMMENTS_QUERY = """
query PostComments($postId: String!, $limit: Int) {
  comments(input: {terms: {postId: $postId, limit: $limit, sortedBy: "top"}}) {
    results {
      contents { plaintextMainText }
      baseScore
      postedAt
      user { displayName }
      _id
    }
  }
}
"""


class LessWrongProvider(Provider):
    """Search LessWrong via GraphQL API."""

    name = "lesswrong"
    supports_time_filter = False
    supports_threads = True

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        try:
            results = await self._search_graphql(query, limit=limit)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return SearchResults(
                platform=self.name,
                query=query,
                error=str(exc),
            )

        return SearchResults(
            platform=self.name,
            query=query,
            results=results[:limit],
            total_found=len(results),
        )

    async def get_thread(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[OpinionResult]:
        """Fetch comments for a LessWrong post by slug or ID."""
        payload = {
            "query": _POST_COMMENTS_QUERY,
            "variables": {"postId": thread_id, "limit": min(limit, 50)},
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE}/graphql",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        comments = (
            data.get("data", {})
            .get("comments", {})
            .get("results", [])
        )

        results: list[OpinionResult] = []
        for c in comments:
            text = (c.get("contents") or {}).get("plaintextMainText", "")
            if not text or len(text) < 10:
                continue
            user = (c.get("user") or {}).get("displayName", "")
            results.append(
                OpinionResult(
                    text=text[:1000],
                    platform="lesswrong",
                    url=f"{_BASE}/posts/{thread_id}#comment-{c.get('_id', '')}",
                    author=user,
                    score=c.get("baseScore", 0),
                    created_at=self._format_date(c.get("postedAt")),
                )
            )

        return results[:limit]

    # ── Internal helpers ────────────────────────────────────────

    async def _search_graphql(
        self, query: str, *, limit: int = 10
    ) -> list[OpinionResult]:
        """Search posts via GraphQL."""
        payload = {
            "query": _SEARCH_QUERY,
            "variables": {"query": query, "limit": min(limit, 50)},
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE}/graphql",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        posts = (
            data.get("data", {})
            .get("posts", {})
            .get("results", [])
        )

        results: list[OpinionResult] = []
        for p in posts:
            title = p.get("title", "")
            body = (p.get("contents") or {}).get("plaintextMainText", "")
            slug = p.get("slug", "")

            text = f"{title}\n{body[:500]}".strip() if body else title
            if not text:
                continue

            user = (p.get("user") or {}).get("displayName", "")
            results.append(
                OpinionResult(
                    text=text[:1000],
                    platform="lesswrong",
                    url=f"{_BASE}/posts/{slug}" if slug else _BASE,
                    author=user,
                    score=p.get("baseScore", 0),
                    num_replies=p.get("commentCount", 0),
                    created_at=self._format_date(p.get("postedAt")),
                )
            )

        return results

    @staticmethod
    def _format_date(ts: str | None) -> str:
        """Extract date from ISO timestamp."""
        if not ts:
            return ""
        return str(ts)[:10]

    async def health_check(self) -> bool:
        try:
            payload = {"query": "{ posts(input: {terms: {limit: 1}}) { results { title } } }"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{_BASE}/graphql", json=payload)
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
