"""
The Backlink agent — Lane A: auto-publish to platforms you own.

Three steps, in the order the dashboard walks you through them:

  1. rank_targets()   which of your pages is worth a link, and why. Only pages
                      Google has actually accepted (Healthy) or hasn't crawled
                      yet (Crawl budget) are eligible — a link to a broken or
                      quality-rejected page is wasted effort, so those are
                      excluded on purpose.
  2. draft_article()  writes a genuinely useful, platform-tailored article with
                      BACKLINK_MODEL, containing ONE natural contextual link
                      back to the target page.
  3. publish()        hands it to a publisher for a platform the user owns and
                      records the outcome in the tracker.

Guardrails this module enforces (CLAUDE.md):
  - destinations come only from `publishers.PLATFORMS`, which is owned platforms
    only. There is no third-party publish path in Lane A.
  - the drafting prompt forbids invented statistics, quotes and keyword stuffing,
    and asks for one link — not a link farm.
  - WordPress stays a draft; that's enforced in the publisher itself.
"""

import json
import math
import re
from dataclasses import dataclass

import requests

from core import config, gsc, openrouter, tracker
from core.classifier import CRAWL_BUDGET, HEALTHY
from publishers import PLATFORMS, Article, PublishResult

# The only buckets worth pointing a link at.
ELIGIBLE_BUCKETS = (HEALTHY, CRAWL_BUDGET)

COMPOUND = "Compound"      # already indexed — links make a good page stronger
RESCUE = "Rescue"          # discovered, never crawled — a link is the unlock


@dataclass
class Target:
    """One page of yours, scored as a link target."""
    url: str
    page: str              # path only, for display
    bucket: str
    opportunity: str       # COMPOUND | RESCUE
    clicks: int = 0
    impressions: int = 0
    position: float = 0.0
    score: float = 0.0
    reason: str = ""       # why this page, in one plain sentence
    has_metrics: bool = False


@dataclass
class DraftResult:
    ok: bool
    article: Article = None
    detail: str = ""


# ── 1. Which page deserves a link ──────────────────────────────────────────
def _score(impressions: int, position: float, bucket: str) -> float:
    """
    Impressions say how much demand a page already sees; position says how much
    headroom is left. A page sitting 5th-20th on real impressions is where one
    good link moves the most — it's within striking distance of page one.
    """
    base = math.log1p(max(impressions, 0)) * 10

    if bucket == CRAWL_BUDGET:
        # No impressions by definition — Google hasn't crawled it. The flat
        # bonus reflects that a link here changes indexing, not just ranking.
        return base + 25.0

    if position <= 0:
        multiplier = 1.0            # no position data for this page
    elif position < 4:
        multiplier = 0.8            # already near the top: least headroom
    elif position <= 20:
        multiplier = 1.6            # striking distance: best return on a link
    elif position <= 40:
        multiplier = 1.2
    else:
        multiplier = 0.9
    return base * multiplier


def _reason(bucket: str, impressions: int, position: float, has_metrics: bool) -> str:
    if bucket == CRAWL_BUDGET:
        return ("Discovered but never crawled. This is the one bucket where a backlink "
                "genuinely helps — it gives Google a reason to go and fetch the page.")
    if not has_metrics:
        return ("Indexed, so links to it compound. No Search Console figures for this "
                "date range, so this isn't ranked on performance — unvalidated.")
    if impressions == 0:
        return "Indexed but no impressions yet in this range. A link builds its authority slowly."
    if position and position < 4:
        return (f"Already averaging position {position} on {impressions:,} impressions. "
                "Solid, but there's less headroom than the pages below it.")
    if position and position <= 20:
        return (f"Position {position} on {impressions:,} impressions — striking distance. "
                "One good link is most likely to pay off here.")
    return (f"{impressions:,} impressions at position {position}. Real demand, but it's "
            "a long way from page one — content matters more than links at this depth.")


