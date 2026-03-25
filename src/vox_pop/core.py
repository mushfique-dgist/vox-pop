"""Core search orchestration for vox-pop.

Provides ``search`` (single platform) and ``search_multiple``
(parallel multi-platform) as the main public API.
"""

from __future__ import annotations

import asyncio
from typing import Any

from vox_pop.providers.base import Provider, SearchResults


async def search(
    query: str,
    *,
    provider: Provider,
    limit: int = 10,
    **kwargs: Any,
) -> SearchResults:
    """Search a single provider."""
    return await provider.search(query, limit=limit, **kwargs)


async def search_multiple(
    query: str,
    *,
    providers: list[Provider],
    limit_per_platform: int = 10,
    **kwargs: Any,
) -> list[SearchResults]:
    """Search multiple providers in parallel.

    Returns one ``SearchResults`` per provider, in the same order.
    Failed providers return a result with ``error`` set — they
    never raise or block other providers.
    """
    tasks = [
        _safe_search(p, query, limit=limit_per_platform, **kwargs)
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


def get_provider(name: str, **kwargs: Any) -> Provider:
    """Instantiate a provider by name.

    Raises ``KeyError`` if the provider name is unknown.
    """
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
    **kwargs: Any,
) -> SearchResults:
    """Wrap provider.search so that exceptions become error results."""
    try:
        return await provider.search(query, limit=limit, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return SearchResults(
            platform=provider.name,
            query=query,
            error=f"Unhandled: {type(exc).__name__}: {exc}",
        )
