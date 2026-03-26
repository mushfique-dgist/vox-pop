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
    supports_threads: bool = False

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

# Common English stop words filtered from keyword matching.
# These match nearly everything and produce false positives.
STOP_WORDS: set[str] = {
    # Grammatical
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "his", "her", "its", "do", "does", "did",
    "have", "has", "had", "will", "would", "could", "should", "shall",
    "can", "may", "might", "must", "to", "of", "in", "on", "at", "by",
    "for", "with", "about", "from", "as", "into", "through", "during",
    "before", "after", "and", "but", "or", "nor", "not", "no", "so",
    "if", "then", "than", "too", "very", "just", "also",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "how", "when", "where", "why",
    "all", "each", "every", "any", "some", "many", "much", "more", "most",
    "am", "vs", "get", "got", "way", "best", "good", "bad",
    # Conversational filler — common in LLM queries, useless for search APIs
    "something", "someone", "anything", "anyone", "everything", "everyone",
    "looking", "want", "wanted", "need", "needed", "think", "thinking",
    "know", "knew", "try", "trying", "tried", "using", "used", "use",
    "going", "like", "really", "actually", "basically", "probably",
    "instead", "person", "people", "thing", "things", "stuff",
    "pretty", "quite", "solid", "great", "nice", "sure", "right",
    "pick", "choice", "choose", "option", "recommend", "suggestion",
    "tell", "help", "please", "thanks", "hi", "hello", "hey",
    "savvy", "wondering", "curious", "anyone", "somebody",
}

_PUNCT_RE = re.compile(r"[^\w\s-]")


def extract_query_keywords(query: str) -> set[str]:
    """Extract meaningful keywords from a query, filtering stop words."""
    # Strip punctuation first so "hp," becomes "hp"
    cleaned = _PUNCT_RE.sub(" ", query.lower())
    words = set(cleaned.split())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


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


def optimize_query(query: str, *, max_terms: int = 8) -> str:
    """Trim a long query to its most meaningful terms for search APIs.

    LLM queries can be essay-length. Search APIs work best with 5-10
    focused terms. This extracts meaningful keywords and truncates.
    """
    words = query.split()
    if len(words) <= max_terms:
        return query
    keywords = extract_query_keywords(query)
    if keywords:
        return " ".join(list(keywords)[:max_terms])
    return " ".join(words[:max_terms])


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
    query_words = extract_query_keywords(query)
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


# ── LLM routing hints parser ──────────────────────────────────

# Maps platform prefixes in routing_hints to provider kwargs.
_HINT_PREFIX_TO_KWARG: dict[str, str] = {
    "reddit": "subreddits",
    "4chan": "boards",
    "stackexchange": "sites",
    "telegram": "channels",
    "lemmy": "communities",
    "forums": "forum_ids",
}


def parse_routing_hints(hints: str) -> dict[str, list[str]]:
    """Parse an LLM-provided routing hints string into provider kwargs.

    Format: comma-separated ``platform:destination`` pairs.
    Example: ``"reddit:fitness,reddit:loseit,4chan:fit,stackexchange:health"``

    Returns a dict like ``{"subreddits": ["fitness", "loseit"], "boards": ["fit"]}``.
    Unknown platform prefixes are silently ignored.
    """
    if not hints or not hints.strip():
        return {}

    by_platform: dict[str, list[str]] = {}
    for part in hints.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        prefix, dest = part.split(":", 1)
        prefix = prefix.strip().lower()
        dest = dest.strip()
        if not dest:
            continue
        kwarg = _HINT_PREFIX_TO_KWARG.get(prefix)
        if kwarg:
            by_platform.setdefault(kwarg, []).append(dest)

    return by_platform


# ── Scoring-based topic router ─────────────────────────────────

@dataclass
class TopicProfile:
    """A destination (board, subreddit, SE site, channel) with keywords.

    Keywords can be multi-word phrases. Longer phrase matches score
    higher — this naturally handles context disambiguation.
    For example, "piano keyboard" will score /mu/ higher than /g/
    because "piano" matches music keywords while both share "keyboard".
    """

    id: str  # e.g. "fit", "MechanicalKeyboards", "stackoverflow"
    keywords: list[str]


def score_route(
    query: str,
    profiles: list[TopicProfile],
    *,
    min_score: float = 0.5,
    max_results: int = 3,
) -> list[str]:
    """Score *query* against topic profiles, return ranked destination IDs.

    Scoring:
      - Each keyword that appears in the query adds points
      - Multi-word keywords score more (word count as weight)
      - This handles synonyms, phrases, and context naturally

    A query "best piano keyboard for beginners" scores:
      - /mu/ profile (has "piano", "music", "instrument"): "piano" matches → 1.0
      - /g/ profile (has "keyboard", "tech"): "keyboard" matches → 1.0
      - r/piano (has "piano", "keyboard piano"): "piano" → 1.0, "keyboard piano" → 2.0
      → r/piano wins because the phrase "keyboard piano" is a stronger signal

    Returns IDs sorted by score descending, filtered by min_score.
    """
    query_lower = query.lower()
    scored: list[tuple[str, float]] = []

    for profile in profiles:
        score = 0.0
        for kw in profile.keywords:
            if kw.lower() in query_lower:
                # Multi-word phrases score higher (more specific)
                score += len(kw.split())
        if score >= min_score:
            scored.append((profile.id, score))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in scored[:max_results]]