def rank_targets(site, coverage_df, start: str = "", end: str = "",
                 limit: int = 25) -> tuple:
    """
    Rank this site's link-eligible pages. Returns (targets, source) where source
    is "live" when Search Console performance figures were used and
    "coverage-only" when the ranking is just the eligible list (no invented
    numbers — see CLAUDE.md).

    `coverage_df` is the shared frame from `ui.data.coverage_frame`, so the agent
    never has to re-inspect URLs.
    """
    if coverage_df is None or coverage_df.empty:
        return [], "coverage-only"

    eligible = coverage_df[coverage_df["Bucket"].isin(ELIGIBLE_BUCKETS)]
    if eligible.empty:
        return [], "coverage-only"

    # Performance figures, keyed by URL. Empty without credentials — that's fine.
    metrics = {}
    if start and end and config.credentials_available():
        for row in gsc.search_analytics(site.gsc_property, start, end, ["page"],
                                        row_limit=500):
            url = (row.get("page") or "").rstrip("/")
            if url:
                metrics[url] = row
    source = "live" if metrics else "coverage-only"

    targets = []
    for _, row in eligible.iterrows():
        url = row["URL"]
        m = metrics.get(url.rstrip("/"), {})
        impressions = int(m.get("impressions", 0) or 0)
        position = float(m.get("position", 0) or 0)
        bucket = row["Bucket"]
        targets.append(Target(
            url=url,
            page=row["Page"],
            bucket=bucket,
            opportunity=RESCUE if bucket == CRAWL_BUDGET else COMPOUND,
            clicks=int(m.get("clicks", 0) or 0),
            impressions=impressions,
            position=position,
            score=round(_score(impressions, position, bucket), 1),
            reason=_reason(bucket, impressions, position, bool(m)),
            has_metrics=bool(m),
        ))

    targets.sort(key=lambda t: (-t.score, t.page))
    return targets[:limit], source


# ── 2. Draft the article ───────────────────────────────────────────────────
def page_facts(url: str, timeout: int = 10, html: str = "") -> dict:
    """
    Read a page's own title, meta description and first heading, so the article
    is written about what the page actually is rather than a guess from its
    slug. Returns {} if the page can't be fetched — the caller falls back to the
    slug and says so.

    Pass `html` when you have already fetched the page (Lane B reads a prospect's
    guidelines page for scoring) so this parses it instead of fetching it twice.
    """
    try:
        if html:
            html = html[:200_000]
        else:
            r = requests.get(url, timeout=timeout,
                             headers={"User-Agent": "seo-command-center"})
            r.raise_for_status()
            html = r.text[:200_000]
        def grab(pattern):
            m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        return {
            "title": grab(r"<title[^>]*>(.*?)</title>"),
            "description": grab(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']'),
            "heading": re.sub(r"<[^>]+>", "", grab(r"<h1[^>]*>(.*?)</h1>")).strip(),
        }
    except Exception:
        return {}


def _slug_topic(url: str) -> str:
    """A readable topic guess from the URL, used when the page won't load."""
    path = re.sub(r"https?://[^/]+", "", url).strip("/")
    return (path.split("/")[-1] or "the homepage").replace("-", " ").replace("_", " ")


_SYSTEM = (
    "You write genuinely useful articles for developer and how-to audiences. "
    "You are strictly factual: you never invent statistics, search volumes, "
    "benchmarks, dates, company names or quotes. If a number would strengthen a "
    "claim but you do not know it, you make the point qualitatively instead. "
    "You write plainly and never pad. You return only JSON when asked for JSON."
)


