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

## Routing Hints — CRITICAL for Quality

When using the MCP `search_opinions` tool, **always pass `routing_hints`** to direct each
platform to the most relevant communities. This is the single biggest quality lever.

The format is comma-separated `platform:destination` pairs:

```
routing_hints: "reddit:fitness,reddit:loseit,4chan:fit,stackexchange:fitness"
```

### How to Choose Destinations

Think about where real humans would discuss the query:

| Query Topic | routing_hints |
|---|---|
| Gym/fitness/workout | `reddit:fitness,reddit:bodybuilding,4chan:fit,lemmy:fitness@lemmy.world` |
| Programming/code | `reddit:programming,4chan:g,stackexchange:stackoverflow,lemmy:programming@programming.dev` |
| Living in Berlin | `reddit:berlin,reddit:germany,4chan:int,lemmy:asklemmy@lemmy.ml` |
| Best headphones | `reddit:headphones,reddit:audiophile,forums:headfi` |
| Piano/keyboard music | `reddit:piano,reddit:WeAreTheMusicMakers,4chan:mu` |
| Mechanical keyboards | `reddit:MechanicalKeyboards,4chan:g` |
| Crypto/bitcoin | `reddit:CryptoCurrency,reddit:Bitcoin,4chan:biz,telegram:bitcoin` |
| Career advice | `reddit:careerguidance,reddit:cscareerquestions,4chan:adv,stackexchange:workplace` |
| Travel/backpacking | `reddit:travel,reddit:solotravel,4chan:trv,stackexchange:travel` |
| Skincare/appearance | `reddit:SkincareAddiction,reddit:mewing,4chan:fit` |
| Cooking/recipes | `reddit:Cooking,reddit:MealPrepSunday,4chan:ck,stackexchange:cooking` |
| AI/alignment/safety | `reddit:MachineLearning,4chan:g,telegram:OpenAI` |
| PC hardware/CPU/GPU | `reddit:buildapc,reddit:hardware,4chan:g,forums:anandtech` |
| Linux/open source | `reddit:linux,lemmy:linux@lemmy.ml,lemmy:technology@lemmy.world` |
| Privacy/selfhosting | `reddit:selfhosted,reddit:privacy,lemmy:privacy@lemmy.ml,lemmy:selfhosted@lemmy.world` |
| Gaming | `reddit:gaming,reddit:pcgaming,4chan:v,lemmy:gaming@lemmy.world` |

**Key rules:**
- Be specific with subreddits — `reddit:SkincareAddiction` not just `reddit:skincare`
- Include 2-4 subreddits per query for Reddit (it's the richest source)
- Match 4chan boards by topic: `/fit/` for fitness, `/g/` for tech, `/mu/` for music, etc.
- If you're unsure, omit `routing_hints` — auto-detection will kick in as fallback

### Platform Routing Guide

Use this to decide which platforms to prioritize:

| Query Type | Best Platforms |
|---|---|
| Tech/programming opinions | hackernews, stackexchange, reddit, lobsters, lemmy |
| AI/ML/alignment | lesswrong, hackernews, reddit, lemmy |
| Headphones/audio | forums (Head-Fi), reddit, 4chan |
| PC hardware/benchmarks | forums (AnandTech), reddit, 4chan |
| Health/fitness/appearance | reddit, 4chan (/fit/), lemmy |
| Travel/living abroad | reddit, telegram, lemmy |
| Product recommendations | reddit, hackernews, forums |
| Career/workplace | reddit, stackexchange (workplace), hackernews |
| Finance/investing | reddit, 4chan (/biz/), hackernews |
| Food/cooking | reddit, stackexchange (cooking) |
| Gaming | reddit, 4chan (/v/), lemmy |
| Linux/open source | lobsters, lemmy, reddit, stackexchange |
| Privacy/self-hosting | lemmy, reddit, lobsters |

## Important Rules

1. **Always cite sources** — include platform name and engagement metrics.
2. **Flag unvetted advice** — especially for health, finance, and legal topics.
3. **Note recency** — "this was posted in 2024" vs "last week" matters.
4. **Don't present opinions as facts** — frame as "people report" not "it is."
5. **Respect the signal** — a 2000-upvote post carries more weight than a 0-score post.
