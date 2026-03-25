"""Core search orchestration for vox-pop.

Provides ``search``, ``search_multiple``, and ``search_with_perspective``
as the main public API.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vox_pop.providers.base import (
    PerspectiveResults,
    Provider,
    SearchResults,
    TimeRange,
)


async def search(
    query: str,
    *,
    provider: Provider,
    limit: int = 10,
    time_range: TimeRange = TimeRange.ALL,
    **kwargs: Any,
) -> SearchResults:
    """Search a single provider."""
    return await provider.search(query, limit=limit, time_range=time_range, **kwargs)


async def search_multiple(
    query: str,
    *,
    providers: list[Provider],
    limit_per_platform: int = 10,
    time_range: TimeRange = TimeRange.ALL,
    **kwargs: Any,
) -> list[SearchResults]:
    """Search multiple providers in parallel.

    Returns one ``SearchResults`` per provider, in the same order.
    """
    tasks = [
        _safe_search(p, query, limit=limit_per_platform, time_range=time_range, **kwargs)
        for p in providers
    ]
    return list(await asyncio.gather(*tasks))


async def search_with_perspective(
    query: str,
    *,
    providers: list[Provider],
    limit_per_period: int = 5,
    **kwargs: Any,
) -> list[PerspectiveResults]:
    """Search each provider for both historical and recent opinions.

    For providers that support time filtering (HN, Reddit, SE),
    two searches are performed: one for recent (last 6 months)
    and one for historical (1+ year ago).

    For providers without time filtering (4chan, Telegram),
    only a single "recent" search is performed, and historical
    returns empty.
    """
    tasks = [
        _perspective_for_provider(p, query, limit_per_period=limit_per_period, **kwargs)
        for p in providers
    ]
    return list(await asyncio.gather(*tasks))


def format_context(
    results: list[SearchResults],
    *,
    max_per_platform: int = 5,
) -> str:
    """Combine multiple SearchResults into a single LLM context string."""
    sections: list[str] = []
    for sr in results:
        sections.append(sr.to_context(max_results=max_per_platform))
    return "\n\n---\n\n".join(sections)


def format_perspective(
    results: list[PerspectiveResults],
    *,
    max_per_period: int = 5,
) -> str:
    """Format perspective results as a Then vs Now context string."""
    sections: list[str] = []
    for pr in results:
        sections.append(pr.to_context(max_per_period=max_per_period))
    return "\n\n---\n\n".join(sections)


def get_provider(name: str, **kwargs: Any) -> Provider:
    """Instantiate a provider by name."""
    from vox_pop.providers import PROVIDERS

    cls = PROVIDERS[name]
    return cls(**kwargs) if kwargs else cls()


def list_providers() -> list[str]:
    """Return all registered provider names."""
    from vox_pop.providers import PROVIDERS

    return list(PROVIDERS.keys())


def get_default_providers(**kwargs: Any) -> list[Provider]:
    """Return instances of all providers with default config."""
    from vox_pop.providers import PROVIDERS

    return [cls() for cls in PROVIDERS.values()]


# ── Internal ────────────────────────────────────────────────────


async def _safe_search(
    provider: Provider,
    query: str,
    *,
    limit: int = 10,
    time_range: TimeRange = TimeRange.ALL,
    **kwargs: Any,
) -> SearchResults:
    """Wrap provider.search so exceptions become error results."""
    try:
        return await provider.search(query, limit=limit, time_range=time_range, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return SearchResults(
            platform=provider.name,
            query=query,
            error=f"Unhandled: {type(exc).__name__}: {exc}",
        )


async def _perspective_for_provider(
    provider: Provider,
    query: str,
    *,
    limit_per_period: int = 5,
    **kwargs: Any,
) -> PerspectiveResults:
    """Run both historical and recent searches for a single provider."""
    if provider.supports_time_filter:
        recent_task = _safe_search(
            provider, query, limit=limit_per_period,
            time_range=TimeRange.RECENT, **kwargs,
        )
        historical_task = _safe_search(
            provider, query, limit=limit_per_period,
            time_range=TimeRange.HISTORICAL, **kwargs,
        )
        recent, historical = await asyncio.gather(recent_task, historical_task)
    else:
        # Provider is inherently current-only
        recent = await _safe_search(
            provider, query, limit=limit_per_period,
            time_range=TimeRange.ALL, **kwargs,
        )
        historical = SearchResults(
            platform=provider.name,
            query=query,
            error=f"{provider.name} only supports current/live data",
            time_range="historical",
        )

    return PerspectiveResults(
        platform=provider.name,
        query=query,
        recent=recent,
        historical=historical,
    )
