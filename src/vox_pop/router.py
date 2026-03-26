"""Smart query routing with LLM intelligence and semantic embeddings.

Architecture (tried in order):
  Tier 1 (MCP):   Calling LLM provides routing_hints → parse_routing_hints()
  Tier 2 (LLM):   Cheap LLM call (~$0.0003) → Anthropic, OpenAI, or Ollama (free)
  Tier 3 (Embed):  FastEmbed semantic similarity — local, free, understands meaning
  Tier 4 (Broad):  Search all platforms broadly — no intelligence, just wide net

Tier 3 is the key innovation: a 33MB embedding model that runs locally, needs no
API key, and understands that "contradictory spell behaviour" matches "tabletop RPG
rules, spell interactions" — zero shared keywords needed.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import os
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Disk Cache ─────────────────────────────────────────────

_CACHE_DIR = pathlib.Path.home() / ".cache" / "vox-pop"
_API_CACHE_TTL = 7 * 86400  # 7 days — platforms rarely add/remove boards/sites


def _read_api_cache(name: str) -> dict | None:
    """Read a cached API response if fresh."""
    path = _CACHE_DIR / name
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_ts", 0) < _API_CACHE_TTL:
            return data
    except Exception:
        pass
    return None


def _write_api_cache(name: str, data: dict) -> None:
    """Write an API response to disk cache."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data["_ts"] = time.time()
        (_CACHE_DIR / name).write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.debug("Cache write failed: %s", exc)


# ── Route Decision ─────────────────────────────────────────

@dataclass
class RouteDecision:
    """Structured routing decision for a query."""

    subreddits: list[str] = field(default_factory=list)
    boards: list[str] = field(default_factory=list)       # 4chan
    sites: list[str] = field(default_factory=list)         # Stack Exchange
    communities: list[str] = field(default_factory=list)   # Lemmy
    channels: list[str] = field(default_factory=list)      # Telegram
    forum_ids: list[str] = field(default_factory=list)     # XenForo
    search_query: str = ""
    routed_by: str = ""  # "llm", "semantic", "broad", or "hints"

    def to_kwargs(self) -> dict[str, list[str]]:
        """Convert to provider kwargs (same format as parse_routing_hints)."""
        kwargs: dict[str, list[str]] = {}
        if self.subreddits:
            kwargs["subreddits"] = self.subreddits
        if self.boards:
            kwargs["boards"] = self.boards
        if self.sites:
            kwargs["sites"] = self.sites
        if self.communities:
            kwargs["communities"] = self.communities
        if self.channels:
            kwargs["channels"] = self.channels
        if self.forum_ids:
            kwargs["forum_ids"] = self.forum_ids
        return kwargs

    @property
    def has_routes(self) -> bool:
        return bool(
            self.subreddits or self.boards or self.sites
            or self.communities or self.channels or self.forum_ids
        )

    def summary(self) -> str:
        """Human-readable summary for CLI output."""
        parts: list[str] = []
        if self.subreddits:
            parts.append(f"reddit: {', '.join(f'r/{s}' for s in self.subreddits)}")
        if self.boards:
            parts.append(f"4chan: {', '.join(f'/{b}/' for b in self.boards)}")
        if self.sites:
            parts.append(f"SE: {', '.join(self.sites[:4])}")
        if self.communities:
            parts.append(f"lemmy: {', '.join(self.communities)}")
        if self.channels:
            parts.append(f"telegram: {', '.join(self.channels)}")
        if self.forum_ids:
            parts.append(f"forums: {', '.join(self.forum_ids)}")
        label = f"[{self.routed_by}]" if self.routed_by else ""
        body = " | ".join(parts) if parts else "broad search (all platforms)"
        return f"{label} {body}".strip()


# ── Public API ─────────────────────────────────────────────