def _prompt(site, target: Target, platform, facts: dict, notes: str) -> str:
    if facts.get("title") or facts.get("description"):
        known = (f"- Its page title: {facts.get('title', '')}\n"
                 f"- Its meta description: {facts.get('description', '')}\n"
                 f"- Its main heading: {facts.get('heading', '')}")
    else:
        known = (f"- The page could not be fetched, so all you know is its URL. Infer the "
                 f"topic from the slug (\"{_slug_topic(target.url)}\") and stay general "
                 f"enough that you cannot be wrong about what the page contains.")

    return f"""Write one article for {platform.label}.

AUDIENCE AND TONE
Write for {platform.style}

THE PAGE THIS ARTICLE SHOULD LINK TO
- URL: {target.url}
- It lives on {site.label} ({site.homepage})
{known}

WHAT THE ARTICLE MUST DO
1. Stand on its own. A reader who never clicks the link should still finish it
   glad they read it. Teach something concrete: a real problem, how to approach
   it, and a worked example or step-by-step walkthrough.
2. Contain EXACTLY ONE link to {target.url}, in markdown, placed at the point in
   the article where that page is genuinely the useful next step. Use descriptive
   anchor text that reads naturally in the sentence — never "click here", and
   never the raw URL as the anchor.
3. Be 700-1100 words. No filler, no "in today's fast-paced digital world",
   no restating the title as the first sentence.
4. Use question-shaped H2 headings where they fit, and end with a short FAQ of
   two or three real questions someone would actually type.

HARD RULES
- Invent nothing. No made-up statistics, percentages, study results, quotes or
  tool names. Anything you are not sure of, say qualitatively or leave out.
- No keyword stuffing and no other outbound links to {site.homepage}.
- Do not mention SEO, backlinks, or that this article exists to link somewhere.
{f"- Extra direction from the user: {notes}" if notes.strip() else ""}

RETURN
Only a JSON object, no code fence, with exactly these keys:
{{"title": "the post title, under 70 characters",
  "summary": "one sentence, under 160 characters",
  "tags": ["3-4 short lowercase topic tags"],
  "body_markdown": "the full article in markdown, starting at the first paragraph (no H1 — the title is separate)"}}"""


def _parse_json(text: str) -> dict:
    """Pull the JSON object out of a model reply, code fence or not."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            return {}
    return {}


def draft_article(site, target: Target, platform_key: str, notes: str = "") -> DraftResult:
    """Write one platform-tailored article for `target`. Never raises."""
    platform = PLATFORMS.get(platform_key)
    if not platform:
        return DraftResult(False, detail=f"Unknown platform '{platform_key}'.")

    facts = page_facts(target.url)
    result = openrouter.chat(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": _prompt(site, target, platform, facts, notes)}],
        model=config.get("BACKLINK_MODEL"),
        temperature=0.7,
    )
    if not result["ok"]:
        return DraftResult(False, detail=result["detail"])

    data = _parse_json(result["text"])
    body = (data.get("body_markdown") or "").strip()
    title = (data.get("title") or "").strip()
    if not body or not title:
        return DraftResult(False, detail="The model's reply wasn't usable JSON. Try again, "
                                         "or pick a different BACKLINK_MODEL in Settings.")

    article = Article(
        title=title,
        body_markdown=body,
        tags=data.get("tags") or [],
        summary=(data.get("summary") or "").strip(),
        target_url=target.url,
    )
    detail = result["detail"]
    if target.url not in body:
        detail += (" ⚠️ The draft doesn't contain the target link — add it before "
                   "publishing, or regenerate.")
    if not facts:
        detail += " (The target page wouldn't load, so the topic came from its slug.)"
    return DraftResult(True, article=article, detail=detail)


def link_count(article: Article) -> int:
    """How many times the draft actually links to the target page."""
    if not article or not article.target_url:
        return 0
    return article.body_markdown.count(article.target_url)


# ── 3. Publish + record ────────────────────────────────────────────────────
def publish(site, article: Article, platform_key: str,
            as_draft: bool = False) -> PublishResult:
    """
    Publish to one owned platform and log the outcome — success or failure — to
    the tracker. Anything not in `publishers.PLATFORMS` is refused here, which is
    what keeps Lane A from ever touching a third-party site.
    """
    platform = PLATFORMS.get(platform_key)
    if not platform:
        return PublishResult(False, platform_key,
                             detail="Not a platform you own — Lane A only publishes to "
                                    "your own accounts.")

    result = platform.publish(article, site, as_draft)
    tracker.log_result(site.key, article.target_url, result, title=article.title)
    return result
