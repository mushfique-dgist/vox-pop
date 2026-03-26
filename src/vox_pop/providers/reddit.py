"""Reddit provider with a multi-source fallback chain.

Tier 1 (Pullpush) → Tier 1 (Arctic Shift) → Tier 2 (Redlib).

All three sources are free and require zero authentication.
Supports time filtering for perspective searches.
Includes subreddit routing to reduce noise.

Pullpush:     Pushshift successor, full-text search, live-ish data.
Arctic Shift: Historical archive, query + subreddit required.
Redlib:       Privacy frontend, renders Reddit server-side as HTML.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from vox_pop.providers.base import (
    OpinionResult,
    Provider,
    SearchResults,
    TimeRange,
    TopicProfile,
    relevance_filter,
    safe_int,
    score_route,
    strip_html,
)

_TIMEOUT = 20.0
_POST_URL = "https://www.reddit.com{permalink}"

# ── Source endpoints ────────────────────────────────────────────

_PULLPUSH_POSTS = "https://api.pullpush.io/reddit/search/submission/"
_PULLPUSH_COMMENTS = "https://api.pullpush.io/reddit/search/comment/"

_ARCTIC_POSTS = "https://arctic-shift.photon-reddit.com/api/posts/search"

# Redlib instances ordered by observed reliability (March 2026).
_REDLIB_INSTANCES = [
    "https://redlib.privacyredirect.com",
    "https://redlib.zaggy.nl",
    "https://rl.bloat.cat",
    "https://redlib.catsarch.com",
    "https://safereddit.com",
]

# ── Subreddit profiles for scoring-based routing ──────────────

SUBREDDIT_PROFILES: list[TopicProfile] = [
    # Tech / programming
    TopicProfile("programming", [
        "programming", "code", "coding", "software", "developer",
        "open source", "github", "debug",
    ]),
    TopicProfile("learnprogramming", [
        "learn programming", "learn to code", "beginner programming",
        "coding bootcamp", "first language",
    ]),
    TopicProfile("Python", [
        "python", "django", "flask", "pandas", "numpy", "pip",
    ]),
    TopicProfile("learnpython", [
        "learn python", "python beginner", "python tutorial",
    ]),
    TopicProfile("javascript", [
        "javascript", "typescript", "react", "vue", "angular", "node",
        "nextjs", "next.js", "frontend", "front end",
    ]),
    TopicProfile("webdev", [
        "web development", "web dev", "frontend", "backend", "fullstack",
        "html", "css", "responsive",
    ]),
    TopicProfile("rust", ["rust", "rustlang", "cargo", "borrow checker"]),
    TopicProfile("golang", ["golang", "go language", "goroutine"]),
    TopicProfile("technology", [
        "tech", "technology", "gadget", "innovation", "silicon valley",
    ]),
    TopicProfile("LocalLLaMA", [
        "llm", "local llm", "llama", "ai model", "fine tuning",
        "artificial intelligence", "machine learning", "deep learning",
        "gpt", "claude", "chatgpt",
    ]),
    TopicProfile("MachineLearning", [
        "machine learning", "deep learning", "neural network", "ai research",
        "transformer", "training", "inference",
    ]),
    TopicProfile("ClaudeAI", ["claude", "anthropic", "claude ai"]),

    # Hardware / gadgets
    TopicProfile("SuggestALaptop", [
        "laptop", "notebook", "chromebook", "best laptop",
        "laptop for programming", "laptop for college",
    ]),
    TopicProfile("buildapc", [
        "build pc", "pc build", "custom pc", "gpu", "cpu",
        "graphics card", "motherboard", "ram",
    ]),
    TopicProfile("PickAnAndroidForMe", [
        "android phone", "best phone", "budget phone", "smartphone",
    ]),
    TopicProfile("iphone", ["iphone", "ios", "apple phone"]),
    TopicProfile("MechanicalKeyboards", [
        "mechanical keyboard", "keycaps", "switches", "custom keyboard",
        "keyboard build", "cherry mx", "gateron",
    ]),
    TopicProfile("headphones", [
        "headphone", "earbuds", "earphone", "iem", "over ear",
        "noise cancelling", "wireless earbuds", "audiophile",
    ]),
    TopicProfile("HeadphoneAdvice", [
        "best headphone", "headphone recommendation", "which headphone",
    ]),
    TopicProfile("Monitors", [
        "monitor", "display", "ultrawide", "4k monitor", "gaming monitor",
    ]),
    TopicProfile("MouseReview", [
        "mouse", "gaming mouse", "wireless mouse", "mouse recommendation",
    ]),
    TopicProfile("cameras", [
        "camera", "dslr", "mirrorless", "photography gear", "lens",
    ]),

    # Fitness / health
    TopicProfile("Fitness", [
        "fitness", "gym", "workout", "exercise", "lifting", "strength",
        "muscle", "bodybuilding", "cardio", "bench press", "squat",
        "deadlift", "personal trainer", "routine",
    ]),
    TopicProfile("bodyweightfitness", [
        "bodyweight", "calisthenics", "pull up", "push up", "home workout",
    ]),
    TopicProfile("loseit", [
        "weight loss", "lose weight", "diet", "calorie deficit", "obesity",
    ]),
    TopicProfile("running", [
        "running", "marathon", "jogging", "5k", "10k", "couch to 5k",
        "treadmill", "trail running",
    ]),
    TopicProfile("yoga", ["yoga", "flexibility", "stretching", "meditation"]),
    TopicProfile("SkincareAddiction", [
        "skincare", "skin care", "acne", "moisturizer", "sunscreen",
        "retinol", "face routine", "skin routine", "face", "bloat",
        "pore", "wrinkle", "glow up",
    ]),
    TopicProfile("nutrition", [
        "nutrition", "diet", "macro", "protein", "vitamin", "supplement",
        "meal plan", "calorie",
    ]),
    TopicProfile("mentalhealth", [
        "mental health", "anxiety", "depression", "therapy", "therapist",
        "burnout", "stress", "panic attack",
    ]),
    TopicProfile("sleep", [
        "sleep", "insomnia", "sleep quality", "mattress", "melatonin",
    ]),

    # Life / career / finance
    TopicProfile("cscareerquestions", [
        "career", "software engineer", "tech career", "interview",
        "resume", "job search", "salary", "tech interview",
        "leetcode", "coding interview",
    ]),
    TopicProfile("careerguidance", [
        "career advice", "career change", "career path", "job advice",
    ]),
    TopicProfile("personalfinance", [
        "finance", "budget", "saving", "debt", "credit card",
        "retirement", "investing", "401k", "ira",
    ]),
    TopicProfile("investing", [
        "investing", "investment", "stock", "etf", "portfolio",
        "dividend", "index fund",
    ]),
    TopicProfile("CryptoCurrency", [
        "crypto", "cryptocurrency", "bitcoin", "ethereum", "defi",
        "blockchain", "token", "nft",
    ]),
    TopicProfile("startups", [
        "startup", "entrepreneur", "founder", "venture capital",
        "mvp", "saas", "side project",
    ]),

    # Education / moving
    TopicProfile("college", [
        "college", "university", "degree", "major", "campus",
        "tuition", "student",
    ]),
    TopicProfile("GradSchool", [
        "grad school", "graduate school", "phd", "masters", "thesis",
    ]),
    TopicProfile("studyAbroad", [
        "study abroad", "exchange student", "international student",
    ]),
    TopicProfile("IWantOut", [
        "moving abroad", "emigrate", "immigration", "expat",
        "relocate", "move to",
    ]),

    # Lifestyle
    TopicProfile("travel", [
        "travel", "traveling", "backpacking", "solo travel", "trip",
        "flight", "hotel", "hostel", "itinerary",
    ]),
    TopicProfile("Cooking", [
        "cooking", "recipe", "meal prep", "kitchen", "baking",
        "chef", "home cooking",
    ]),
    TopicProfile("EatCheapAndHealthy", [
        "cheap food", "budget meal", "healthy eating", "meal budget",
    ]),
    TopicProfile("relationships", [
        "relationship", "dating", "partner", "breakup", "marriage",
    ]),
    TopicProfile("malefashionadvice", [
        "fashion", "outfit", "style", "clothing", "men fashion",
        "what to wear", "wardrobe",
    ]),
    TopicProfile("movies", [
        "movie", "film", "cinema", "best movie", "movie recommendation",
    ]),
    TopicProfile("books", [
        "book", "reading", "novel", "author", "book recommendation",
    ]),
    TopicProfile("gaming", [
        "gaming", "video game", "game", "playstation", "xbox",
        "nintendo", "steam", "pc gaming",
    ]),

    # Music
    TopicProfile("piano", [
        "piano", "keyboard piano", "learn piano", "piano practice",
        "digital piano", "piano keyboard",
    ]),
    TopicProfile("Guitar", [
        "guitar", "acoustic guitar", "electric guitar", "guitar pedal",
    ]),

    # Pets
    TopicProfile("dogs", ["dog", "puppy", "dog breed", "dog training"]),
    TopicProfile("cats", ["cat", "kitten", "cat behavior"]),

    # Cars
    TopicProfile("whatcarshouldIbuy", [
        "car", "vehicle", "suv", "sedan", "used car", "best car",
        "buy car", "car recommendation",
    ]),

    # Housing
    TopicProfile("renting", [
        "apartment", "renting", "lease", "landlord", "rent",
    ]),

    # Photography
    TopicProfile("photography", [
        "photography", "photo", "portrait", "landscape photography",
    ]),
]


# General-purpose subreddits tried when no specific route matches
# and primary sources are down.
_FALLBACK_SUBREDDITS = ["AskReddit", "NoStupidQuestions", "OutOfTheLoop"]


class RedditProvider(Provider):
    """Search Reddit via Pullpush → Arctic Shift → Redlib fallback."""

    name = "reddit"
    supports_time_filter = True

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str | None = None,
        time_range: TimeRange = TimeRange.ALL,
        **kwargs: Any,
    ) -> SearchResults:
        # Auto-route to relevant subreddits if none specified
        subreddits = [subreddit] if subreddit else self._route_subreddits(query)

        all_results: list[OpinionResult] = []
        last_error: str | None = None

        for sub in subreddits[:3]:
            # Try Pullpush first (best for broad search)
            result = await self._pullpush_search(
                query, limit=limit, subreddit=sub, time_range=time_range,
            )
            if result.ok:
                all_results.extend(result.results)
                continue

            # Fall back to Arctic Shift (needs subreddit)
            if sub:
                result = await self._arctic_search(
                    query, limit=limit, subreddit=sub, time_range=time_range,
                )
                if result.ok:
                    all_results.extend(result.results)
                    continue

            last_error = result.error

        # If no subreddit-scoped results, try Pullpush without subreddit
        if not all_results and not subreddit:
            result = await self._pullpush_search(
                query, limit=limit, subreddit=None, time_range=time_range,
            )
            if result.ok:
                all_results = list(result.results)
            else:
                last_error = result.error

        # If still nothing and no routes matched, try Arctic Shift
        # with broad subreddits as a safety net
        if not all_results and not subreddits:
            for fallback_sub in _FALLBACK_SUBREDDITS:
                result = await self._arctic_search(
                    query, limit=limit, subreddit=fallback_sub,
                    time_range=time_range,
                )
                if result.ok:
                    all_results.extend(result.results)
                    break

        # Last resort: try Redlib (works without subreddit scope)
        if not all_results:
            for sub in (subreddits[:2] if subreddits else [""]):
                result = await self._redlib_search(
                    query, limit=limit, subreddit=sub, time_range=time_range,
                )
                if result.ok:
                    all_results.extend(result.results)
                    break
                last_error = result.error

        # Post-filter for relevance to reduce Pullpush noise
        all_results = relevance_filter(all_results, query)

        # Sort by engagement
        all_results.sort(key=lambda r: r.score + r.num_replies, reverse=True)

        if all_results:
            return SearchResults(
                platform=self.name,
                query=query,
                results=all_results[:limit],
                total_found=len(all_results),
                time_range=time_range.value,
            )

        return SearchResults(
            platform=self.name,
            query=query,
            error=last_error or "No results found",
            time_range=time_range.value,
        )

    # ── Pullpush (primary) ──────────────────────────────────────

    async def _pullpush_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str | None = None,
        time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        params: dict[str, Any] = {"q": query, "size": min(limit * 2, 100)}
        if subreddit:
            params["subreddit"] = subreddit

        after, before = time_range.to_timestamps()
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_PULLPUSH_POSTS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=f"Pullpush: {exc}",
                time_range=time_range.value,
            )

        return self._parse_pushshift_response(data, query, time_range)

    # ── Arctic Shift (fallback 1) ───────────────────────────────

    async def _arctic_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str = "",
        time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        params: dict[str, Any] = {
            "query": query,
            "subreddit": subreddit,
            "limit": min(limit * 2, 100),
        }

        after, before = time_range.to_timestamps()
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_ARCTIC_POSTS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SearchResults(
                platform=self.name, query=query, error=f"Arctic Shift: {exc}",
                time_range=time_range.value,
            )

        posts = data.get("data") or []
        results = [self._post_to_result(p) for p in posts]
        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=len(results),
            time_range=time_range.value,
        )

    # ── Redlib (fallback 2) ─────────────────────────────────────

    async def _redlib_search(
        self,
        query: str,
        *,
        limit: int = 10,
        subreddit: str = "",
        time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        if subreddit:
            path = f"/r/{subreddit}/search?q={query}&restrict_sr=on&sort=relevance&t=all"
        else:
            path = f"/search?q={query}&sort=relevance&t=all"

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            for base in _REDLIB_INSTANCES:
                try:
                    resp = await client.get(
                        base + path,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; vox-pop/0.1)"},
                    )
                    if resp.status_code != 200:
                        continue
                    body = resp.text
                    if "anubis" in body.lower() or "checking your browser" in body.lower():
                        continue
                    return self._parse_redlib_html(body, query, time_range)
                except httpx.HTTPError:
                    continue

        return SearchResults(
            platform=self.name,
            query=query,
            error="All Redlib instances failed",
            time_range=time_range.value,
        )

    # ── Shared parsers ──────────────────────────────────────────

    def _parse_pushshift_response(
        self, data: dict[str, Any], query: str, time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        posts = data.get("data") or []
        results = [self._post_to_result(p) for p in posts]
        return SearchResults(
            platform=self.name,
            query=query,
            results=results,
            total_found=len(results),
            time_range=time_range.value,
        )

    @staticmethod
    def _post_to_result(post: dict[str, Any]) -> OpinionResult:
        title = post.get("title", "")
        selftext = post.get("selftext") or ""
        text = f"{title}\n{selftext}".strip() if selftext else title
        permalink = post.get("permalink", "")
        url = _POST_URL.format(permalink=permalink) if permalink else ""
        # Convert Unix timestamp to ISO date
        created_utc = post.get("created_utc", "")
        if isinstance(created_utc, (int, float)) and created_utc > 0:
            from datetime import datetime, timezone
            created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            created_at = str(created_utc)
        return OpinionResult(
            text=strip_html(text),
            platform="reddit",
            url=url,
            author=post.get("author", "[deleted]"),
            score=safe_int(post.get("score")),
            num_replies=safe_int(post.get("num_comments")),
            created_at=created_at,
            metadata={
                "subreddit": post.get("subreddit", ""),
            },
        )

    @staticmethod
    def _parse_redlib_html(
        html_text: str, query: str, time_range: TimeRange = TimeRange.ALL,
    ) -> SearchResults:
        results: list[OpinionResult] = []
        post_blocks = re.findall(
            r'<a\s+class="post_title"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            html_text,
        )
        for href, title in post_blocks:
            results.append(
                OpinionResult(
                    text=strip_html(title),
                    platform="reddit (via Redlib)",
                    url=f"https://www.reddit.com{href}" if href.startswith("/r/") else href,
                    author="",
                    score=0,
                )
            )

        return SearchResults(
            platform="reddit",
            query=query,
            results=results,
            total_found=len(results),
            time_range=time_range.value,
        )

    @staticmethod
    def _route_subreddits(query: str) -> list[str]:
        """Score query against subreddit profiles, return best matches."""
        return score_route(query, SUBREDDIT_PROFILES, min_score=0.5, max_results=3)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    _PULLPUSH_POSTS, params={"q": "test", "size": 1},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
