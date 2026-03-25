# vox-pop

**Public opinion for LLMs.** Search HackerNews, Reddit, 4chan, Stack Exchange, and Telegram for what people *actually* think. Zero API keys.

Your LLM knows what textbooks say. Vox Pop tells it what people actually think.

---

## The Problem

```
User: "How do I debloat my face?"

Without vox-pop:
  Generic clinical answer: lymphatic drainage, reduce sodium,
  cold compress, drink water, sleep elevated...
  (correct but soulless — same as every health blog)
```

```
With vox-pop:
  ★ Searched 4 platforms: Reddit r/SkincareAddiction (23 threads),
    4chan /fit/ (8 threads), Stack Exchange Fitness (5 threads)

  Consensus (70%+ of threads):
    → Reduce sodium + drink 3L water/day (fastest visible result, 2-3 days)
    → Sleep elevated on back (multiple before/after posts)

  Controversial:
    → Gua sha: loved on Reddit, mocked on /fit/ as placebo
    → Mewing: looksmax-adjacent communities endorse, no clinical evidence

  What actually worked (high-engagement reports):
    → "Cut dairy for 2 weeks — face visibly deflated" (847 upvotes, r/SCA)
    → "Minoxidil bloat is real, went away month 3" (/fit/, recurring topic)

  ⚠ Some suggestions involve unvetted supplements.
    Cross-reference with medical sources.
```

**That** is the difference. Not "I searched Reddit." It's "my LLM understands what actual humans have experienced."

---

## Platforms

| Platform | Method | Auth | Tier |
|---|---|---|---|
| **HackerNews** | [Algolia API](https://hn.algolia.com/api) | None | 1 — stable |
| **Reddit** | [Pullpush](https://pullpush.io) → [Arctic Shift](https://arctic-shift.photon-reddit.com) → [Redlib](https://github.com/redlib-org/redlib) | None | 1 — fallback chain |
| **4chan** | [Official API](https://github.com/4chan/4chan-API) | None | 1 — stable since 2012 |
| **Stack Exchange** | [Official API](https://api.stackexchange.com/docs) (180+ sites) | None (300 req/day) | 1 — stable |
| **Telegram** | Public channel web preview (`t.me/s/`) | None | 1 — stable |

**Zero API keys.** Install and it works.

---

## Install

```bash
pip install vox-pop
```

## Usage

### Python

```python
import asyncio
from vox_pop import search_multiple
from vox_pop.core import format_context, get_default_providers

async def main():
    results = await search_multiple(
        "best laptop for programming 2026",
        providers=get_default_providers(),
    )
    print(format_context(results))

asyncio.run(main())
```

### CLI

```bash
# Search all platforms
vox-pop search "is Rust worth learning in 2026"

# Search specific platforms
vox-pop search "best budget phone" --platforms reddit,hackernews

# Get thread comments
vox-pop thread hackernews 12345678

# List available platforms
vox-pop platforms
```

### MCP Server (Claude Code, Cursor, Windsurf, etc.)

Add to your MCP config:

```json
{
  "mcpServers": {
    "vox-pop": {
      "command": "python",
      "args": ["-m", "vox_pop.server"]
    }
  }
}
```

Then your LLM can call:

```
search_opinions(query="best laptop 2026", platforms="auto")
get_thread_opinions(platform="hackernews", thread_id="12345678")
list_available_platforms()
```

### Claude Code Plugin

Install the plugin:

```bash
claude plugin add /path/to/vox-pop
```

The **vox-pop skill** auto-triggers when your question would benefit from real public opinion. No manual invocation needed — just ask naturally:

```
> "What do people think about living in Berlin?"
> "Should I use Next.js or Remix?"
> "Best gym routine for beginners?"
```

For manual search: `/vox-search "your query"`

---

## How It Works

```
┌─────────────────────────────────────────┐
│  Claude Code Plugin / MCP Client        │  ← what you see
│  • Auto-triggering skill                │
│  • /vox-search command                  │
├─────────────────────────────────────────┤
│  MCP Server                             │  ← what any LLM can use
│  • search_opinions()                    │
│  • get_thread_opinions()                │
├─────────────────────────────────────────┤
│  Python Provider Library                │  ← the engine
│  • HackerNews (Algolia)                 │
│  • Reddit (Pullpush → Arctic Shift      │
│           → Redlib fallback)            │
│  • 4chan (official API + catalog search) │
│  • Stack Exchange (180+ communities)    │
│  • Telegram (public channel preview)    │
└─────────────────────────────────────────┘
```

Each provider implements a fallback chain where applicable. If one source is down, the next is tried automatically. You always get results.

---

## Smart Routing

Vox-pop auto-routes queries to the most relevant platforms:

| Query Type | Auto-selected Platforms |
|---|---|
| Tech/programming | HackerNews, Stack Overflow, Reddit |
| Health/fitness | Reddit, 4chan /fit/, SE Fitness |
| Travel/living | Reddit, Telegram |
| Finance/crypto | Reddit, 4chan /biz/, HackerNews |
| Career/workplace | Reddit, SE Workplace, HackerNews |
| Cooking/food | Reddit, SE Cooking |

Override with `--platforms` or the `platforms` parameter.

---

## Roadmap

### v0.2 — Regional Platforms
- **DC Inside** (Korea) — Korea's 4chan equivalent, massive public forum
- **Naver Blog/Café** (Korea) — dominant Korean platform
- **5ch** (Japan) — successor to 2ch

### v0.3 — Niche & Zoomer
- **TikTok** (unofficial, fragile) — comments are opinion gold
- **Discord** (public servers via bot API)
- **Looksmax.org** and other XenForo forums
- **YouTube** comments via Invidious

### v1.0 — Sentiment Aggregation
- Built-in opinion synthesis (consensus / controversy / outlier detection)
- Structured JSON output with confidence scores
- Historical trend tracking ("what did people think about X in 2023 vs now")

---

## Contributing

PRs welcome — especially:
- **New providers** — follow the pattern in `src/vox_pop/providers/base.py`
- **Better routing** — improve the keyword → platform mapping
- **Redlib/Nitter instances** — report working/dead instances
- **Regional platforms** — we want DC Inside, Naver, 5ch, VK, Bilibili

---

## Security & Ethics

- **Zero auth by default.** We only access publicly available data through official APIs and public web endpoints. No scraping behind login walls.
- **No credential storage.** Optional API keys (e.g., Stack Exchange) are passed at runtime, never persisted.
- **Rate limiting respected.** All providers enforce the rate limits documented by the platform.
- **User-Agent transparency.** We identify as `vox-pop/0.1` in all requests.
- **No PII collection.** Author names from public posts are included for attribution only and never stored.

---

## License

MIT

---

*vox populi, vox dei — the voice of the people is the voice of god*
