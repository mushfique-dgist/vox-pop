"""Platform providers for vox-pop."""

from vox_pop.providers.hackernews import HackerNewsProvider
from vox_pop.providers.reddit import RedditProvider
from vox_pop.providers.fourchan import FourChanProvider
from vox_pop.providers.stackexchange import StackExchangeProvider
from vox_pop.providers.telegram import TelegramProvider
from vox_pop.providers.lobsters import LobstersProvider
from vox_pop.providers.lemmy import LemmyProvider
from vox_pop.providers.lesswrong import LessWrongProvider
from vox_pop.providers.xenforo import XenForoProvider

PROVIDERS: dict[str, type] = {
    "hackernews": HackerNewsProvider,
    "reddit": RedditProvider,
    "4chan": FourChanProvider,
    "stackexchange": StackExchangeProvider,
    "telegram": TelegramProvider,
    "lobsters": LobstersProvider,
    "lemmy": LemmyProvider,
    "lesswrong": LessWrongProvider,
    "forums": XenForoProvider,
}

__all__ = [
    "PROVIDERS",
    "HackerNewsProvider",
    "RedditProvider",
    "FourChanProvider",
    "StackExchangeProvider",
    "TelegramProvider",
    "LobstersProvider",
    "LemmyProvider",
    "LessWrongProvider",
    "XenForoProvider",
]
