<div align="center">

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
  <img alt="VOX-POP" src="assets/logo-dark.svg" width="420">
</picture>

### Your LLM knows what textbooks say.<br>This tells it what people *actually* think.

**9 platforms** &bull; **Semantic routing** &bull; **LLM intelligence layer** &bull; **Works without API keys**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-8A2BE2.svg)](https://modelcontextprotocol.io)
[![No Keys Required](https://img.shields.io/badge/API_Keys-Optional-brightgreen.svg)](#how-routing-works)

[Install](#install) &bull; [Quick Start](#quick-start) &bull; [Platforms](#platforms) &bull; [How Routing Works](#how-routing-works) &bull; [MCP Server](#mcp-server) &bull; [Claude Code Plugin](#claude-code-plugin) &bull; [Roadmap](#roadmap)

</div>

---

<br>

## Why?

<table>
<tr>
<td width="50%">

**Without vox-pop**

```
> How do I debloat my face?

Lymphatic drainage, reduce sodium,
cold compress, drink water,
sleep elevated...

(correct but soulless — same answer
 as every health blog since 2015)
```

</td>
<td width="50%">

**With vox-pop**

```
★ Searched: Reddit, 4chan /fit/, SE Fitness

Consensus (70%+ of threads):
 → Reduce sodium + 3L water/day
 → Sleep elevated on back

Controversial:
 → Gua sha: loved on Reddit,
   mocked on /fit/ as placebo

What actually worked:
 → "Cut dairy for 2 weeks — face
    visibly deflated" (847↑ r/SCA)
 → "Minox bloat is real, went away
    month 3" (/fit/, recurring)

⚠ Some suggestions are unvetted.
```

</td>
</tr>
</table>

<br>

## Install

```bash
pip install vox-pop
```

That's it. All 9 platforms work with zero API keys. Optional LLM key unlocks smarter routing (see [How Routing Works](#how-routing-works)).

<br>

## Quick Start

**CLI** — search all 9 platforms in one command:

```bash
vox-pop search "should I learn Rust or Go"
```

**Perspective mode** — see how opinions evolved over time:

```bash
vox-pop search "rust vs go" --perspective --platforms hackernews,reddit
```

```
## hackernews — Then vs Now

Historical (1+ year ago):
> "Rust vs. Go"
  — hackernews | +481 points | 580 replies | 2017-01-18

Recent (last 6 months):
> "Rust vs. Go: Memory Management"
  — hackernews | +2 points | 2025-11-15

## reddit — Then vs Now

Historical:
> "Experienced developer but total beginner in Rust..."
  — reddit | +124 points | 34 replies | 2025-03-14

Recent:
> "I rebuilt the same API in Java, Go, Kotlin, and Rust — here are the numbers"
  — reddit | +174 points | 59 replies | 2026-03-19
```

The shift tells a story: **2017 was a flame war. 2026 is domain-specific pragmatism.**

---

**Standard search** — flat results from all platforms:

```bash
vox-pop search "should I learn Rust or Go" --limit 3
```

```
### hackernews (45 found)
> "I am a full stack TypeScript dev looking to broaden my skill set..."
  — hackernews | +78 points | 42 replies | by throwaway_dev
  Source: https://news.ycombinator.com/item?id=41907717

### 4chan /g/ (12 found)
> "Rust is a mass psychosis. Go is boring but you'll actually ship..."
  — 4chan /g/ | 129 replies | by Anonymous

### reddit (8 found)
> "After 2 years with both: Rust for systems, Go for services..."
  — reddit | +234 points | 87 replies | by senior_dev_42
```

**Python** — embed in your own tools:

```python
import asyncio
from vox_pop.core import search_multiple, format_context, get_default_providers

async def main():
    results = await search_multiple(
        "best laptop for programming",
        providers=get_default_providers(),
    )
    print(format_context(results))

asyncio.run(main())
```

<br>

## Platforms

Every platform works out of the box. No tokens, no OAuth, no rate limit headaches.

| | Platform | Source | Time Filter | Threads |
|:---:|---|---|:---:|:---:|
| ![HN](https://img.shields.io/badge/Y-FF6600?style=flat-square) | **HackerNews** | [Algolia Search API](https://hn.algolia.com/api) | Yes | Yes |
| ![Reddit](https://img.shields.io/badge/r/-FF4500?style=flat-square) | **Reddit** | [Pullpush](https://pullpush.io) + [Arctic Shift](https://arctic-shift.photon-reddit.com) + [Redlib](https://github.com/redlib-org/redlib) fallback | Yes | &mdash; |
| ![4chan](https://img.shields.io/badge/4-008000?style=flat-square) | **4chan** | [Official JSON API](https://github.com/4chan/4chan-API) (since 2012) | &mdash; | Yes |
| ![SE](https://img.shields.io/badge/SE-F48024?style=flat-square) | **Stack Exchange** | [Official API](https://api.stackexchange.com/docs) &mdash; 180+ communities | Yes | Yes |
| ![TG](https://img.shields.io/badge/TG-26A5E4?style=flat-square) | **Telegram** | Public channel web preview (`t.me/s/`) | &mdash; | &mdash; |
| ![Lobsters](https://img.shields.io/badge/L-AC0000?style=flat-square) | **Lobsters** | [lobste.rs](https://lobste.rs) JSON API + search scraping | Yes | &mdash; |
| ![Lemmy](https://img.shields.io/badge/LE-00BC8C?style=flat-square) | **Lemmy** | [Public REST API](https://join-lemmy.org/api/) &mdash; federated instances | Yes | Yes |
| ![LW](https://img.shields.io/badge/LW-5F9B65?style=flat-square) | **LessWrong** | [GraphQL API](https://www.lesswrong.com/graphql) | Yes | Yes |
| ![Forums](https://img.shields.io/badge/XF-E7700D?style=flat-square) | **XenForo Forums** | HTML scraping (Head-Fi, AnandTech, etc.) | &mdash; | &mdash; |

<br>

## How Routing Works

Queries can be anything — a single word, a paragraph, an essay-length D&D rules question. vox-pop understands them all through a **four-tier routing system**:

```
User query: "i was looking into a solid laptop for linux
             something from hp, what would a savvy person pick"
                                    │
    ┌───────────────────────────────▼──────────────────────────────┐
    │  Tier 1: MCP Hints                                          │
    │  Calling LLM provides routing_hints directly                │
    │  (skips all other tiers)                                    │
    ├─────────────────────────────────────────────────────────────┤
    │  Tier 2: LLM Query Rewrite          ← like Perplexity      │
    │  Cheap LLM call rewrites query to search-optimized form     │
    │  "hp laptop linux compatibility" + routes to communities    │
    │  Supports: Anthropic, OpenAI, Ollama (local/free)           │
    ├─────────────────────────────────────────────────────────────┤
    │  Tier 3: Semantic Embeddings         ← free, no API key     │
    │  FastEmbed (33MB model) understands meaning, not keywords   │
    │  Dynamic catalog: 77 4chan boards + 180 SE sites + static   │
    │  "contradictory spell behaviour" → SE:rpg, r/DnD, /tg/     │
    ├─────────────────────────────────────────────────────────────┤
    │  Tier 4: Broad Defaults                                     │
    │  Search popular destinations everywhere                     │
    └─────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    Routes to: r/buildapc, r/linux, r/hardware │ /g/
               SE:hardwarerecs, SE:askubuntu │ lemmy:linux@lemmy.ml
```

**Tier 2** works like Perplexity/ChatGPT Search — the LLM rewrites your conversational query into a clean search string and picks the right communities. Set any of these env vars to enable:

```bash
ANTHROPIC_API_KEY=...   # Uses Claude Haiku (~$0.0003/query)
OPENAI_API_KEY=...      # Uses GPT-4o Mini
OLLAMA_HOST=...         # Uses local Ollama (free)
```

**Tier 3** runs entirely locally with zero API keys. A 33MB embedding model understands that "contradictory spell behaviour on a creature" means tabletop RPG rules — zero shared keywords needed. On first run, it fetches all 4chan boards and Stack Exchange sites dynamically, embeds everything, and caches to disk.

| | Cold start | Warm start | Singleton |
|---|---|---|---|
| **Tier 3 timing** | ~7s | ~1.3s | instant |

**No configuration needed.** If an LLM key is set, Tier 2 is used. Otherwise Tier 3 handles it. If fastembed isn't installed, Tier 4 (broad search) still works.

<details>
<summary><strong>Routing examples</strong></summary>

<br>

| Query | Routes to |
|---|---|
| "best hp laptop for linux" | r/buildapc, r/linux, r/hardware, /g/, SE:hardwarerecs, SE:askubuntu |
| "contradictory spell effects on a creature" | r/dndnext, r/DnD, /tg/, SE:rpg |
| "best mechanical keyboard for programming" | r/MechanicalKeyboards, /g/, SE:hardwarerecs |
| "what are the risks of yield farming" | r/CryptoCurrency, SE:tezos, telegram:ethereum |
| "how to make authentic kimchi jjigae" | r/Cooking, /ck/ |

</details>

<br>

## MCP Server

Works with **Claude Code**, **Cursor**, **Windsurf**, and any MCP-compatible client.

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

Your LLM gets four tools:

| Tool | What it does |
|---|---|
| `search_opinions` | Search all platforms for opinions on a topic |
| `search_opinions_perspective` | **Then vs Now** — historical + recent opinions side by side |
| `get_thread_opinions` | Dive into a specific thread's comments |
| `list_available_platforms` | Check what's available and healthy |

The `routing_hints` parameter lets the calling LLM specify exactly where to search:

```
routing_hints: "reddit:MechanicalKeyboards,4chan:g,stackexchange:hardwarerecs"
```

When no hints are provided, the [routing system](#how-routing-works) handles it automatically.

<br>

## Claude Code Plugin

```bash
claude plugin add /path/to/vox-pop
```

The skill **auto-triggers** when your question would benefit from real opinions. Just ask naturally:

```
> "What do people think about living in Berlin?"    → activates
> "Should I use Next.js or Remix?"                  → activates
> "Best gym routine for beginners?"                 → activates
> "What's the capital of France?"                   → does not activate
```

Manual search: `/vox-search "your query"`

<br>

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Layer 3: Claude Code / MCP Client                       │
│  Auto-triggering skill + /vox-search                     │
├──────────────────────────────────────────────────────────┤
│  Layer 2: MCP Server                                     │
│  search_opinions · perspectives · threads · list         │
├──────────────────────────────────────────────────────────┤
│  Layer 1: Python Library                                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Smart Router (4-tier)                             │  │
│  │  MCP hints → LLM rewrite → FastEmbed → broad      │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  9 Providers with fallback chains                  │  │
│  │  HN · Reddit · 4chan · SE · Telegram               │  │
│  │  Lobsters · Lemmy · LessWrong · XenForo Forums     │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Dynamic Catalog                                   │  │
│  │  77 4chan boards + 180 SE sites fetched from APIs   │  │
│  │  + 120 static destinations · cached to disk         │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

Each provider implements **automatic fallback** — if one source is down, the next is tried. Reddit alone has three fallback sources (Pullpush → Arctic Shift → Redlib).

<br>

## Roadmap

| Version | Status | What |
|:---:|:---:|---|
| **v0.1** | Shipped | 5 providers (HN, Reddit, 4chan, SE, Telegram), MCP server, Claude Code plugin |
| **v0.2** | **Current** | 9 providers, 4-tier smart routing, LLM query rewriting, FastEmbed semantic routing, dynamic catalog |
| **v0.3** | Next | **Regional** — DC Inside (Korea), Naver, 5ch (Japan) |
| **v0.4** | Planned | **Niche** — TikTok, Discord, YouTube comments, Looksmax |
| **v1.0** | Planned | **Synthesis** — built-in consensus/controversy detection, confidence scores, trend tracking |

<br>

## Contributing

```
New provider?          → Subclass Provider in src/vox_pop/providers/base.py
New routing destination → Add to DESTINATIONS in router.py (one line)
Dynamic catalog source → Add a _fetch_*_destinations() function in router.py
Better LLM prompt?     → Improve _LLM_SYSTEM in router.py
Multilingual support?  → Swap FastEmbed model to bge-m3 in SemanticRouter
Dead instance?         → Open an issue with the instance URL
Regional platform?     → DC Inside, Naver, 5ch, VK, Bilibili — all welcome
```

<br>

## Security

| | |
|---|---|
| **Data access** | Public data only — official APIs and public web endpoints. No login-wall scraping. |
| **Credentials** | Zero stored. Optional LLM keys passed via env vars at runtime, never written to disk. |
| **LLM routing** | When `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set, your query text (up to 4000 chars) is sent to the respective LLM API for routing only. No queries are sent externally without an explicit API key. Without keys, routing runs entirely locally via FastEmbed. |
| **Rate limits** | Respected per-platform. Built-in concurrency guards. |
| **User-Agent** | Transparent: `vox-pop/0.2` in all requests. |
| **Caching** | API responses (7 days) and embeddings cached locally at `~/.cache/vox-pop/`. No data sent to third parties. Embeddings stored as JSON, no serialization dependencies. |
| **PII** | Author names from public posts included for attribution only. Never stored beyond the response. |

<br>

---

<div align="center">

*vox populi, vox dei*<br>
the voice of the people is the voice of god

<br>

MIT License

</div>
