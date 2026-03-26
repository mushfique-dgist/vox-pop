"""
vox-pop — Public opinion for LLMs.

Search HackerNews, Reddit, 4chan, Stack Exchange, and Telegram
for real human opinions. Zero API keys required.
"""

__version__ = "0.1.1"

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
