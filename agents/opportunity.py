"""
The Opportunity Finder — "what should I write next?", answered with evidence.

This is the dashboard's implementation of the `competitor-site-scraper` skill,
widened to look at your own site at the same time. It scans three things and
merges what they say into one ranked list:

  1. **Competitors** — their sitemap (one polite fetch) plus a site-scoped
     search for titles, turned into the topics they cover. Optionally it reads a
     handful of their best pages for the question-shaped headings they answer.
  2. **Your own coverage** — the pages in the shared coverage frame. Tools you
     ship with no article explaining them, and pages Google crawled and rejected
     on quality, are opportunities in their own right.
  3. **Your Search Console queries** — via `core/keywords.py`, when the keyword
     branch is on. Striking-distance terms are the fastest wins you own.

Every opportunity carries the evidence behind it, the same way Lane B's prospect
scores do: the score is a summary of the listed reasons, never an authority in
itself. Nothing here invents a search volume — an opportunity with no
impressions behind it is marked **unvalidated** and says so on the card.

Guardrails (CLAUDE.md + the skill):
  - competitor pages are read politely: robots.txt is honoured, there's a delay
    between fetches, and the caps are 3 competitors / 4 pages each.
  - competitor text is never reproduced. Only topics, titles and question
    headings are recorded, and they exist to find the gap — not to copy it.
  - your own domains and the usual social/aggregator noise are never treated as
    competitors.
"""

import re
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field

import requests

from core import config, gsc, keywords as kw, search
from core.classifier import CONTENT, CRAWL_BUDGET, HEALTHY
# Lane B already solved domain handling, the exclusion list and page reading.
from agents.outreach import EXCLUDED_DOMAINS, _fetch, domain_of, own_domains

TIMEOUT = 12
UA = "seo-command-center (content-gap research)"
POLITE_DELAY = 1.0                 # seconds between fetches on the same competitor

MAX_COMPETITORS = 3                # the skill's cap: this is analysis, not scraping
PAGES_PER_COMPETITOR = 4

# Kinds of opportunity, in the order they're worth acting on.
STRIKING = "Striking distance"
GAP = "Competitor gap"
ORPHAN = "Tool with no article"
REWRITE = "Rejected on quality"

KIND_ICON = {STRIKING: "🎯", GAP: "🕳️", ORPHAN: "🧰", REWRITE: "🟠"}
KIND_BLURB = {
    STRIKING: "A query you already rank 5th-20th for. Strengthen the page that ranks.",
    GAP: "Competitors cover this and you don't. The clearest reason to write something new.",
    ORPHAN: "You ship the tool but nothing explains it. The article is the way in.",
    REWRITE: "Google crawled this and declined it on quality. Rewriting beats writing more.",
}

# URL paths that are never a content topic.
_NON_CONTENT = re.compile(
    r"/(category|categories|tag|tags|author|page|feed|search|wp-|wp-content|amp|"
    r"privacy|privacy-policy|terms|terms-of-service|disclaimer|about|about-us|"
    r"contact|contact-us|sitemap|cart|checkout|login|register|account)(/|$|\.)",
    re.IGNORECASE)

# Only used when robots.txt doesn't name a sitemap, which most do.
_SITEMAP_NAMES = ("sitemap_index.xml", "sitemap.xml", "wp-sitemap.xml")

_HEADING_RE = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# ── Dataclasses ────────────────────────────────────────────────────────────
@dataclass
class CompetitorPage:
    url: str
    topic: str                      # readable topic, from the title or the slug
    title: str = ""
    domain: str = ""


@dataclass
class CompetitorMap:
    """What one competitor covers, and how we found out."""
    domain: str
    pages: list = field(default_factory=list)     # [CompetitorPage]
    questions: list = field(default_factory=list) # question headings they answer
    sources: list = field(default_factory=list)   # "sitemap" / "search" / "pages read"
    ok: bool = True
    detail: str = ""


