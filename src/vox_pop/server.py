"""MCP server for vox-pop.

Exposes ``search_opinions``, ``get_thread``, and ``list_platforms``
as MCP tools usable by any MCP-compatible client (Claude Code,
Cursor, Windsurf, etc.).

Run with:
    python -m vox_pop.server
or:
    uvx vox-pop-server
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from vox_pop.core import (
    format_context,
    get_default_providers,
    get_provider,
    list_providers,
    search,
    search_multiple,
)

mcp = FastMCP(
    "vox-pop",
    version="0.1.0",
    description="Public opinion for LLMs — search HackerNews, Reddit, 4chan, Stack Exchange, and Telegram for real human opinions. Zero API keys.",
)


@mcp.tool()
async def search_opinions(
    query: str,
    platforms: str = "auto",
    limit: int = 5,
) -> str:
    """Search for real public opinions across multiple platforms.

    Args:
        query: What to search for (e.g. "best laptop for programming 2026")
        platforms: Comma-separated platform names, or "auto" for all.
                   Available: hackernews, reddit, 4chan, stackexchange, telegram
        limit: Max results per platform (default 5).

    Returns:
        Formatted context string with opinions, trust signals, and source URLs.
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
        return f"No valid platforms specified. Available: {', '.join(list_providers())}"

    results = await search_multiple(
        query, providers=providers, limit_per_platform=limit,
    )
    return format_context(results, max_per_platform=limit)


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

    Returns:
        Formatted list of comments with trust signals.
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
    """List all available opinion platforms and their status.

    Returns:
        JSON string with platform names and health status.
    """
    providers = get_default_providers()
    statuses: list[dict[str, Any]] = []

    for p in providers:
        healthy = await p.health_check()
        statuses.append({
            "name": p.name,
            "status": "ok" if healthy else "degraded",
        })

    return json.dumps(statuses, indent=2)


def main() -> None:
    """Entry point for ``python -m vox_pop.server``."""
    mcp.run()


if __name__ == "__main__":
    main()
