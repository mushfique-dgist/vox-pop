"""Telegram public channel provider via the t.me/s/ web preview.

Tier 1 — no auth, no bot token, no API key.

Telegram exposes a server-rendered HTML preview at:
    https://t.me/s/<channel_name>

This works for any public channel/group that hasn't disabled the web
preview. We parse the HTML to extract messages.

Limitations:
  - Only the ~20 most recent messages are shown per page.
  - No server-side search — we can only filter client-side.
  - Private channels/groups are inaccessible (by design).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    strip_html,
)

_BASE = "https://t.me/s"
_TIMEOUT = 15.0

# Known public channels by topic. Community-contributed.
CHANNEL_ROUTES: dict[str, list[str]] = {
    "ai": ["OpenAI", "anthropic_ai"],
    "tech": ["duaborern_tech", "techcrunch"],
    "crypto": ["bitcoin", "ethereum"],
    "news": ["bbcnews", "caborernnn"],
}

# Regex to extract messages from t.me/s/ HTML.
# Each message is wrapped in a div with class "tgme_widget_message_text"
_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_DATE_RE = re.compile(
    r'<time[^>]*datetime="([^"]+)"',
)
_MSG_LINK_RE = re.compile(
    r'data-post="([^"]+)"',
)


class TelegramProvider(Provider):
    """Search Telegram public channels via web preview."""

    name = "telegram"

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        channels: list[str] | None = None,
        **kwargs: Any,
    ) -> SearchResults:
        if not channels:
            channels = self._route_channels(query)

        if not channels:
            return SearchResults(
                platform=self.name,
                query=query,
                error="No channels specified and could not auto-route. "
                      "Pass channels=['channel_name'] explicitly.",
            )

        all_results: list[OpinionResult] = []
        errors: list[str] = []

        for channel in channels[:5]:
            try:
                msgs = await self._fetch_channel(channel)
                # Client-side filter by query keywords
                query_words = set(query.lower().split())
                for msg in msgs:
                    text_lower = msg.text.lower()
                    matched = sum(1 for w in query_words if w in text_lower)
                    if matched >= max(1, len(query_words) // 2):
                        all_results.append(msg)
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"@{channel}: {exc}")

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

    async def _fetch_channel(self, channel: str) -> list[OpinionResult]:
        """Fetch recent messages from a public Telegram channel."""
        url = f"{_BASE}/{channel}"

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; vox-pop/0.1)"},
            )
            resp.raise_for_status()
            html = resp.text

        messages = _MSG_RE.findall(html)
        dates = _DATE_RE.findall(html)
        links = _MSG_LINK_RE.findall(html)

        results: list[OpinionResult] = []
        for i, raw_msg in enumerate(messages):
            text = strip_html(raw_msg).strip()
            if not text or len(text) < 10:
                continue

            date = dates[i] if i < len(dates) else ""
            link = links[i] if i < len(links) else ""
            msg_url = f"https://t.me/{link}" if link else f"https://t.me/{channel}"

            results.append(
                OpinionResult(
                    text=text,
                    platform=f"telegram/@{channel}",
                    url=msg_url,
                    author=f"@{channel}",
                    score=0,
                    created_at=date,
                )
            )

        return results

    @staticmethod
    def _route_channels(query: str) -> list[str]:
        """Pick relevant Telegram channels from query keywords."""
        query_lower = query.lower()
        channels: list[str] = []
        for keyword, channel_list in CHANNEL_ROUTES.items():
            if keyword in query_lower:
                for c in channel_list:
                    if c not in channels:
                        channels.append(c)
        return channels

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_BASE}/telegram")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
