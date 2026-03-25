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

mcp = FastMCP(
    "vox-pop",
    version="0.1.1",
    description="Public opinion for LLMs — HackerNews, Reddit, 4chan, Stack Exchange, Telegram. Zero API keys.",
)


@mcp.tool()
async def search_opinions(
    query: str,
    platforms: str = "auto",
    limit: int = 5,
) -> str:
    """Search for real public opinions across multiple platforms.

    Args:
        query: What to search for (e.g. "best laptop for programming")
        platforms: Comma-separated platform names, or "auto" for all.
                   Available: hackernews, reddit, 4chan, stackexchange, telegram
        limit: Max results per platform (default 5).
    """
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

    results = await search_multiple(
        query, providers=providers, limit_per_platform=limit,
    )
    return format_context(results, max_per_platform=limit)


@mcp.tool()
async def search_opinions_perspective(
    query: str,
    platforms: str = "auto",
    limit: int = 5,
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
    """
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

    results = await search_with_perspective(
        query, providers=providers, limit_per_period=limit,
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