@dataclass
class Opportunity:
    """One thing worth writing, with the evidence that says so."""
    topic: str
    kind: str
    keyword: str = ""
    target_page: str = ""           # an existing URL to strengthen; "" means a new post
    competitors: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    impressions: int = 0
    position: float = 0.0
    score: int = 0
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    unvalidated: bool = True
    angle: str = ""

    @property
    def icon(self) -> str:
        return KIND_ICON.get(self.kind, "💡")

    @property
    def demand(self) -> str:
        """What we can honestly say about demand for this topic."""
        if self.impressions:
            pos = f" at position {self.position}" if self.position else ""
            return f"{self.impressions:,} impressions{pos} in Search Console"
        return "unvalidated — no impressions and no volume data"


@dataclass
class ScanResult:
    opportunities: list = field(default_factory=list)
    maps: list = field(default_factory=list)
    keywords: list = field(default_factory=list)   # the GSC keyword list, reused by the UI
    notes: list = field(default_factory=list)
    ok: bool = True
    detail: str = ""


# ── Small helpers ──────────────────────────────────────────────────────────
def configured_competitors(site) -> list:
    """The competitor domains saved for this site in Settings, if any."""
    raw = config.get(f"{site.env_prefix}_COMPETITORS", "")
    out = []
    for part in re.split(r"[,\s]+", raw):
        part = part.strip().strip("/")
        if not part:
            continue
        domain = domain_of(part)
        if domain and domain not in out:
            out.append(domain)
    return out


def _is_excluded(domain: str) -> bool:
    return any(domain == bad or domain.endswith("." + bad) for bad in EXCLUDED_DOMAINS)


def topic_from_url(url: str) -> str:
    """A readable topic from a URL slug, or "" when the path isn't content."""
    path = urllib.parse.urlparse(url).path
    if not path or _NON_CONTENT.search(path):
        return ""
    segment = [p for p in path.strip("/").split("/") if p]
    if not segment:
        return ""
    last = re.sub(r"\.(html?|php|aspx?)$", "", segment[-1])
    if re.fullmatch(r"[\d\-]+", last):          # a date or an id, not a topic
        return ""
    words = [w for w in re.split(r"[-_]+", last) if w and not w.isdigit()]
    if len(words) < 2 and len(last) < 4:
        return ""
    return " ".join(words).strip()


