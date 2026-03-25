"""Base classes and data models for all providers."""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OpinionResult:
    """A single opinion/post/comment from a platform."""

    text: str
    platform: str
    url: str
    author: str = ""
    score: int = 0
    num_replies: int = 0
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def trust_signal(self) -> str:
        """Human-readable trust indicator for LLM context."""
        parts: list[str] = [self.platform]
        if self.score:
            parts.append(f"{self.score:+d} points")
        if self.num_replies:
            parts.append(f"{self.num_replies} replies")
        if self.author:
            parts.append(f"by {self.author}")
        return " | ".join(parts)


@dataclass
class SearchResults:
    """Aggregated results from a platform search."""

    platform: str
    query: str
    results: list[OpinionResult] = field(default_factory=list)
    total_found: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.results) > 0

    def to_context(self, max_results: int = 10) -> str:
        """Format results as LLM-friendly context string."""
        if self.error:
            return f"[{self.platform}] Error: {self.error}"
        if not self.results:
            return f"[{self.platform}] No results for: {self.query}"

        lines = [f"### {self.platform} ({self.total_found} found, showing {min(len(self.results), max_results)})"]
        for r in self.results[:max_results]:
            text = r.text[:500] + "..." if len(r.text) > 500 else r.text
            lines.append(f"\n> {text}")
            lines.append(f"— {r.trust_signal}")
            if r.url:
                lines.append(f"  Source: {r.url}")
        return "\n".join(lines)


class Provider(ABC):
    """Base class for all platform providers.

    Subclasses must implement ``search``. Implementing ``get_thread``
    is optional but recommended for providers that support it.
    """

    name: str = "unknown"

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        **kwargs: Any,
    ) -> SearchResults:
        """Search for opinions matching *query*."""
        ...

    async def get_thread(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[OpinionResult]:
        """Fetch all comments in a single thread.

        Optional — returns empty list if not implemented.
        """
        return []

    async def health_check(self) -> bool:
        """Return True if the provider is currently reachable."""
        return True


# ── Shared utilities ────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = _HTML_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _MULTI_SPACE_RE.sub(" ", text).strip()


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce *value* to int without raising."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
