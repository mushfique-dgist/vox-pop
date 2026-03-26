"""MCP server for vox-pop.

Exposes ``search_opinions``, ``search_opinions_perspective``,
``get_thread_opinions``, and ``list_platforms`` as MCP tools.

Run with:  python -m vox_pop.server
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

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
from vox_pop.providers.base import parse_routing_hints

mcp = FastMCP(
    "vox-pop",
    instructions="Public opinion for LLMs — 9 platforms (HackerNews, Reddit, 4chan, Stack Exchange, Telegram, Lobsters, Lemmy, LessWrong, forums) with semantic routing. Optional LLM key improves routing.",
)


@mcp.tool()
async def search_opinions(
    query: str,
    platforms: str = "auto",
    limit: int = 5,
    routing_hints: str = "",
) -> str:
    """Search for real public opinions across multiple platforms.

    Args:
        query: What to search for (e.g. "best laptop for programming")
        platforms: Comma-separated platform names, or "auto" for all.
                   Available: hackernews, reddit, 4chan, stackexchange,
                   telegram, lobsters, lemmy, lesswrong, forums
        limit: Max results per platform (default 5).
        routing_hints: Optional. Comma-separated platform:destination pairs
                       specifying which communities/boards to search.
                       This dramatically improves result quality.
                       Format: "reddit:subreddit,4chan:board,stackexchange:site,telegram:channel,
                                lemmy:community,forums:forum_id"
                       Examples:
                         "reddit:fitness,reddit:loseit,4chan:fit,lemmy:fitness@lemmy.world"
                         "reddit:MechanicalKeyboards,4chan:g,forums:headfi"
                         "reddit:berlin,reddit:germany,4chan:int,lemmy:asklemmy@lemmy.ml"
                         "stackexchange:stackoverflow,reddit:programming,lemmy:programming@programming.dev"
                       Forum IDs: headfi, anandtech
                       If empty, destinations are auto-detected from the query.
    """
    if not query or not query.strip():
        return "Error: search query cannot be empty."

    if platforms == "auto":
        providers = get_default_providers()
    else:
        names = [n.strip() for n in platforms.split(",")]
        providers = []
        for name in names:
            try:
                providers.append(get_provider(name))
            except KeyError:
                pass

    if not providers:
        return f"No valid platforms. Available: {', '.join(list_providers())}"

    # Tier 1: LLM-provided routing hints take priority
    hint_kwargs = parse_routing_hints(routing_hints)
    search_q = query  # default: original query

    # Tier 2/3: If no hints from calling LLM, use smart routing
    if not hint_kwargs:
        from vox_pop.router import route_query

        route = await route_query(query)
        hint_kwargs = route.to_kwargs()
        # Use LLM-rewritten search query when available
        if route.search_query:
            search_q = route.search_query

    results = await search_multiple(
        search_q, providers=providers, limit_per_platform=limit, **hint_kwargs,
    )
    return format_context(results, max_per_platform=limit)


@mcp.tool()
async def search_opinions_perspective(
    query: str,
    platforms: str = "auto",
    limit: int = 5,
    routing_hints: str = "",
) -> str:
    """Search for opinions with a Then vs Now perspective.

    Returns both historical (1+ year old) and recent (last 6 months)
    opinions side by side, showing how public sentiment has evolved.

    Works best with HackerNews, Reddit, and Stack Exchange which
    support time filtering. 4chan and Telegram return current data only.

    Args:
        query: What to search for
        platforms: Comma-separated platform names, or "auto" for all
        limit: Max results per time period per platform (default 5)
        routing_hints: Optional. Comma-separated platform:destination pairs
                       specifying which communities/boards to search.
                       Format: "reddit:subreddit,4chan:board,stackexchange:site,telegram:channel"
                       If empty, destinations are auto-detected from the query.
    """
    if not query or not query.strip():
        return "Error: search query cannot be empty."
    if platforms == "auto":
        providers = get_default_providers()
    else:
        names = [n.strip() for n in platforms.split(",")]
        providers = []
        for name in names:
            try:
                providers.append(get_provider(name))
            except KeyError:
                pass

    if not providers:
        return f"No valid platforms. Available: {', '.join(list_providers())}"

    # Tier 1: LLM-provided routing hints take priority
    hint_kwargs = parse_routing_hints(routing_hints)
    search_q = query

    # Tier 2/3: If no hints, use smart routing
    if not hint_kwargs:
        from vox_pop.router import route_query

        route = await route_query(query)
        hint_kwargs = route.to_kwargs()
        if route.search_query:
            search_q = route.search_query

    results = await search_with_perspective(
        search_q, providers=providers, limit_per_period=limit, **hint_kwargs,
    )
    return format_perspective(results, max_per_period=limit)


@mcp.tool()
async def get_thread_opinions(
    platform: str,
    thread_id: str,
    limit: int = 20,
) -> str:
    """Get all opinions/comments from a specific thread.

    Args:
        platform: Platform name (hackernews, reddit, 4chan, stackexchange)
        thread_id: The thread/post ID on that platform
        limit: Max comments to return (default 20)
    """
    try:
        provider = get_provider(platform)
    except KeyError:
        return f"Unknown platform: {platform}. Available: {', '.join(list_providers())}"

    if not provider.supports_threads:
        return (
            f"Thread retrieval is not supported for {platform}. "
            f"Supported platforms: hackernews, 4chan, stackexchange, lemmy, lesswrong."
        )

    comments = await provider.get_thread(thread_id, limit=limit)

    if not comments:
        return f"No comments found for thread {thread_id} on {platform}."

    lines = [f"### Thread {thread_id} on {platform} ({len(comments)} comments)"]
    for c in comments:
        text = c.text[:500] + "..." if len(c.text) > 500 else c.text
        lines.append(f"\n> {text}")
        lines.append(f"— {c.trust_signal}")
    return "\n".join(lines)


@mcp.tool()
async def list_available_platforms() -> str:
    """List all available opinion platforms and their capabilities."""
    providers = get_default_providers()
    statuses: list[dict[str, Any]] = []

    for p in providers:
        healthy = await p.health_check()
        statuses.append({
            "name": p.name,
            "status": "ok" if healthy else "degraded",
            "supports_perspective": p.supports_time_filter,
        })

    return json.dumps(statuses, indent=2)


def main() -> None:
    """Entry point for ``python -m vox_pop.server``."""
    mcp.run()


if __name__ == "__main__":
    main()