def _clean_title(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    # Strip the site name most titles end with: "Topic - Some Site"
    return re.sub(r"\s*[|\-–—]\s*[^|\-–—]{2,40}$", "", text).strip() or text


def _robots(domain: str, cache: dict) -> dict:
    """
    A domain's robots.txt, fetched once and reused: the parsed rules we have to
    obey, plus any `Sitemap:` lines it advertises — which saves guessing at
    filenames later.
    """
    if domain in cache:
        return cache[domain]
    entry = {"parser": None, "sitemaps": []}
    try:
        r = requests.get(f"https://{domain}/robots.txt", timeout=TIMEOUT,
                         headers={"User-Agent": UA})
        if r.status_code == 200 and len(r.text) < 500_000:
            lines = r.text.splitlines()
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(lines)
            entry["parser"] = parser
            entry["sitemaps"] = [line.split(":", 1)[1].strip() for line in lines
                                 if line.lower().startswith("sitemap:")][:3]
    except Exception:
        pass
    cache[domain] = entry
    return entry


def _may_fetch(url: str, cache: dict) -> bool:
    """Honour robots.txt. No robots.txt (or an unreadable one) means allowed."""
    parser = _robots(domain_of(url), cache).get("parser")
    if parser is None:
        return True
    try:
        return parser.can_fetch(UA, url)
    except Exception:
        return True


# ── 1. Who are the competitors? ────────────────────────────────────────────
def find_competitors(niche: str, site=None, limit: int = MAX_COMPETITORS) -> dict:
    """
    Search the niche and take the top domains that aren't yours and aren't the
    usual social/aggregator noise. Returns {'ok', 'domains', 'detail'}.
    """
    niche = (niche or "").strip()
    if not niche:
        return {"ok": False, "domains": [], "detail": "No niche or topic given."}

    mine = own_domains()
    result = search.search(niche, limit=15)
    if not result["ok"]:
        return {"ok": False, "domains": [], "detail": result["detail"]}

    domains = []
    for hit in result["results"]:
        domain = domain_of(hit.url)
        if not domain or domain in mine or _is_excluded(domain) or domain in domains:
            continue
        domains.append(domain)
        if len(domains) >= limit:
            break
    if not domains:
        return {"ok": False, "domains": [],
                "detail": "The search found no independent sites for that phrase — only "
                          "your own pages or the usual aggregators."}
    return {"ok": True, "domains": domains,
            "detail": f"Top {len(domains)} independent domains ranking for “{niche}”."}


# ── 2. What does a competitor cover? ───────────────────────────────────────
def map_competitor(domain: str, niche: str = "", read_pages: bool = False,
                   max_pages: int = PAGES_PER_COMPETITOR,
                   robots_cache: dict = None) -> CompetitorMap:
    """
    Map one competitor's coverage: their sitemap for breadth, a site-scoped
    search for real titles, and optionally a few pages read for the questions
    they answer. Polite by construction — see the caps at the top of the file.
    """
    domain = domain_of(domain)
    robots_cache = robots_cache if robots_cache is not None else {}
    cmap = CompetitorMap(domain=domain)
    seen = set()

    # Breadth: their sitemap. robots.txt usually names it; the guesses are the
    # fallback. `gsc.discover_urls` already walks sitemap indexes.
    advertised = _robots(domain, robots_cache)["sitemaps"]
    for url in advertised + [f"https://{domain}/{name}" for name in _SITEMAP_NAMES]:
        if not _may_fetch(url, robots_cache):
            continue
        urls = gsc.discover_urls(url, limit=400)
        if urls:
            for page_url in urls:
                topic = topic_from_url(page_url)
                key = page_url.rstrip("/")
                if not topic or key in seen:
                    continue
                seen.add(key)
                cmap.pages.append(CompetitorPage(url=page_url, topic=topic, domain=domain))
            cmap.sources.append(f"sitemap ({len(urls)} URLs)")
            break
        time.sleep(POLITE_DELAY)

    # Depth: real titles, from a site-scoped search.
    query = f"site:{domain} {niche}".strip()
    result = search.search(query, limit=15)
    if result["ok"]:
        added = 0
        for hit in result["results"]:
            if domain_of(hit.url) != domain:
                continue
            key = hit.url.rstrip("/")
            title = _clean_title(hit.title)
            topic = title or topic_from_url(hit.url)
            if not topic:
                continue
            existing = next((p for p in cmap.pages if p.url.rstrip("/") == key), None)
            if existing:
                existing.title = title or existing.title
                if title:
                    existing.topic = title
                continue
            seen.add(key)
            cmap.pages.append(CompetitorPage(url=hit.url, topic=topic, title=title,
                                             domain=domain))
            added += 1
        if added or cmap.pages:
            cmap.sources.append("site: search")
    elif not cmap.pages:
        cmap.ok = False
        cmap.detail = result["detail"]
        return cmap

    # Optional: read a few of their most relevant pages for the questions they
    # answer. This is where the FAQ gaps come from.
    if read_pages and cmap.pages:
        for page in _most_relevant(cmap.pages, niche, max_pages):
            if not _may_fetch(page.url, robots_cache):
                continue
            html = _fetch(page.url, timeout=TIMEOUT)
            time.sleep(POLITE_DELAY)
            if not html:
                continue
            if not page.title:
                match = _TITLE_RE.search(html)
                if match:
                    page.title = _clean_title(match.group(1))
                    page.topic = page.title or page.topic
            for raw in _HEADING_RE.findall(html)[:40]:
                heading = _clean_title(raw)
                if 12 <= len(heading) <= 120 and kw.is_question(heading) \
                        and heading not in cmap.questions:
                    cmap.questions.append(heading)
        if cmap.questions:
            cmap.sources.append(f"{len(cmap.questions)} question headings read")

    if not cmap.pages:
        cmap.ok = False
        cmap.detail = (f"Couldn't read anything from {domain}: no reachable sitemap and no "
                       "search results for it. Check the domain, or try again later.")
        return cmap

    cmap.detail = (f"{len(cmap.pages)} pages mapped from {domain} via "
                   f"{', '.join(cmap.sources)}.")
    return cmap


def _most_relevant(pages: list, niche: str, count: int) -> list:
    """The competitor pages closest to the niche — what's worth reading."""
    if not niche:
        return pages[:count]
    ranked = sorted(pages, key=lambda p: -kw.overlap(niche, p.topic))
    return [p for p in ranked if kw.overlap(niche, p.topic) > 0][:count] or pages[:count]


# ── 3. What do *I* cover? ──────────────────────────────────────────────────
@dataclass
class OwnCoverage:
    """Your side of the comparison: your tools, your articles, your queries."""
    tools: list = field(default_factory=list)       # [{url, page, topic, bucket}]
    articles: list = field(default_factory=list)    # same shape
    rejected: list = field(default_factory=list)    # crawled and declined on quality
    query_terms: set = field(default_factory=set)   # words you already get impressions for

    @property
    def topics(self) -> list:
        return [p["topic"] for p in self.tools + self.articles if p["topic"]]


def own_coverage(coverage_df, site, gsc_keywords: list = None) -> OwnCoverage:
    """Read your own coverage frame into tools, articles and rejected pages."""
    own = OwnCoverage()
    if coverage_df is not None and not getattr(coverage_df, "empty", True):
        for _, row in coverage_df.iterrows():
            url, bucket = row["URL"], row["Bucket"]
            topic = topic_from_url(url)
            if not topic:
                continue
            entry = {"url": url, "page": row["Page"], "topic": topic, "bucket": bucket}
            is_article = bool(re.search(r"/(blog|blogs|article|articles|post|posts|news)/",
                                        url, re.IGNORECASE))
            if bucket == CONTENT:
                own.rejected.append(entry)
            if is_article:
                own.articles.append(entry)
            elif bucket in (HEALTHY, CRAWL_BUDGET, CONTENT):
                own.tools.append(entry)

    for keyword in gsc_keywords or []:
        own.query_terms |= kw.terms(keyword.keyword)
    return own


def _covered(topic: str, own: OwnCoverage, floor: float = 0.4) -> tuple:
    """Do I already have a page about this? Returns (covered, the closest page)."""
    best, best_score = None, 0.0
    for entry in own.articles + own.tools:
        score = kw.overlap(topic, entry["topic"])
        if score > best_score:
            best, best_score = entry, score
    return (best_score >= floor, best)


# ── 4. Merge everything into a ranked list ─────────────────────────────────
def _demand_for(topic: str, gsc_keywords: list) -> tuple:
    """The best-matching real query for a topic: (keyword, impressions, position)."""
    best, best_rel = None, 0.0
    for keyword in gsc_keywords or []:
        rel = kw.overlap(topic, keyword.keyword)
        if rel > best_rel:
            best, best_rel = keyword, rel
    if best is None or best_rel < 0.3:
        return None, 0, 0.0
    return best, best.impressions, best.position


def _finalise(opp: Opportunity) -> Opportunity:
    """Turn the listed evidence into a score. The reasons are the authority."""
    score = 0
    if opp.kind == STRIKING:
        score += 40
    if len(opp.competitors) >= 2:
        score += 25
    elif len(opp.competitors) == 1:
        score += 15
    if opp.impressions:
        score += min(25, int(opp.impressions ** 0.5))
    if opp.kind == ORPHAN:
        score += 15
    if opp.kind == REWRITE:
        score += 10
    if opp.questions:
        score += 5
    if opp.unvalidated:
        opp.warnings.append("No measured demand behind this topic yet — it's a lead, "
                            "not a number.")
    opp.score = max(0, min(100, score))
    return opp


def scan(site, coverage_df=None, niche: str = "", competitors: list = None,
         start: str = "", end: str = "", use_keywords: bool = True,
         read_pages: bool = False, limit: int = 25,
         max_competitors: int = MAX_COMPETITORS,
         pages_per_competitor: int = PAGES_PER_COMPETITOR,
         progress=None) -> ScanResult:
    """
    The whole scan. `progress` is an optional callback(fraction, message) so the
    UI can show where it is. Never raises: every source that fails leaves a note
    and the rest of the scan carries on.
    """
    result = ScanResult()
    niche = (niche or "").strip()

    def step(fraction: float, message: str) -> None:
        if progress:
            progress(fraction, message)

    # ── Your Search Console queries (only when the keyword branch is on) ────
    gsc_keywords = []
    if use_keywords and kw.enabled():
        step(0.05, "Reading the queries you already rank for…")
        found = kw.gsc_keywords(site, start, end) if (start and end) else {
            "ok": False, "keywords": [], "detail": "No date range selected."}
        gsc_keywords = found["keywords"]
        if not found["ok"]:
            result.notes.append(found["detail"])
    elif not kw.enabled():
        result.notes.append("The keyword engine is off, so this scan is competitor- and "
                            "coverage-only. Striking-distance opportunities need it on.")
    result.keywords = gsc_keywords

    own = own_coverage(coverage_df, site, gsc_keywords)

    # ── Competitors ────────────────────────────────────────────────────────
    domains = [domain_of(d) for d in (competitors or []) if d]
    domains = [d for d in dict.fromkeys(domains) if d and not _is_excluded(d)]
    if not domains and niche:
        step(0.15, "Finding who ranks for this niche…")
        found = find_competitors(niche, site, limit=max_competitors)
        domains = found["domains"]
        if not found["ok"]:
            result.notes.append(found["detail"])
    domains = domains[:max_competitors]

    for i, domain in enumerate(domains):
        step(0.2 + 0.5 * (i / max(len(domains), 1)), f"Mapping what {domain} covers…")
        cmap = map_competitor(domain, niche, read_pages=read_pages,
                              max_pages=pages_per_competitor)
        result.maps.append(cmap)
        if not cmap.ok:
            result.notes.append(cmap.detail)

    # ── Build the opportunities ────────────────────────────────────────────
    step(0.8, "Comparing their coverage with yours…")
    opportunities = []
    opportunities += _gap_opportunities(result.maps, own, gsc_keywords)
    if use_keywords and kw.enabled():
        opportunities += _striking_opportunities(gsc_keywords, own)
    opportunities += _orphan_opportunities(own, gsc_keywords)
    opportunities += _rewrite_opportunities(own, gsc_keywords)

    opportunities.sort(key=lambda o: (-o.score, o.topic))
    result.opportunities = opportunities[:limit]

    step(1.0, "Done.")
    result.ok = bool(result.opportunities)
    if result.ok:
        counts = {}
        for opp in result.opportunities:
            counts[opp.kind] = counts.get(opp.kind, 0) + 1
        result.detail = (f"{len(result.opportunities)} opportunities · "
                         + " · ".join(f"{n} {k.lower()}" for k, n in counts.items()))
    else:
        result.detail = ("Nothing surfaced. Add a competitor domain or a niche phrase "
                         "above, or connect Search Console so your own queries can be read.")
    return result


def _gap_opportunities(maps: list, own: OwnCoverage, gsc_keywords: list) -> list:
    """Topics competitors cover that you don't — the classic content gap."""
    # Group near-identical competitor topics so two rivals writing the same
    # thing counts as one (stronger) opportunity rather than two.
    clusters: list = []
    for cmap in maps:
        for page in cmap.pages:
            topic = page.topic.strip()
            if not topic or len(topic) < 8:
                continue
            match = next((c for c in clusters if kw.overlap(c["topic"], topic) >= 0.55),
                         None)
            if match:
                if cmap.domain not in match["domains"]:
                    match["domains"].append(cmap.domain)
                if len(topic) > len(match["topic"]):
                    match["topic"] = topic
                match["questions"] += [q for q in cmap.questions
                                       if q not in match["questions"]]
            else:
                clusters.append({"topic": topic, "domains": [cmap.domain],
                                 "questions": cmap.questions})

    out = []
    for cluster in clusters:
        covered, closest = _covered(cluster["topic"], own)
        if covered:
            continue
        keyword, impressions, position = _demand_for(cluster["topic"], gsc_keywords)
        reasons = [f"Covered by {', '.join(cluster['domains'])}; nothing on your site "
                   "matches it."]
        if closest:
            reasons.append(f"Your closest page is {closest['page']} — related, but not "
                           "the same question.")
        if impressions:
            reasons.append(f"Search Console already shows {impressions:,} impressions for "
                           f"“{keyword.keyword}”, so the demand is real and measured.")
        questions = [q for q in cluster["questions"]
                     if kw.overlap(cluster["topic"], q) >= 0.25][:4]
        if questions:
            reasons.append(f"{len(questions)} question headings on their pages you could "
                           "answer better.")
        out.append(_finalise(Opportunity(
            topic=cluster["topic"], kind=GAP,
            keyword=keyword.keyword if keyword else "",
            competitors=cluster["domains"], questions=questions,
            impressions=impressions, position=position,
            unvalidated=not impressions, reasons=reasons,
            angle=("Answer it more directly than they do: an answer-first opening, a "
                   "worked example, and an FAQ they don't have."),
        )))
    return out


def _striking_opportunities(gsc_keywords: list, own: OwnCoverage) -> list:
    """Queries you rank 5th-20th for. The fastest wins you already own."""
    out = []
    for keyword in kw.striking_distance(gsc_keywords)[:12]:
        page = keyword.page
        entry = next((e for e in own.tools + own.articles
                      if e["url"].rstrip("/") == page.rstrip("/")), None)
        reasons = [keyword.reason]
        if entry:
            reasons.append(f"The page that ranks is {entry['page']} — strengthen that "
                           "rather than writing a competing one.")
        elif page:
            reasons.append(f"The page that ranks is {page}.")
        else:
            reasons.append("Search Console didn't say which page ranks for it — check "
                           "before writing, so you don't compete with yourself.")
        out.append(_finalise(Opportunity(
            topic=keyword.keyword, kind=STRIKING, keyword=keyword.keyword,
            target_page=page, impressions=keyword.impressions,
            position=keyword.position, unvalidated=False, reasons=reasons,
            angle=("Deepen the page that already ranks: answer the query in the first "
                   "paragraph, add the sub-questions, and link to it internally."),
        )))
    return out


def _orphan_opportunities(own: OwnCoverage, gsc_keywords: list) -> list:
    """Tools you ship that no article explains — an easy, honest win."""
    out = []
    for tool in own.tools:
        if tool["bucket"] == CONTENT:
            continue                    # that's a rewrite, handled below
        if any(kw.overlap(tool["topic"], article["topic"]) >= 0.4
               for article in own.articles):
            continue
        keyword, impressions, position = _demand_for(tool["topic"], gsc_keywords)
        reasons = [f"{tool['page']} exists and is {tool['bucket'].lower()}, but no article "
                   "on your site explains when or why to use it."]
        if impressions:
            reasons.append(f"“{keyword.keyword}” already draws {impressions:,} impressions "
                           "— an article can catch the searches the tool page doesn't.")
        reasons.append("A supporting article is also the natural internal link into the "
                       "tool, which is what gets it crawled.")
        out.append(_finalise(Opportunity(
            topic=f"How to use {tool['topic']}", kind=ORPHAN,
            keyword=keyword.keyword if keyword else tool["topic"],
            target_page=tool["url"], impressions=impressions, position=position,
            unvalidated=not impressions, reasons=reasons,
            angle=("Write the use-case article the tool page can't be: the real problem, "
                   "a worked example, and a link into the tool at the point it helps."),
        )))
    return out[:8]


def _rewrite_opportunities(own: OwnCoverage, gsc_keywords: list) -> list:
    """Pages Google crawled and declined. Rewriting beats writing more."""
    out = []
    for page in own.rejected[:6]:
        keyword, impressions, position = _demand_for(page["topic"], gsc_keywords)
        reasons = [f"{page['page']} was crawled and left un-indexed on quality. Another "
                   "thin page next to it makes the site worse, not better."]
        if impressions:
            reasons.append(f"There is still demand: {impressions:,} impressions for "
                           f"“{keyword.keyword}”.")
        reasons.append("Rewriting it — real use-cases, a worked example, an FAQ — is what "
                       "changes Google's mind.")
        out.append(_finalise(Opportunity(
            topic=page["topic"], kind=REWRITE,
            keyword=keyword.keyword if keyword else "",
            target_page=page["url"], impressions=impressions, position=position,
            unvalidated=not impressions, reasons=reasons,
            angle=("Rewrite it as the answer to one real question, then keep the tool or "
                   "product point secondary."),
        )))
    return out