async def route_query(query: str) -> RouteDecision:
    """Route a query using the best available method.

    Tier 2: LLM (if API key set) → Tier 3: Semantic embeddings → Tier 4: Broad.
    """
    # Tier 2: LLM routing
    decision = await _llm_route(query)
    if decision is not None and decision.has_routes:
        decision.routed_by = "llm"
        return decision

    # Tier 3: Semantic embedding routing (local, free)
    decision = await _semantic_route(query)
    if decision is not None and decision.has_routes:
        decision.routed_by = "semantic"
        return decision

    # Tier 4: Broad defaults
    return _broad_defaults()


# ── Tier 2: LLM Routing ───────────────────────────────────

_LLM_SYSTEM = """\
You route user queries to the most relevant online communities for finding \
real human opinions and discussions. The query can be anything: a single word, \
a paragraph, an essay, a D&D rules question, a medical symptom, slang, etc.

Return ONLY valid JSON. No explanation.

Platforms you can route to:
- reddit: 2-4 specific subreddit names (be precise — r/SkincareAddiction not r/skincare, \
r/MechanicalKeyboards not r/keyboards). Think about which actual subreddits exist.
- 4chan: 1-2 board codes. Common boards: g(technology), fit(fitness/health/looks), \
sci(science/math), biz(finance/crypto), ck(cooking/food), trv(travel), fa(fashion), \
adv(advice/life), a(anime/manga), v(gaming), mu(music), tv(film/tv), diy(crafts), \
o(auto/cars), p(photography), pol(politics), int(international/countries), \
lit(literature/books), his(history), tg(tabletop games/rpg/dnd), k(weapons), \
r9k(feelings/lonely), wsg(worksafe gif)
- stackexchange: 1-3 sites. Common: stackoverflow, superuser, math, physics, \
cooking, travel, money, fitness, workplace, security, gaming, diy, english, \
photo, health, chemistry, biology, academia, electronics, music, law, askubuntu, \
rpg, worldbuilding, philosophy, history, economics, hardwarerecs, softwarerecs, \
gardening, pets, scifi, boardgames, psychology
- lemmy: 1-2 communities (format: name@instance). Common instances: lemmy.ml, \
lemmy.world, programming.dev, beehaw.org
- telegram: Only for news/crypto/AI. Channels: OpenAI, anthropic_ai, techcrunch, \
bitcoin, ethereum, bbcnews
- forums: headfi (headphones/audio gear), anandtech (PC hardware/benchmarks). \
Only if topic is directly about audio gear or PC hardware.

Output:
{"subreddits":[],"boards":[],"sites":[],"communities":[],"channels":[],\
"forum_ids":[],"search_query":"concise search-optimized version of the query"}

Rules:
- Only include platforms where the topic would actually be discussed
- search_query: rewrite the query as a concise search string (strip filler, keep core topic)
- For very niche queries, focus on 1-2 highly relevant communities
- For broad queries, include diverse platforms
- Empty arrays for platforms that aren't relevant"""


async def _llm_route(query: str) -> RouteDecision | None:
    """Try LLM routing. Returns None if no LLM available."""
    for attempt in [_try_anthropic, _try_openai, _try_ollama]:
        result = await attempt(query)
        if result is not None:
            return result
    return None


