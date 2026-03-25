---
name: vox-search
description: >
  Manual search command. Use when the user explicitly asks to search public opinion
  with "/vox" or "/vox-search". Accepts a query and optional platform filter.
  Examples: "/vox best laptop 2026", "/vox reddit maastricht university".
---

# Vox Search — Manual Public Opinion Search

The user explicitly requested a public opinion search.

## Usage

Parse the user's input to extract:
- **Query**: The search terms
- **Platform filter**: If they mentioned a specific platform (e.g., "reddit", "hackernews")

## Execute

```bash
cd "${CLAUDE_PLUGIN_ROOT}"
python -m vox_pop.cli search "<query>" --platforms <platforms|auto> --limit 8
```

## Present Results

Show the raw results with trust signals, then provide a brief synthesis:

1. List the top results with platform, score, and key quote
2. Note any consensus or disagreement across platforms
3. Flag low-quality or potentially unreliable results
4. Suggest follow-up searches if the results seem thin

Keep it concise — the user asked for a search, not an essay.
