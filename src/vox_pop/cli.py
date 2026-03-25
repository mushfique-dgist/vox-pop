"""Standalone CLI for vox-pop.

Usage:
    vox-pop search "how to debloat face" --platforms auto
    vox-pop search "best laptop 2026" --platforms hackernews,reddit
    vox-pop search "rust vs go" --perspective
    vox-pop thread hackernews 12345678
    vox-pop platforms
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from vox_pop.core import (
    format_context,
    format_perspective,
    get_default_providers,
    get_provider,
    list_providers,
    search_multiple,
    search_with_perspective,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="vox-pop",
        description="Public opinion for LLMs — zero API keys.",
    )
    sub = parser.add_subparsers(dest="command")

    # ── search ──────────────────────────────────────────────────
    search_p = sub.add_parser("search", help="Search for opinions")
    search_p.add_argument("query", help="What to search for")
    search_p.add_argument(
        "--platforms", "-p",
        default="auto",
        help="Comma-separated platforms or 'auto' (default: auto)",
    )
    search_p.add_argument(
        "--limit", "-n",
        type=int,
        default=5,
        help="Max results per platform (default: 5)",
    )
    search_p.add_argument(
        "--perspective",
        action="store_true",
        help="Show both historical and recent opinions (Then vs Now)",
    )

    # ── thread ──────────────────────────────────────────────────
    thread_p = sub.add_parser("thread", help="Get thread comments")
    thread_p.add_argument("platform", help="Platform name")
    thread_p.add_argument("thread_id", help="Thread/post ID")
    thread_p.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Max comments (default: 20)",
    )

    # ── platforms ────────────────────────────────────────────────
    sub.add_parser("platforms", help="List available platforms")

    args = parser.parse_args(argv)

    if args.command == "search":
        asyncio.run(_cmd_search(args))
    elif args.command == "thread":
        asyncio.run(_cmd_thread(args))
    elif args.command == "platforms":
        _cmd_platforms()
    else:
        parser.print_help()
        sys.exit(1)


async def _cmd_search(args: argparse.Namespace) -> None:
    providers = _resolve_providers(args.platforms)

    if args.perspective:
        results = await search_with_perspective(
            args.query, providers=providers, limit_per_period=args.limit,
        )
        print(format_perspective(results, max_per_period=args.limit))
    else:
        results = await search_multiple(
            args.query, providers=providers, limit_per_platform=args.limit,
        )
        print(format_context(results, max_per_platform=args.limit))


async def _cmd_thread(args: argparse.Namespace) -> None:
    try:
        provider = get_provider(args.platform)
    except KeyError:
        print(f"Unknown platform: {args.platform}", file=sys.stderr)
        sys.exit(1)

    comments = await provider.get_thread(args.thread_id, limit=args.limit)

    if not comments:
        print(f"No comments found for thread {args.thread_id}")
        return

    for c in comments:
        text = c.text[:500] + "..." if len(c.text) > 500 else c.text
        print(f"\n> {text}")
        print(f"  — {c.trust_signal}")


def _cmd_platforms() -> None:
    from vox_pop.providers import PROVIDERS

    print("Available platforms:")
    for name, cls in PROVIDERS.items():
        temporal = "time filter" if cls().supports_time_filter else "current only"
        print(f"  - {name} ({temporal})")


def _resolve_providers(platforms_str: str) -> list:
    if platforms_str == "auto":
        return get_default_providers()

    providers = []
    for name in platforms_str.split(","):
        try:
            providers.append(get_provider(name.strip()))
        except KeyError:
            print(f"Warning: unknown platform '{name.strip()}', skipping", file=sys.stderr)

    if not providers:
        print(f"No valid platforms. Available: {', '.join(list_providers())}", file=sys.stderr)
        sys.exit(1)

    return providers


if __name__ == "__main__":
    main()
