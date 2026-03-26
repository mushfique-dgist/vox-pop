"""
vox-pop — Public opinion for LLMs.

Search 9 platforms (HackerNews, Reddit, 4chan, Stack Exchange, Telegram,
Lobsters, Lemmy, LessWrong, forums) for real human opinions.
Semantic routing + optional LLM intelligence layer.
"""

__version__ = "0.2.0"

from vox_pop.providers.base import (
    OpinionResult,
    PerspectiveResults,
    Provider,
    SearchResults,
    TimeRange,
)
from vox_pop.core import (
    format_context,
    format_perspective,
    get_default_providers,
    get_provider,
    list_providers,
    search,
    search_multiple,
    search_with_perspective,
)

__all__ = [
    "search",
    "search_multiple",
    "search_with_perspective",
    "format_context",
    "format_perspective",
    "get_default_providers",
    "get_provider",
    "list_providers",
    "OpinionResult",
    "PerspectiveResults",
    "SearchResults",
    "Provider",
    "TimeRange",
]
