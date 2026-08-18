"""
The keyword engine — OPTIONAL, and Search-Console-first when it's on.

This is the dashboard's implementation of the `keyword-researcher` skill, and it
follows that skill's priority order exactly:

  1. **Search Console query data (free, first-party).** The queries your pages
     already get impressions for. Three gold seams come out of it: terms you're
     already winning, **striking-distance** terms (average position ~5-20 with
     real impressions — one page already ranks, it just needs a push), and
     impression-rich queries whose landing page is weak.
  2. **Google autocomplete (free).** Real phrasings and questions people type.
     Loaded from the skill's own `assets/keyword_adapter.py`, the same way
     `core/images.py` loads the image adapter — so when the user wires a real
     provider there, both paths pick it up with no second edit.
  3. **A paid keyword API (optional, pluggable).** `get_metrics()` in that same
     adapter. Dummy by default, and dummy returns *no numbers* rather than fake
     ones.

The honest rule, from CLAUDE.md: **never fabricate a search volume.** A keyword
with no GSC impressions and no paid-API figure is marked `unvalidated` and says
so everywhere it appears. Ranking is done on signals we can actually verify —
real impressions, a real average position, real autocomplete presence.

The whole branch is switchable: `KEYWORD_ENGINE=off` in Settings and every
caller degrades to "no keyword data", which is a supported state, not an error.
"""

import importlib.util
import math
import re
from dataclasses import dataclass, field

from . import config, gsc

ADAPTER_PATH = (config.ROOT / ".claude" / "skills" / "keyword-researcher"
                / "assets" / "keyword_adapter.py")

DUMMY = "dummy"
_adapter = None                       # cached module, loaded once per process

# Bands — what a keyword is *for*, in plain language.
WINNING = "Already winning"
STRIKING = "Striking distance"
DEEP = "Demand, ranking deep"
QUIET = "Impressions, no traction"
UNVALIDATED = "Unvalidated"

# Striking distance: high enough that Google already likes the page, low enough
# that page one is realistically reachable.
STRIKING_MIN = 4.0
STRIKING_MAX = 20.0
MIN_IMPRESSIONS = 10

INFORMATIONAL = "informational"
COMMERCIAL = "commercial"
NAVIGATIONAL = "navigational"

_COMMERCIAL_WORDS = ("best", "top", "vs", "versus", "review", "reviews", "alternative",
                     "alternatives", "cheapest", "cheap", "price", "pricing", "buy",
                     "compare", "comparison", "software", "tool", "tools", "app")
_INFORMATIONAL_WORDS = ("how", "what", "why", "when", "where", "which", "guide",
                        "tutorial", "example", "examples", "meaning", "definition",
                        "difference", "explained", "tips")

_STOPWORDS = {"the", "and", "for", "with", "that", "this", "your", "you", "from",
              "have", "how", "what", "are", "our", "can", "does", "into", "online",
              "free", "best", "using", "use"}


# ── Dataclasses ────────────────────────────────────────────────────────────
@dataclass
class Keyword:
    """
    One keyword with only the numbers we can actually stand behind.

    `volume` and `difficulty` stay None unless a paid provider returned them.
    `unvalidated` is True when nothing measured this term at all — it's a guess,
    and it is labelled as one wherever it's shown.
    """
    keyword: str
    source: str = "gsc"                # gsc | autocomplete | api | competitor | seed
    intent: str = INFORMATIONAL
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0
    page: str = ""                     # the URL of yours that ranks for it, if known
    volume: int = None                 # paid API only. None means "we don't know".
    difficulty: int = None             # paid API only.
    band: str = UNVALIDATED
    reason: str = ""
    score: float = 0.0

    @property
    def validated(self) -> bool:
        return bool(self.impressions) or self.volume is not None

    @property
    def unvalidated(self) -> bool:
        return not self.validated

    @property
    def volume_label(self) -> str:
        """What to print in a table cell. Never a made-up number."""
        return f"{self.volume:,}" if self.volume is not None else "unvalidated"