async def _try_anthropic(query: str) -> RouteDecision | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "system": _LLM_SYSTEM,
                    "messages": [{"role": "user", "content": query[:4000]}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return _parse_llm_json(data["content"][0]["text"])
    except Exception as exc:
        logger.debug("Anthropic routing failed: %s", exc)
        return None


async def _try_openai(query: str) -> RouteDecision | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 300,
                    "messages": [
                        {"role": "system", "content": _LLM_SYSTEM},
                        {"role": "user", "content": query[:4000]},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return _parse_llm_json(data["choices"][0]["message"]["content"])
    except Exception as exc:
        logger.debug("OpenAI routing failed: %s", exc)
        return None


async def _try_ollama(query: str) -> RouteDecision | None:
    """Try local Ollama for free LLM routing."""
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not os.environ.get("OLLAMA_HOST"):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.get(f"{host}/api/tags")
        except Exception:
            return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{host}/api/chat",
                json={
                    "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": _LLM_SYSTEM},
                        {"role": "user", "content": query[:4000]},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return _parse_llm_json(data["message"]["content"])
    except Exception as exc:
        logger.debug("Ollama routing failed: %s", exc)
        return None


def _parse_llm_json(text: str) -> RouteDecision:
    """Parse LLM JSON response into a RouteDecision."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    data = json.loads(text)
    return RouteDecision(
        subreddits=data.get("subreddits") or [],
        boards=data.get("boards") or [],
        sites=data.get("sites") or [],
        communities=data.get("communities") or [],
        channels=data.get("channels") or [],
        forum_ids=data.get("forum_ids") or [],
        search_query=data.get("search_query", ""),
    )


# ── Tier 3: Semantic Embedding Routing ─────────────────────

@dataclass(frozen=True)
class Destination:
    """A routable destination with a natural-language description."""

    platform: str   # "reddit", "4chan", "stackexchange", "lemmy", "telegram", "forums"
    id: str         # subreddit name, board code, SE site, etc.
    description: str  # Rich natural-language description for embedding


# Comprehensive destination catalog.  Descriptions are NATURAL LANGUAGE — the
# embedding model understands semantics, not keywords.  Adding a new destination
# is one line: Destination(platform, id, "what people discuss there").
DESTINATIONS: list[Destination] = [
    # ── Reddit ──────────────────────────────────────────────
    Destination("reddit", "AskReddit", "General questions, opinions, and stories about anything in life"),
    Destination("reddit", "programming", "Software development, programming languages, coding practices, developer tools"),
    Destination("reddit", "Python", "Python programming language, libraries, frameworks, best practices"),
    Destination("reddit", "javascript", "JavaScript, TypeScript, Node.js, React, web development frameworks"),
    Destination("reddit", "rust", "Rust programming language, systems programming, memory safety, performance"),
    Destination("reddit", "golang", "Go programming language, backend development, concurrency, microservices"),
    Destination("reddit", "MachineLearning", "Machine learning research, deep learning, neural networks, AI papers and models"),
    Destination("reddit", "artificial", "AI news, artificial intelligence applications, AGI discussion, AI ethics"),
    Destination("reddit", "buildapc", "Building custom PCs, hardware selection, CPU GPU comparisons, benchmarks"),
    Destination("reddit", "hardware", "Computer hardware news, reviews, benchmarks, CPU GPU motherboard discussions"),
    Destination("reddit", "MechanicalKeyboards", "Mechanical keyboards, custom builds, switches, keycaps, typing experience"),
    Destination("reddit", "headphones", "Headphones, earbuds, IEMs, DACs, amplifiers, audiophile gear, sound quality"),
    Destination("reddit", "audiophile", "High fidelity audio equipment, speakers, turntables, room acoustics"),
    Destination("reddit", "android", "Android phones, tablets, apps, custom ROMs, mobile technology"),
    Destination("reddit", "apple", "Apple products, iPhone, Mac, iPad, iOS, macOS, Apple ecosystem"),
    Destination("reddit", "linux", "Linux distributions, command line, system administration, open source software"),
    Destination("reddit", "selfhosted", "Self-hosting services, home servers, privacy, Docker containers, networking"),
    Destination("reddit", "privacy", "Digital privacy, data protection, encryption, surveillance, VPN services"),
    Destination("reddit", "fitness", "Exercise routines, gym workouts, strength training, bodybuilding, cardio"),
    Destination("reddit", "loseit", "Weight loss journeys, calorie counting, diet strategies, body transformation"),
    Destination("reddit", "nutrition", "Nutrition science, dietary advice, meal planning, supplements, macronutrients"),
    Destination("reddit", "SkincareAddiction", "Skincare routines, acne treatment, anti-aging, product reviews, dermatology"),
    Destination("reddit", "mewing", "Facial structure, jaw exercises, mewing technique, facial aesthetics, looksmaxing"),
    Destination("reddit", "personalfinance", "Personal finance, budgeting, saving, debt management, financial planning"),
    Destination("reddit", "CryptoCurrency", "Cryptocurrency trading, Bitcoin, Ethereum, DeFi, blockchain technology"),
    Destination("reddit", "investing", "Stock market investing, portfolio management, ETFs, value investing"),
    Destination("reddit", "cscareerquestions", "Software engineering career advice, job interviews, tech salary negotiation"),
    Destination("reddit", "careerguidance", "Career advice, job transitions, resume help, workplace challenges"),
    Destination("reddit", "Cooking", "Cooking recipes, meal preparation, kitchen techniques, food discussions"),
    Destination("reddit", "MealPrepSunday", "Meal prep ideas, batch cooking, weekly food planning, budget meals"),
    Destination("reddit", "travel", "Travel destinations, trip planning, budget travel, backpacking experiences"),
    Destination("reddit", "solotravel", "Solo traveling, safety tips, hostel life, meeting people abroad"),
    Destination("reddit", "expats", "Living abroad, expatriate life, immigration, culture shock, visa processes"),
    Destination("reddit", "gaming", "Video games, game recommendations, gaming news, game reviews and discussions"),
    Destination("reddit", "pcgaming", "PC gaming, performance optimization, game settings, PC game recommendations"),
    Destination("reddit", "DnD", "Dungeons and Dragons, tabletop RPG, character builds, campaign stories, spell rules"),
    Destination("reddit", "dndnext", "D&D 5th edition rules discussions, homebrew, spell interactions, game mechanics"),
    Destination("reddit", "boardgames", "Board games, card games, tabletop game reviews and recommendations"),
    Destination("reddit", "relationships", "Relationship advice, dating, marriage, breakups, interpersonal issues"),
    Destination("reddit", "AskMen", "Men's perspectives on relationships, career, health, lifestyle, and culture"),
    Destination("reddit", "AskWomen", "Women's perspectives on relationships, career, health, lifestyle, and culture"),
    Destination("reddit", "DIY", "Do it yourself projects, home improvement, woodworking, crafts"),
    Destination("reddit", "HomeImprovement", "Home renovation, plumbing, electrical work, painting, remodeling"),
    Destination("reddit", "photography", "Photography techniques, camera gear, composition, editing, photo critique"),
    Destination("reddit", "movies", "Film discussion, movie reviews, cinema analysis, director filmographies"),
    Destination("reddit", "books", "Book recommendations, reading discussion, literary analysis, book reviews"),
    Destination("reddit", "music", "Music discovery, album reviews, concert experiences, genre discussions"),
    Destination("reddit", "Guitar", "Guitar playing, gear reviews, pedals, amplifiers, learning guitar"),
    Destination("reddit", "piano", "Piano playing, keyboard instruments, music theory, practice techniques"),
    Destination("reddit", "cars", "Automobiles, car buying advice, maintenance, racing, car culture"),
    Destination("reddit", "gardening", "Gardening tips, plant care, landscaping, growing vegetables and flowers"),
    Destination("reddit", "legaladvice", "Legal questions, rights, court procedures, landlord-tenant disputes"),
    Destination("reddit", "dogs", "Dog ownership, breeds, training, health, behavior, pet care"),

    # ── 4chan ───────────────────────────────────────────────
    Destination("4chan", "g", "Technology, programming, software, hardware, phones, laptops, Linux, coding"),
    Destination("4chan", "fit", "Fitness, weightlifting, bodybuilding, diet, skincare, facial aesthetics, mewing"),
    Destination("4chan", "sci", "Science and mathematics, physics, chemistry, biology, proofs, research"),
    Destination("4chan", "biz", "Business, finance, cryptocurrency, Bitcoin, Ethereum, trading, stock market"),
    Destination("4chan", "ck", "Food and cooking, recipes, restaurants, cuisine, baking, kitchen equipment"),
    Destination("4chan", "trv", "Travel, backpacking, destinations, budget travel, living abroad, expat life"),
    Destination("4chan", "fa", "Fashion and style, clothing, sneakers, streetwear, outfit advice"),
    Destination("4chan", "adv", "Life advice, relationships, dating, career decisions, personal problems"),
    Destination("4chan", "a", "Anime and manga discussion, seasonal anime, recommendations, otaku culture"),
    Destination("4chan", "v", "Video games, game recommendations, gaming news, game mechanics, strategy"),
    Destination("4chan", "mu", "Music, albums, instruments, guitar, piano, concerts, playlists, genres"),
    Destination("4chan", "tv", "Film, movies, television shows, series, directors, actors, streaming"),
    Destination("4chan", "diy", "Do it yourself projects, woodworking, crafts, repairs, building things"),
    Destination("4chan", "o", "Automobiles, cars, motorcycles, driving, engines, vehicle maintenance"),
    Destination("4chan", "p", "Photography, cameras, lenses, exposure, composition, photo editing"),
    Destination("4chan", "pol", "Politics, political discussion, elections, government policy, current events"),
    Destination("4chan", "int", "International culture, living in different countries, cities, languages, expat life"),
    Destination("4chan", "lit", "Literature, books, writing, poetry, philosophy, reading recommendations"),
    Destination("4chan", "his", "History, historical events, civilizations, wars, ancient and modern history"),
    Destination("4chan", "tg", "Tabletop games, Dungeons and Dragons, Pathfinder, RPG rules, spell interactions, wargaming"),
    Destination("4chan", "r9k", "Feelings, loneliness, social anxiety, personal struggles, life stories"),
    Destination("4chan", "k", "Weapons, firearms, knives, military equipment, self-defense"),

    # ── Stack Exchange ─────────────────────────────────────
    Destination("stackexchange", "stackoverflow", "Programming questions, debugging code, algorithms, web development, databases"),
    Destination("stackexchange", "superuser", "Computer hardware and software troubleshooting, Windows, Mac, peripherals"),
    Destination("stackexchange", "serverfault", "System administration, networking, servers, DevOps, deployment"),
    Destination("stackexchange", "unix", "Linux and Unix command line, shell scripting, system configuration"),
    Destination("stackexchange", "askubuntu", "Ubuntu Linux, package management, desktop environment, drivers"),
    Destination("stackexchange", "math", "Mathematics, algebra, calculus, statistics, proofs, polynomials, linear algebra"),
    Destination("stackexchange", "physics", "Physics questions, quantum mechanics, relativity, thermodynamics"),
    Destination("stackexchange", "chemistry", "Chemistry, organic reactions, biochemistry, molecular structure"),
    Destination("stackexchange", "biology", "Biology, genetics, evolution, ecology, cell biology"),
    Destination("stackexchange", "cooking", "Cooking techniques, recipes, food science, baking, kitchen equipment"),
    Destination("stackexchange", "travel", "Travel planning, flights, visas, passports, destinations, customs"),
    Destination("stackexchange", "money", "Personal finance, investing, taxes, budgeting, retirement planning"),
    Destination("stackexchange", "fitness", "Exercise science, workout routines, nutrition, weight training"),
    Destination("stackexchange", "workplace", "Career advice, office etiquette, job hunting, management, salary"),
    Destination("stackexchange", "security", "Information security, cryptography, vulnerabilities, ethical hacking"),
    Destination("stackexchange", "gaming", "Video game mechanics, achievements, walkthroughs, game strategy"),
    Destination("stackexchange", "diy", "Home improvement projects, plumbing, electrical, woodworking"),
    Destination("stackexchange", "english", "English language, grammar, vocabulary, word usage, etymology"),
    Destination("stackexchange", "photo", "Photography, camera settings, lighting, composition, post-processing"),
    Destination("stackexchange", "electronics", "Electronic circuits, Arduino, microcontrollers, embedded systems"),
    Destination("stackexchange", "music", "Music theory, instruments, practice, composition, performance"),
    Destination("stackexchange", "academia", "Academic research, university life, publishing, thesis writing"),
    Destination("stackexchange", "law", "Legal questions, rights, regulations, court procedures"),
    Destination("stackexchange", "rpg", "Tabletop RPG rules, Dungeons and Dragons, Pathfinder, spell effects, game mechanics"),
    Destination("stackexchange", "hardwarerecs", "Hardware recommendations, laptops, keyboards, monitors, peripherals"),
    Destination("stackexchange", "softwarerecs", "Software tool recommendations, app alternatives, productivity tools"),
    Destination("stackexchange", "worldbuilding", "Fictional worldbuilding, maps, cultures, alternate histories"),
    Destination("stackexchange", "philosophy", "Philosophy, ethics, logic, epistemology, metaphysics"),
    Destination("stackexchange", "history", "History questions, ancient and modern civilizations, historical events"),
    Destination("stackexchange", "economics", "Economics, markets, trade policy, macro and microeconomics"),
    Destination("stackexchange", "health", "Health questions, symptoms, disease, medical advice, wellness"),
    Destination("stackexchange", "psychology", "Psychology, cognitive science, mental health, therapy"),

    # ── Lemmy ──────────────────────────────────────────────
    Destination("lemmy", "asklemmy@lemmy.ml", "General questions and discussions about anything"),
    Destination("lemmy", "linux@lemmy.ml", "Linux operating system, distributions, open source software"),
    Destination("lemmy", "technology@lemmy.world", "Technology news, gadgets, software, digital trends"),
    Destination("lemmy", "programming@programming.dev", "Software development, coding, programming languages, tools"),
    Destination("lemmy", "selfhosted@lemmy.world", "Self-hosting services, home lab, Docker, privacy-focused tools"),
    Destination("lemmy", "privacy@lemmy.ml", "Digital privacy, surveillance, encryption, data protection"),
    Destination("lemmy", "gaming@lemmy.world", "Video games, game recommendations, gaming news and discussion"),
    Destination("lemmy", "fitness@lemmy.world", "Exercise, gym, nutrition, weight loss, health and fitness"),
    Destination("lemmy", "science@lemmy.world", "Science news, research, discoveries, academic discussion"),

    # ── Telegram ───────────────────────────────────────────
    Destination("telegram", "OpenAI", "AI news, OpenAI announcements, GPT, ChatGPT, machine learning"),
    Destination("telegram", "anthropic_ai", "Anthropic news, Claude AI, AI safety, language models"),
    Destination("telegram", "techcrunch", "Tech industry news, startups, funding, product launches"),
    Destination("telegram", "bitcoin", "Bitcoin news, cryptocurrency market, blockchain technology"),
    Destination("telegram", "ethereum", "Ethereum network, DeFi, smart contracts, web3 development"),
    Destination("telegram", "bbcnews", "World news, breaking news, current events, international affairs"),

    # ── Forums (XenForo) ───────────────────────────────────
    Destination("forums", "headfi", "Headphones, earphones, IEMs, DACs, amplifiers, audiophile equipment reviews"),
    Destination("forums", "anandtech", "PC hardware benchmarks, CPU GPU reviews, motherboards, storage, tech analysis"),
]


# Platform → RouteDecision field name mapping.
_PLATFORM_TO_FIELD: dict[str, str] = {
    "reddit": "subreddits",
    "4chan": "boards",
    "stackexchange": "sites",
    "lemmy": "communities",
    "telegram": "channels",
    "forums": "forum_ids",
}


# ── Dynamic Catalog Fetching ──────────────────────────────

async def _fetch_4chan_destinations() -> list[Destination]:
    """Fetch all 4chan boards with descriptions from boards.json.

    Returns ~77 boards.  Cached to disk for 7 days.
    Static DESTINATIONS entries act as fallback if this fails.
    """
    cached = _read_api_cache("4chan_boards.json")
    if cached and "boards" in cached:
        return [
            Destination("4chan", b["board"], b["desc"])
            for b in cached["boards"]
        ]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://a.4cdn.org/boards.json")
            resp.raise_for_status()
            data = resp.json()

        boards = []
        for b in data.get("boards", []):
            code = b.get("board", "")
            # meta_description is richer than title
            desc = b.get("meta_description", "") or b.get("title", "")
            desc = html_mod.unescape(desc).strip()
            if code and desc:
                boards.append({"board": code, "desc": desc})

        _write_api_cache("4chan_boards.json", {"boards": boards})
        return [Destination("4chan", b["board"], b["desc"]) for b in boards]
    except Exception as exc:
        logger.debug("Failed to fetch 4chan boards: %s", exc)
        return []


async def _fetch_se_destinations() -> list[Destination]:
    """Fetch all Stack Exchange sites with audience descriptions.

    The /sites API is paginated (~180 sites across 3 pages).
    Cached to disk for 7 days.
    """
    cached = _read_api_cache("se_sites.json")
    if cached and "sites" in cached:
        return [
            Destination("stackexchange", s["id"], s["desc"])
            for s in cached["sites"]
        ]

    try:
        sites: list[dict[str, str]] = []
        page = 1
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                resp = await client.get(
                    "https://api.stackexchange.com/2.3/sites",
                    params={"pagesize": 100, "page": page},
                )
                resp.raise_for_status()
                data = resp.json()
                for s in data.get("items", []):
                    api_param = s.get("api_site_parameter", "")
                    # Skip meta sites and localized SO variants
                    if ".meta" in api_param or "meta." in api_param:
                        continue
                    # Skip localized Stack Overflow (pt, ja, ru, es, etc.)
                    # They match on language, not topic, creating noise
                    if api_param != "stackoverflow" and "stackoverflow" in api_param:
                        continue
                    audience = s.get("audience", "") or s.get("name", "")
                    if api_param and audience:
                        sites.append({"id": api_param, "desc": audience})
                if not data.get("has_more", False):
                    break
                page += 1
                if page > 5:  # Safety cap
                    break

        _write_api_cache("se_sites.json", {"sites": sites})
        return [Destination("stackexchange", s["id"], s["desc"]) for s in sites]
    except Exception as exc:
        logger.debug("Failed to fetch SE sites: %s", exc)
        return []


# ── Embedding Disk Cache (JSON, no pickle) ────────────────

_EMBED_CACHE_DIR = _CACHE_DIR / "embeddings"


def _embedding_cache_key(descriptions: list[str]) -> str:
    """Deterministic hash of all destination descriptions."""
    content = "\n".join(descriptions)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _load_embedding_cache(key: str) -> Any | None:
    """Load cached embeddings from JSON. Returns numpy array or None."""
    path = _EMBED_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        import numpy as np
        data = json.loads(path.read_text(encoding="utf-8"))
        return np.array(data, dtype=np.float32)
    except Exception:
        return None


def _save_embedding_cache(key: str, embeddings: Any) -> None:
    """Save embeddings to JSON (numpy array → list)."""
    try:
        _EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = embeddings.tolist()  # numpy array → nested Python lists
        (_EMBED_CACHE_DIR / f"{key}.json").write_text(
            json.dumps(data), encoding="utf-8",
        )
    except Exception as exc:
        logger.debug("Embedding cache write failed: %s", exc)


class SemanticRouter:
    """Routes queries using embedding similarity against destination descriptions.

    Uses FastEmbed (BAAI/bge-small-en-v1.5, ~33MB) to encode both queries and
    destination descriptions into a shared vector space.  Cosine similarity
    finds the best matches — this understands meaning, not keywords.

    On first run, fetches dynamic catalogs from 4chan boards.json (~77 boards)
    and SE /sites API (~180 sites), merges with static DESTINATIONS, embeds
    everything, and caches to disk.  Warm start: ~1s.  Cold start: ~5s.
    """

    _instance: SemanticRouter | None = None

    def __init__(
        self,
        destinations: list[Destination],
        dest_embeddings: Any,  # numpy ndarray
        np_mod: Any,
        model: Any,
    ) -> None:
        self._destinations = destinations
        self._dest_embeddings = dest_embeddings
        self._np = np_mod
        self._model = model

    @classmethod
    async def create(cls) -> SemanticRouter:
        """Async factory: build catalog, fetch dynamic sources, embed."""
        from fastembed import TextEmbedding
        import numpy as np

        model = TextEmbedding("BAAI/bge-small-en-v1.5")

        # Merge static catalog with dynamic sources
        # Static entries have richer, embedding-optimized descriptions so
        # they take priority.  Dynamic entries fill in the long tail.
        seen: set[tuple[str, str]] = set()
        all_dests: list[Destination] = []

        # Fetch dynamic catalogs (these expand coverage dramatically)
        dynamic_4chan = await _fetch_4chan_destinations()
        dynamic_se = await _fetch_se_destinations()

        # Static first — hand-written descriptions are more specific
        for d in DESTINATIONS:
            key = (d.platform, d.id)
            if key not in seen:
                seen.add(key)
                all_dests.append(d)

        # Dynamic entries fill the long tail (niche boards/sites)
        for d in dynamic_4chan + dynamic_se:
            key = (d.platform, d.id)
            if key not in seen:
                seen.add(key)
                all_dests.append(d)

        logger.debug(
            "Semantic catalog: %d destinations (%d dynamic 4chan, %d dynamic SE, %d static)",
            len(all_dests), len(dynamic_4chan), len(dynamic_se), len(DESTINATIONS),
        )

        # Compute or load cached embeddings
        descriptions = [d.description for d in all_dests]
        cache_key = _embedding_cache_key(descriptions)
        dest_embeddings = _load_embedding_cache(cache_key)

        if dest_embeddings is None or dest_embeddings.shape[0] != len(descriptions):
            dest_embeddings = np.array(list(model.embed(descriptions)))
            _save_embedding_cache(cache_key, dest_embeddings)

        return cls(all_dests, dest_embeddings, np, model)

    # Per-platform limits to avoid flooding one platform with noise.
    _PLATFORM_CAPS: dict[str, int] = {
        "reddit": 4,
        "4chan": 2,
        "stackexchange": 3,
        "lemmy": 2,
        "telegram": 2,
        "forums": 2,
    }

    def route(
        self,
        query: str,
        *,
        top_k: int = 12,
        threshold: float = 0.55,
    ) -> RouteDecision:
        """Find the most semantically similar destinations for a query."""
        np = self._np
        q_emb = np.array(list(self._model.embed([query])))[0]

        # Cosine similarity (embeddings are L2-normalized by FastEmbed)
        similarities = self._dest_embeddings @ q_emb

        # Get top-k indices above threshold
        top_indices = np.argsort(similarities)[::-1][:top_k]

        decision = RouteDecision()
        platform_counts: dict[str, int] = {}
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim < threshold:
                break
            dest = self._destinations[idx]
            field_name = _PLATFORM_TO_FIELD.get(dest.platform)
            if not field_name:
                continue

            # Enforce per-platform cap
            count = platform_counts.get(dest.platform, 0)
            cap = self._PLATFORM_CAPS.get(dest.platform, 3)
            if count >= cap:
                continue

            getattr(decision, field_name).append(dest.id)
            platform_counts[dest.platform] = count + 1

        return decision

    @classmethod
    async def get_instance(cls) -> SemanticRouter:
        """Get or create the singleton SemanticRouter (async)."""
        if cls._instance is None:
            cls._instance = await cls.create()
        return cls._instance


async def _semantic_route(query: str) -> RouteDecision | None:
    """Try semantic embedding routing. Returns None if fastembed not available."""
    try:
        router = await SemanticRouter.get_instance()
        return router.route(query)
    except ImportError:
        logger.debug("fastembed not installed — skipping semantic routing")
        return None
    except Exception as exc:
        logger.debug("Semantic routing failed: %s", exc)
        return None


# ── Tier 4: Broad Defaults ────────────────────────────────

_BROAD_BOARDS = ["g", "adv", "fit", "biz", "sci", "v", "int", "pol"]
_BROAD_SE_SITES = [
    "stackoverflow", "superuser", "math", "cooking",
    "fitness", "money", "diy", "travel", "workplace",
]


def _broad_defaults() -> RouteDecision:
    """Cast a wide net — search popular destinations on every platform.

    No intelligence. Platforms with server-side search (Reddit, HN, Lobsters,
    LessWrong, Lemmy) don't need routing — their APIs handle relevance.
    Only 4chan (catalog-based) and SE (site-scoped) need explicit destinations.
    """
    return RouteDecision(
        boards=_BROAD_BOARDS,
        sites=_BROAD_SE_SITES,
        routed_by="broad",
    )
