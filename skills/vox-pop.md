---
name: vox-pop
description: >
  Auto-activates when the user asks questions where real public opinion, lived
  experience, or community sentiment would meaningfully improve the answer beyond
  generic/clinical responses. Triggers on: product recommendations, life decisions,
  health/fitness routines, travel and living advice, career and workplace questions,
  tool/framework comparisons, consumer sentiment, lifestyle optimization, and
  "should I..." or "what do people think about..." style questions.
  Does NOT trigger on: pure factual lookups, math, code syntax, creative writing,
  or questions with definitive textbook answers.
---

# Vox Pop — Public Opinion Context Layer

When this skill activates, you are adding **real human opinion context** to your response.
This transforms a generic LLM answer into one grounded in what people have actually experienced.

## How It Works

1. **Detect** that the user's question would benefit from public opinion (this skill
   already triggered, so the detection happened).
2. **Search** across platforms using the vox-pop CLI or MCP server.
3. **Aggregate** the results into: consensus, controversy, outliers, and trust signals.
4. **Present** the enriched answer — always cite platform and engagement metrics.

## Step 1: Search

Run the vox-pop CLI to search across platforms. Adjust the query to be search-friendly
(strip filler words, focus on the core topic):

```bash
cd "${CLAUDE_PLUGIN_ROOT}"
python -m vox_pop.cli search "<search-optimized query>" --platforms auto --limit 5
```

If you need to target specific platforms:
```bash
python -m vox_pop.cli search "<query>" --platforms hackernews,reddit --limit 8
```

If the auto search doesn't return good results, try narrowing:
```bash
python -m vox_pop.cli search "<query>" --platforms reddit --limit 10
python -m vox_pop.cli search "<query>" --platforms 4chan --limit 10
```

For questions where **how opinion has changed over time matters** (tech choices,
product reputation, company culture, etc.), use perspective mode:
```bash
python -m vox_pop.cli search "<query>" --perspective --platforms hackernews,reddit --limit 5
```
This returns both historical (1+ year old) and recent (last 6 months) opinions.

## Step 2: Aggregate

After collecting results, organize them into this structure for your response:

### Response Template

```
★ Public Opinion Context ─────────────────────────
Searched: [platforms searched] | [N total results]

**Consensus** (mentioned in majority of sources):
→ [What most people agree on]

**Controversial/Split**:
→ [Topics where communities disagree, noting which community says what]

**Surprising/Outlier**:
→ [Unexpected findings that might be valuable]

**Trust Signals**:
→ [Highest-engagement results with platform + score]

⚠ Caveats: [Any quality warnings — unvetted medical advice, anecdotal evidence, etc.]
─────────────────────────────────────────────────
```

### Perspective Template (when --perspective was used)

```
★ Public Opinion: Then vs Now ───────────────────
Topic: [query]

**Historical** (1+ year ago):
→ [What people used to think/recommend]
→ [Old consensus, now-outdated tools/methods]

**Recent** (last 6 months):
→ [Current opinion — what changed?]
→ [New consensus, updated recommendations]

**Shift**: [Brief summary of how opinion evolved]
─────────────────────────────────────────────────
```

## Step 3: Integrate

Weave the opinion context naturally into your answer. Don't just dump the raw results —
synthesize them alongside your own knowledge. The opinion data should ENHANCE your answer,
not replace it.

**Good**: "Most people on Reddit's r/SkincareAddiction (847 upvotes) found that cutting dairy
for 2 weeks helped with facial bloating. This aligns with the clinical evidence that dairy
can contribute to water retention in some individuals."

**Bad**: "Here are 10 Reddit posts about face bloating: [raw dump]"

## Platform Routing Guide

Use this to decide which platforms to prioritize:

| Query Type | Best Platforms |
|---|---|
| Tech/programming opinions | hackernews, stackexchange, reddit |
| Health/fitness/appearance | reddit, 4chan (/fit/) |
| Travel/living abroad | reddit, telegram |
| Product recommendations | reddit, hackernews |
| Career/workplace | reddit, stackexchange (workplace), hackernews |
| Finance/investing | reddit, 4chan (/biz/), hackernews |
| Food/cooking | reddit, stackexchange (cooking) |
| Gaming | reddit, 4chan (/v/) |

## Important Rules

1. **Always cite sources** — include platform name and engagement metrics.
2. **Flag unvetted advice** — especially for health, finance, and legal topics.
3. **Note recency** — "this was posted in 2024" vs "last week" matters.
4. **Don't present opinions as facts** — frame as "people report" not "it is."
5. **Respect the signal** — a 2000-upvote post carries more weight than a 0-score post.