@dataclass
class Brief:
    """The keyword brief the writer and the backlink targeter both read."""
    topic: str
    primary: Keyword = None
    secondary: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    target_page: str = ""              # an existing URL to strengthen, or "" for a new post
    notes: str = ""
    sources_used: list = field(default_factory=list)
    ok: bool = True
    detail: str = ""

    @property
    def cluster(self) -> list:
        return ([self.primary] if self.primary else []) + list(self.secondary)


# ── Switches and status ────────────────────────────────────────────────────
def enabled() -> bool:
    """
    Is the keyword branch on? It is by default — Search Console query data is
    free and needs no extra key — but everything downstream checks this first,
    so turning it off is a supported state rather than a broken one.
    """
    return config.get_bool("KEYWORD_ENGINE", True)


def provider() -> str:
    """The paid keyword provider selected in Settings ('dummy' by default)."""
    return config.get("KEYWORD_API_PROVIDER", DUMMY).strip().lower() or DUMMY


def live() -> bool:
    """True when a real paid keyword API is configured."""
    return provider() != DUMMY and config.is_set("KEYWORD_API_KEY")


def status() -> str:
    """One plain-language line for the UI."""
    if not enabled():
        return ("The keyword engine is switched off. Turn it on in Settings → Content "
                "tools; it needs no paid key — Search Console query data is free.")
    if live():
        return (f"Search Console first, then Google autocomplete, then {provider()} "
                "for volume and difficulty.")
    return ("Search Console first, then Google autocomplete. No paid keyword API is "
            "configured, so no keyword shows a search volume — a term with no "
            "impressions behind it is labelled unvalidated rather than given a number.")


