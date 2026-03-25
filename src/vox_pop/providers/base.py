"""Base classes and data models for all providers."""

from __future__ import annotations

import html
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TimeRange(Enum):
    """Predefined time ranges for perspective searches."""

    RECENT = "recent"          # Last 6 months
    HISTORICAL = "historical"  # Older than 1 year
    ALL = "all"                # No time filter

    def to_timestamps(self) -> tuple[int | None, int | None]:
        """Return (after, before) Unix timestamps for this range."""
        now = int(time.time())
        if self == TimeRange.RECENT:
            return (now - 180 * 86400, None)       # 6 months ago → now
        if self == TimeRange.HISTORICAL:
            return (None, now - 365 * 86400)       # beginning → 1 year ago
        return (None, None)


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
        if self.created_at:
            date_str = str(self.created_at)[:10]
            if len(date_str) >= 4:
                parts.append(date_str)
        return " | ".join(parts)


@dataclass
class SearchResults:
    """Aggregated results from a platform search."""

    platform: str
    query: str
    results: list[OpinionResult] = field(default_factory=list)
    total_found: int = 0
    error: str | None = None
    time_range: str = "all"

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.results) > 0

    def to_context(self, max_results: int = 10) -> str:
        """Format results as LLM-friendly context string."""
        if self.error:
            return f"[{self.platform}] Error: {self.error}"
        if not self.results:
            return f"[{self.platform}] No results for: {self.query}"

        label = self.platform
        if self.time_range != "all":
            label = f"{self.platform} ({self.time_range})"

        lines = [f"### {label} ({self.total_found} found, showing {min(len(self.results), max_results)})"]
        for r in self.results[:max_results]:
            text = r.text[:500] + "..." if len(r.text) > 500 else r.text
            lines.append(f"\n> {text}")
            lines.append(f"— {r.trust_signal}")
            if r.url:
                lines.append(f"  Source: {r.url}")
        return "\n".join(lines)


@dataclass
class PerspectiveResults:
    """Combined historical + recent results for a single platform."""

    platform: str
    query: str
    recent: SearchResults
    historical: SearchResults

    def to_context(self, max_per_period: int = 5) -> str:
        """Format as a Then vs Now comparison."""
        lines: list[str] = [f"## {self.platform} — Then vs Now\n"]

        if self.historical.ok:
            lines.append(f"**Historical** (1+ year ago):")
            for r in self.historical.results[:max_per_period]:
                text = r.text[:300] + "..." if len(r.text) > 300 else r.text
                lines.append(f"> {text}")
                lines.append(f"— {r.trust_signal}\n")
        else:
            lines.append("**Historical**: No data found.\n")

        if self.recent.ok:
            lines.append(f"**Recent** (last 6 months):")
            for r in self.recent.results[:max_per_period]:
                text = r.text[:300] + "..." if len(r.text) > 300 else r.text
                lines.append(f"> {text}")
                lines.append(f"— {r.trust_signal}\n")
        else:
            lines.append("**Recent**: No data found.\n")

        return "\n".join(lines)


class Provider(ABC):
    """Base class for all platform providers.

    Subclasses must implement ``search``. Implementing ``get_thread``
    is optional but recommended for providers that support it.
    """

    name: str = "unknown"
    supports_time_filter: bool = False

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        time_range: TimeRange = TimeRange.ALL,
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


def relevance_filter(
    results: list[OpinionResult],
    query: str,
    *,
    min_word_match_ratio: float = 0.4,
) -> list[OpinionResult]:
    """Post-filter results by keyword relevance.

    Removes results where fewer than *min_word_match_ratio* of the
    query words appear in the result text. Helps eliminate noise from
    broad full-text search APIs like Pullpush.
    """
    query_words = set(query.lower().split())
    # Remove very short/common words
    query_words = {w for w in query_words if len(w) > 2}
    if not query_words:
        return results

    threshold = max(1, int(len(query_words) * min_word_match_ratio))
    filtered: list[OpinionResult] = []
    for r in results:
        text_lower = r.text.lower()
        matched = sum(1 for w in query_words if w in text_lower)
        if matched >= threshold:
            filtered.append(r)

    return filtered
