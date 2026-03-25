<div align="center">

<br>

```
   ██╗   ██╗ ██████╗ ██╗  ██╗      ██████╗  ██████╗ ██████╗
    ██║   ██║██╔═══██╗╚██╗██╔╝      ██╔══██╗██╔═══██╗██╔══██╗
    ██║   ██║██║   ██║ ╚███╔╝ █████╗██████╔╝██║   ██║██████╔╝
   ╚██╗ ██╔╝██║   ██║ ██╔██╗ ╚════╝██╔═══╝ ██║   ██║██╔═══╝
╚████╔╝ ╚██████╔╝██╔╝ ██╗     ██║     ╚██████╔╝██║
╚═══╝   ╚═════╝ ╚═╝  ╚═╝     ╚═╝      ╚═════╝ ╚═╝
```

### Your LLM knows what textbooks say.<br>This tells it what people *actually* think.

**HackerNews** &bull; **Reddit** &bull; **4chan** &bull; **Stack Exchange** &bull; **Telegram**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-8A2BE2.svg)](https://modelcontextprotocol.io)
[![Zero API Keys](https://img.shields.io/badge/API_Keys-Zero-brightgreen.svg)](#)

[Install](#install) &bull; [Quick Start](#quick-start) &bull; [Platforms](#platforms) &bull; [MCP Server](#mcp-server) &bull; [Claude Code Plugin](#claude-code-plugin) &bull; [Roadmap](#roadmap)

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

That's it. No API keys. No config. No accounts.

<br>

## Quick Start

**CLI** — search all platforms in one command:

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

| | Platform | Source | Status |
|:---:|---|---|:---:|
| ![HN](https://img.shields.io/badge/Y-FF6600?style=flat-square) | **HackerNews** | [Algolia Search API](https://hn.algolia.com/api) | Stable |
| ![Reddit](https://img.shields.io/badge/r/-FF4500?style=flat-square) | **Reddit** | [Pullpush](https://pullpush.io) + [Arctic Shift](https://arctic-shift.photon-reddit.com) + [Redlib](https://github.com/redlib-org/redlib) fallback | Stable |
| ![4chan](https://img.shields.io/badge/4-008000?style=flat-square) | **4chan** | [Official JSON API](https://github.com/4chan/4chan-API) (since 2012) | Stable |
| ![SE](https://img.shields.io/badge/SE-F48024?style=flat-square) | **Stack Exchange** | [Official API](https://api.stackexchange.com/docs) &mdash; 180+ communities | Stable |
| ![TG](https://img.shields.io/badge/TG-26A5E4?style=flat-square) | **Telegram** | Public channel web preview (`t.me/s/`) | Stable |

<details>
<summary><strong>Smart routing</strong> — queries auto-route to the best platforms</summary>

<br>

| Your question is about... | Searched automatically |
|---|---|
| Tech / programming | HackerNews, Stack Overflow, Reddit |
| Health / fitness / appearance | Reddit, 4chan /fit/, SE Fitness |
| Travel / living abroad | Reddit, Telegram |
| Finance / crypto | Reddit, 4chan /biz/, HackerNews |
| Career / workplace | Reddit, SE Workplace, HackerNews |
| Cooking / food | Reddit, SE Cooking |

Override anytime with `--platforms reddit,hackernews`

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

Your LLM gets three tools:

| Tool | What it does |
|---|---|
| `search_opinions` | Search all platforms for opinions on a topic |
| `search_opinions_perspective` | **Then vs Now** — historical + recent opinions side by side |
| `get_thread_opinions` | Dive into a specific thread's comments |
| `list_available_platforms` | Check what's available and healthy |

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
┌─────────────────────────────────────────────┐
│  Layer 3: Claude Code / MCP Client          │  You see this
│  Auto-triggering skill + /vox-search        │
├─────────────────────────────────────────────┤
│  Layer 2: MCP Server                        │  Any LLM can use this
│  search_opinions() + get_thread_opinions()  │
├─────────────────────────────────────────────┤
│  Layer 1: Python Library                    │  The engine
│  5 providers with fallback chains           │
│  HN · Reddit · 4chan · SE · Telegram        │
└─────────────────────────────────────────────┘
```

Each provider implements **automatic fallback** — if one source is down, the next is tried. You always get results.

<br>

## Roadmap

| Version | What's coming |
|:---:|---|
| **v0.2** | **Regional** — DC Inside (Korea), Naver, 5ch (Japan) |
| **v0.3** | **Niche** — TikTok, Discord, YouTube comments, Looksmax, XenForo forums |
| **v1.0** | **Synthesis** — built-in consensus/controversy detection, confidence scores, trend tracking |

<br>

## Contributing

The easiest way to contribute:

```
New provider?     → Follow the pattern in src/vox_pop/providers/base.py
Better routing?   → Improve keyword → platform mapping in any provider
Dead instance?    → Open an issue with the instance URL
Regional platform → DC Inside, Naver, 5ch, VK, Bilibili — all welcome
```

<br>

## Security

| | |
|---|---|
| **Data access** | Public data only — official APIs and public web endpoints. No login-wall scraping. |
| **Credentials** | Zero stored. Optional keys (e.g. SE) passed at runtime, never persisted. |
| **Rate limits** | Respected per-platform. Built-in concurrency guards. |
| **User-Agent** | Transparent: `vox-pop/0.1` in all requests. |
| **PII** | Author names from public posts included for attribution only. Never stored. |

<br>

---

<div align="center">

*vox populi, vox dei*<br>
the voice of the people is the voice of god

<br>

MIT License

</div>