# ── The skill's adapter (autocomplete + the paid slot) ─────────────────────
def _load_adapter():
    """Import the keyword-researcher skill's adapter by path. None if missing."""
    global _adapter
    if _adapter is not None:
        return _adapter
    if not ADAPTER_PATH.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("keyword_adapter", ADAPTER_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _adapter = module
        return _adapter
    except Exception:
        return None


def _sync(module) -> None:
    """Point the adapter at whatever Settings holds right now."""
    module.PROVIDER = provider()
    module.API_KEY = config.get("KEYWORD_API_KEY", "REPLACE_ME_LATER")


def autocomplete(seed: str, limit: int = 25) -> dict:
    """
    Free Google Suggest expansion through the skill's adapter.
    Returns {'ok', 'suggestions', 'detail'} and never raises.
    """
    seed = (seed or "").strip()
    if not seed:
        return {"ok": False, "suggestions": [], "detail": "No seed phrase given."}

    module = _load_adapter()
    if module is None:
        return {"ok": False, "suggestions": [],
                "detail": "The keyword adapter file is missing from "
                          ".claude/skills/keyword-researcher/assets/."}
    try:
        _sync(module)
        found = [s.strip() for s in module.autocomplete_suggestions(seed) if s.strip()]
    except Exception as e:
        return {"ok": False, "suggestions": [],
                "detail": f"Google autocomplete couldn't be reached: {e}"}

    found = [s for s in dict.fromkeys(found) if s.lower() != seed.lower()][:limit]
    if not found:
        return {"ok": False, "suggestions": [],
                "detail": "Autocomplete returned nothing for that phrase. It's an "
                          "unofficial endpoint, so it can be blocked or rate-limited."}
    return {"ok": True, "suggestions": found,
            "detail": f"{len(found)} real phrasings from Google autocomplete."}


def metrics(keywords: list) -> dict:
    """
    Volume + difficulty from the pluggable paid provider, keyed by keyword.
    Dummy provider → an empty map, which is how "we don't know" is represented.
    Never invents a number.
    """
    words = [k for k in (keywords or []) if k]
    if not words or not live():
        return {}
    module = _load_adapter()
    if module is None:
        return {}
    try:
        _sync(module)
        rows = module.get_metrics(words)
    except Exception:
        return {}
    out = {}
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("keyword"):
            continue
        if row.get("volume") is None and row.get("difficulty") is None:
            continue                    # the dummy shape — no numbers, so nothing to store
        out[row["keyword"].lower()] = {"volume": row.get("volume"),
                                       "difficulty": row.get("difficulty")}
    return out


# ── Small helpers ──────────────────────────────────────────────────────────
def terms(text: str) -> set:
    """The meaningful words in a phrase, used for matching topics to queries."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def overlap(a: str, b: str) -> float:
    """0-1 similarity between two phrases, on shared meaningful words."""
    ta, tb = terms(a), terms(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def intent_of(keyword: str, brand_terms: set = None) -> str:
    """A plain heuristic — informational, commercial or navigational."""
    words = set(re.findall(r"[a-z0-9]+", (keyword or "").lower()))
    if brand_terms and (words & brand_terms):
        return NAVIGATIONAL
    if words & set(_COMMERCIAL_WORDS):
        return COMMERCIAL
    if words & set(_INFORMATIONAL_WORDS) or (keyword or "").strip().endswith("?"):
        return INFORMATIONAL
    return INFORMATIONAL


def brand_terms(site) -> set:
    """Words that mean "this person is looking for you specifically"."""
    if site is None:
        return set()
    host = re.sub(r"^https?://(www\.)?", "", site.homepage or "").strip("/").split("/")[0]
    return terms(site.label) | terms(host.replace(".", " "))


def is_question(text: str) -> bool:
    first = (text or "").strip().lower().split(" ")[0] if text else ""
    return (text or "").strip().endswith("?") or first in (
        "how", "what", "why", "when", "where", "which", "who", "can", "do", "does", "is")


def band_of(impressions: int, position: float, has_volume: bool = False) -> str:
    if not impressions:
        return UNVALIDATED if not has_volume else QUIET
    if position and position < STRIKING_MIN:
        return WINNING
    if position and STRIKING_MIN <= position <= STRIKING_MAX:
        return STRIKING if impressions >= MIN_IMPRESSIONS else QUIET
    if position and position > STRIKING_MAX:
        return DEEP
    return QUIET


def _reason(kw: Keyword) -> str:
    if kw.band == STRIKING:
        return (f"Position {kw.position} on {kw.impressions:,} impressions — page one is "
                "within reach. The fastest win there is: strengthen the page that already "
                "ranks rather than starting a new one.")
    if kw.band == WINNING:
        return (f"Already averaging position {kw.position} on {kw.impressions:,} "
                f"impressions and {kw.clicks:,} clicks. Protect it; don't write a second "
                "page for the same term.")
    if kw.band == DEEP:
        return (f"{kw.impressions:,} impressions but position {kw.position}. Real demand, "
                "a long way from page one — this needs better content, not a link.")
    if kw.band == QUIET:
        return (f"{kw.impressions:,} impressions, no meaningful position yet. Watch it "
                "rather than build on it.")
    if kw.volume is not None:
        return f"{kw.volume:,} monthly searches according to {provider()}."
    if kw.source == "autocomplete":
        return ("Google autocompletes this phrase, so people really type it — but nothing "
                "here measures how many. Treat the demand as unvalidated.")
    return "No impressions and no volume data. Unvalidated — this is a guess, not a number."


def _score(kw: Keyword) -> float:
    """
    Rank on what's measurable. Impressions are the backbone; striking distance is
    the multiplier, because that's where one piece of work moves the most.
    """
    base = math.log1p(max(kw.impressions, 0)) * 10
    if kw.volume is not None:
        base = max(base, math.log1p(kw.volume) * 8)
    if kw.band == STRIKING:
        base *= 1.8
    elif kw.band == DEEP:
        base *= 1.1
    elif kw.band == WINNING:
        base *= 0.7                     # least headroom left
    if kw.unvalidated:
        base += 1.0 if kw.source == "autocomplete" else 0.0
    return round(base, 1)


def finish(kw: Keyword) -> Keyword:
    """Fill in band, reason and score once the numbers are on the keyword."""
    kw.band = band_of(kw.impressions, kw.position, kw.volume is not None)
    kw.reason = _reason(kw)
    kw.score = _score(kw)
    return kw


# ── 1. Search Console (the first and best source) ──────────────────────────
def gsc_keywords(site, start: str, end: str, row_limit: int = 500) -> dict:
    """
    Every query this site got impressions for, as Keywords.
    Returns {'ok', 'keywords', 'detail'} — no credentials is not an error, it
    just means there's nothing first-party to work from yet.
    """
    if not enabled():
        return {"ok": False, "keywords": [],
                "detail": "The keyword engine is switched off in Settings."}
    if not config.credentials_available():
        return {"ok": False, "keywords": [],
                "detail": "No Google service-account file, so Search Console query data "
                          "isn't available. Everything below is unvalidated until it is."}

    rows = gsc.search_analytics(site.gsc_property, start, end, ["query"],
                                row_limit=row_limit)
    if not rows:
        return {"ok": False, "keywords": [],
                "detail": "Search Console returned no queries for this date range. Either "
                          "the site genuinely has no impressions yet, or the service "
                          "account can't read this property — Settings → Test connections "
                          "says which."}

    brands = brand_terms(site)
    pages = page_map(site, start, end)
    out = []
    for row in rows:
        query = (row.get("query") or "").strip()
        if not query:
            continue
        kw = Keyword(
            keyword=query, source="gsc", intent=intent_of(query, brands),
            clicks=int(row.get("clicks", 0) or 0),
            impressions=int(row.get("impressions", 0) or 0),
            ctr=float(row.get("ctr", 0) or 0),
            position=float(row.get("position", 0) or 0),
            page=pages.get(query.lower(), ""),
        )
        out.append(finish(kw))

    out.sort(key=lambda k: -k.score)
    return {"ok": True, "keywords": out,
            "detail": f"{len(out)} real queries from Search Console for {start} → {end}."}


def page_map(site, start: str, end: str, row_limit: int = 1000) -> dict:
    """query (lowercased) → the URL of yours that ranks for it. {} without creds."""
    if not config.credentials_available():
        return {}
    rows = gsc.search_analytics(site.gsc_property, start, end, ["page", "query"],
                                row_limit=row_limit)
    best = {}
    for row in rows:
        query = (row.get("query") or "").strip().lower()
        page = (row.get("page") or "").strip()
        if not query or not page:
            continue
        impressions = int(row.get("impressions", 0) or 0)
        if impressions >= best.get(query, (0, ""))[0]:
            best[query] = (impressions, page)
    return {q: p for q, (_, p) in best.items()}


def striking_distance(keywords: list, min_impressions: int = MIN_IMPRESSIONS) -> list:
    """The subset that is one push away from page one."""
    return [k for k in keywords
            if k.band == STRIKING and k.impressions >= min_impressions]


def for_page(site, url: str, start: str, end: str, limit: int = 8) -> list:
    """
    The queries one specific page of yours ranks for, best first. This is what
    the backlink targeter shows: *why* this page deserves a link, in the user's
    own Search Console numbers rather than a score out of nowhere.
    """
    if not (enabled() and config.credentials_available() and url):
        return []
    rows = gsc.search_analytics(site.gsc_property, start, end, ["page", "query"],
                                row_limit=1000)
    wanted = url.rstrip("/")
    brands = brand_terms(site)
    out = []
    for row in rows:
        if (row.get("page") or "").rstrip("/") != wanted:
            continue
        query = (row.get("query") or "").strip()
        if not query:
            continue
        out.append(finish(Keyword(
            keyword=query, source="gsc", intent=intent_of(query, brands),
            clicks=int(row.get("clicks", 0) or 0),
            impressions=int(row.get("impressions", 0) or 0),
            ctr=float(row.get("ctr", 0) or 0),
            position=float(row.get("position", 0) or 0),
            page=url,
        )))
    out.sort(key=lambda k: -k.score)
    return out[:limit]


# ── 2. Build the brief ─────────────────────────────────────────────────────
def _relevant(keywords: list, topic: str, floor: float = 0.15) -> list:
    """GSC queries that are actually about this topic, most relevant first."""
    scored = [(overlap(topic, k.keyword), k) for k in keywords]
    hits = [(rel, k) for rel, k in scored if rel >= floor]
    hits.sort(key=lambda pair: (-pair[0] * 100 - pair[1].score))
    return [k for _, k in hits]


def brief(topic: str, site, start: str = "", end: str = "",
          use_autocomplete: bool = True, gsc_keywords_cached: list = None,
          limit: int = 15) -> Brief:
    """
    Turn a topic into the keyword brief the writer builds on: one primary, a
    secondary cluster, real questions, and a target page.

    Follows the skill's honest heuristic for picking the primary:
    striking-distance GSC term → paid-API volume → autocomplete-confirmed →
    otherwise the topic itself, explicitly marked unvalidated.
    """
    topic = (topic or "").strip()
    if not topic:
        return Brief(topic, ok=False, detail="Give the keyword engine a topic first.")
    if not enabled():
        return Brief(topic, ok=False,
                     detail="The keyword engine is switched off. Turn it on in "
                            "Settings → Content tools — it needs no paid key.")

    used, notes = [], []
    candidates: list = []

    # 1. Search Console first.
    if gsc_keywords_cached is None:
        found = gsc_keywords(site, start, end) if (site and start and end) else {
            "ok": False, "keywords": [], "detail": "No date range given."}
        gsc_all = found["keywords"]
        if not found["ok"]:
            notes.append(found["detail"])
    else:
        gsc_all = gsc_keywords_cached
    if gsc_all:
        used.append("Search Console")
        candidates.extend(_relevant(gsc_all, topic))

    # 2. Free autocomplete expansion.
    brands = brand_terms(site)
    if use_autocomplete:
        suggest = autocomplete(topic)
        if suggest["ok"]:
            used.append("Google autocomplete")
            known = {k.keyword.lower() for k in candidates}
            for phrase in suggest["suggestions"]:
                if phrase.lower() in known:
                    continue
                known.add(phrase.lower())
                candidates.append(finish(Keyword(
                    keyword=phrase, source="autocomplete",
                    intent=intent_of(phrase, brands))))
        else:
            notes.append(suggest["detail"])

    # 3. The optional paid slot — only ever *adds* numbers, never invents them.
    if live() and candidates:
        found_metrics = metrics([k.keyword for k in candidates[:50]])
        if found_metrics:
            used.append(provider())
            for kw in candidates:
                row = found_metrics.get(kw.keyword.lower())
                if row:
                    kw.volume = row.get("volume")
                    kw.difficulty = row.get("difficulty")
                    finish(kw)

    if not candidates:
        seed = finish(Keyword(keyword=topic, source="seed", intent=intent_of(topic, brands)))
        return Brief(
            topic, primary=seed, secondary=[], questions=[], target_page="",
            notes="Nothing measured this topic: no Search Console impressions and no "
                  "autocomplete data. The keyword below is the topic as you typed it, "
                  "and it is **unvalidated** — a guess, not demand.",
            sources_used=[], ok=False,
            detail=" ".join(notes) or "No keyword source returned anything.")

    candidates.sort(key=lambda k: -k.score)

    # Primary: the skill's order of preference.
    striking = [k for k in candidates if k.band == STRIKING]
    with_volume = [k for k in candidates if k.volume is not None]
    validated = [k for k in candidates if k.validated]
    if striking:
        primary = striking[0]
        notes.append("Primary keyword is a striking-distance term — the page that already "
                     "ranks for it is the fastest win on this topic.")
    elif with_volume:
        primary = with_volume[0]
    elif validated:
        primary = validated[0]
    else:
        primary = candidates[0]
        notes.append("No keyword here has measured demand behind it, so the primary is "
                     "**unvalidated** — autocomplete confirms people phrase it this way, "
                     "but not how many.")

    secondary = [k for k in candidates if k is not primary][:limit]
    questions = [k.keyword for k in candidates if is_question(k.keyword)][:8]

    target = primary.page or next((k.page for k in candidates if k.page), "")
    return Brief(
        topic=topic, primary=primary, secondary=secondary, questions=questions,
        target_page=target, notes=" ".join(notes),
        sources_used=used, ok=True,
        detail=f"{len(candidates)} candidates from {', '.join(used) or 'nothing'}.")
