"""Platform providers for vox-pop."""

from vox_pop.providers.hackernews import HackerNewsProvider
from vox_pop.providers.reddit import RedditProvider
from vox_pop.providers.fourchan import FourChanProvider
from vox_pop.providers.stackexchange import StackExchangeProvider
from vox_pop.providers.telegram import TelegramProvider

PROVIDERS: dict[str, type] = {
    "hackernews": HackerNewsProvider,
    "reddit": RedditProvider,
    "4chan": FourChanProvider,
    "stackexchange": StackExchangeProvider,
    "telegram": TelegramProvider,
}

__all__ = [
    "PROVIDERS",
    "HackerNewsProvider",
    "RedditProvider",
    "FourChanProvider",
    "StackExchangeProvider",
    "TelegramProvider",
]
