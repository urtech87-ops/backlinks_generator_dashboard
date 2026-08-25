"""
Analysis agent — the triage everything else is conducted from (Phase 7).

This is the module the Overview page runs. It fetches almost nothing of its
own: coverage comes from the frame the dashboard already loaded, performance
from `core.gsc`, queries from `core.keywords`, and link-eligibility from
`agents.backlink.rank_targets` (the same ranking the Backlinks page uses). What
it adds is the **ordering** — which pages to touch first, and which page of the
dashboard does that job — so Overview can hand a specific URL to the writer or
the backlink targeter instead of just naming a bucket.

Two rules it keeps, both from CLAUDE.md:

  · **No invented numbers.** With no Search Console credentials the report is
    built from coverage alone, `source` says `coverage-only`, and the ordering
    is by bucket rather than by performance. Nothing is filled in with a guess.
  · **Links come last.** Broken URLs, then rejected content, then crawl budget,
    then links. A backlink to a page Google hasn't indexed does nothing, so the
    ordering here is the honest one rather than the one the user wants to hear.
"""

from dataclasses import dataclass, field
import datetime as dt

from agents import backlink as bl
from agents.opportunity import topic_from_url
from core import config, gsc, keywords as kw, openrouter
from core.classifier import PLUMBING, CONTENT, CRAWL_BUDGET, HEALTHY

# ── The five things a page can need ────────────────────────────────────────
FIX = "Fix the URL"
REWRITE = "Rewrite the page"
PRUNE = "Delete or noindex it"
LINK = "Build links to it"
STRENGTHEN = "Strengthen it for a keyword"

KIND_ORDER = [FIX, REWRITE, PRUNE, LINK, STRENGTHEN]
KIND_ICON = {FIX: "🔴", REWRITE: "🟠", PRUNE: "🗑️", LINK: "🟢", STRENGTHEN: "🎯"}

# Which page of the dashboard actually carries the action out, and what the
# button on Overview should say. One source of truth for the hand-offs.
KIND_PAGE = {FIX: "Analysis", REWRITE: "Content", PRUNE: "Analysis",
             LINK: "Backlinks", STRENGTHEN: "Content"}
KIND_CTA = {FIX: "🔧 Fix Plan", REWRITE: "✍️ Rewrite it", PRUNE: "🗑️ Fix Plan",
            LINK: "🔗 Target with links", STRENGTHEN: "✍️ Write for this"}

MAX_PER_KIND = 5          # Overview lists the top few; the full list lives on its page


@dataclass
class Recommendation:
    """One page of yours, what it needs, and the evidence for saying so."""
    kind: str
    url: str
    page: str                       # path only, for display
    bucket: str = ""
    why: str = ""                   # one plain sentence
    evidence: list = field(default_factory=list)
    clicks: int = 0
    impressions: int = 0
    position: float = 0.0
    has_metrics: bool = False
    keyword: str = ""               # for STRENGTHEN, the query it's closest on
    topic: str = ""                 # what the writer would be asked to write about
    notes: str = ""                 # the direction handed to the writer
    score: float = 0.0

    @property
    def icon(self) -> str:
        # A link to an uncrawled page is a rescue, not a compound — the same
        # green/amber split the Backlinks target picker uses.
        if self.kind == LINK and self.bucket == CRAWL_BUDGET:
            return "🟡"
        return KIND_ICON.get(self.kind, "•")

    @property
    def target_page(self) -> str:
        """Where in the dashboard this gets done."""
        return KIND_PAGE.get(self.kind, "Analysis")

    @property
    def cta(self) -> str:
        return KIND_CTA.get(self.kind, "Open")

    @property
    def metrics_line(self) -> str:
        """The numbers behind it, or an honest blank. Never a guess."""
        if not self.has_metrics:
            return "No Search Console figures for this page in this date range."
        pos = f" at position {self.position}" if self.position else ""
        return (f"{self.clicks:,} clicks · {self.impressions:,} impressions{pos} "
                "in this date range.")


@dataclass
class PageStat:
    """
    One page of yours as it actually performs — the row the Overview's winners
    table draws, and the row every one-click action is launched from.

    Everything here is measured or blank. `has_metrics` False means Search
    Console had nothing for this page in this range, and the row says so rather
    than showing a zero that looks like a reading.
    """
    url: str
    page: str                       # path only, for display
    bucket: str = ""
    coverage: str = ""
    clicks: int = 0
    impressions: int = 0
    position: float = 0.0
    ctr: float = 0.0
    has_metrics: bool = False
    keyword: str = ""               # the striking-distance query this page ranks for
    keyword_position: float = 0.0
    keyword_impressions: int = 0

    @property
    def indexed(self) -> bool:
        return self.bucket == HEALTHY

    @property
    def can_link(self) -> bool:
        """Backlinks are only ever offered for pages where a link isn't wasted."""
        return self.bucket in (HEALTHY, CRAWL_BUDGET)

    @property
    def link_note(self) -> str:
        if self.bucket == HEALTHY:
            return "Indexed, so links to this page compound."
        if self.bucket == CRAWL_BUDGET:
            return ("Discovered but never crawled — the one case where a backlink "
                    "actually changes indexing.")
        if self.bucket == PLUMBING:
            return ("Google can't reach this page at all, so a link to it earns "
                    "nothing. Fix the URL first.")
        if self.bucket == CONTENT:
            return ("Google crawled this and refused it on quality. No link overrides "
                    "that — it needs rewriting first.")
        return "Not a link target: this page isn't one Google will rank."

    @property
    def needs_fix(self) -> bool:
        return self.bucket in (PLUMBING, CONTENT)

    @property
    def status_state(self) -> str:
        return {HEALTHY: "ok", CRAWL_BUDGET: "warn",
                PLUMBING: "bad", CONTENT: "bad"}.get(self.bucket, "idle")

    @property
    def status_label(self) -> str:
        return {HEALTHY: "indexed", CRAWL_BUDGET: "not crawled yet",
                PLUMBING: "broken URL", CONTENT: "refused on quality"}.get(
                    self.bucket, self.bucket.lower() or "unknown")

    @property
    def metrics_line(self) -> str:
        if not self.has_metrics:
            return "No Search Console figures for this page in this date range."
        pos = f" · average position {self.position}" if self.position else ""
        return (f"{self.impressions:,} impressions · {self.clicks:,} clicks{pos} "
                "in this date range.")

    @property
    def topic(self) -> str:
        """What the writer would be asked to write about. "" = not an article."""
        return self.keyword or topic_from_url(self.url)

    @property
    def write_note(self) -> str:
        """The direction handed to the writer, matched to what this page is."""
        if self.bucket == CONTENT:
            return (f"This rewrites an existing page: {self.url}. Google crawled it and "
                    "refused to index it on quality, so it needs real use-cases, one "
                    "worked example and an FAQ — not more of the same.")
        if self.keyword:
            return (f"Strengthen {self.url} for the query \u201c{self.keyword}\u201d, which "
                    f"already earns {self.keyword_impressions:,} impressions at position "
                    f"{self.keyword_position}.")
        if self.has_metrics and self.impressions:
            return (f"A supporting article for {self.url}, which already earns "
                    f"{self.impressions:,} impressions"
                    + (f" at position {self.position}" if self.position else "")
                    + ". Link to it from the new piece.")
        return f"A supporting article that links to {self.url}."


@dataclass
class Step:
    """One line of the ordered 'what to do next' list."""
    icon: str
    title: str
    detail: str
    page: str                       # sidebar page that does it
    cta: str
    kind: str = ""                  # which recommendations belong under it
    bucket: str = ""                # narrow those to one bucket, when it matters
    count: int = 0


@dataclass
class Report:
    """Everything the Overview page draws, produced in one run."""
    site_key: str = ""
    health: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    pages: list = field(default_factory=list)      # PageStat, best-performing first
    performance: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    source: str = "coverage-only"   # live | coverage-only
    coverage_source: str = "seed"   # live | seed — passed through from the caller
    range: str = ""
    generated_at: str = ""
    ok: bool = True
    detail: str = ""

    def of_kind(self, kind: str) -> list:
        return [r for r in self.recommendations if r.kind == kind]

    def for_step(self, step: "Step") -> list:
        """
        The pages behind one step. Both link steps share a kind, so the bucket
        is what keeps "rescue these" and "compound these" as separate lists.
        """
        if not step.kind:
            return []
        return [r for r in self.of_kind(step.kind)
                if not step.bucket or r.bucket == step.bucket]


# ── Indexing health ────────────────────────────────────────────────────────
def health(coverage_df) -> dict:
    """
    The headline indexing numbers. One implementation, used by Overview, the
    Analysis page and this agent, so the three can never disagree.
    """
    total = 0 if coverage_df is None else len(coverage_df)
    if not total:
        return {"total": 0, "healthy": 0, "problems": 0, "pct": 0, "counts": {}}
    healthy = int((coverage_df["Bucket"] == HEALTHY).sum())
    return {
        "total": total,
        "healthy": healthy,
        "problems": total - healthy,
        "pct": round(healthy / total * 100),
        "counts": coverage_df["Bucket"].value_counts().to_dict(),
    }


# ── Performance, read once and shared ──────────────────────────────────────
def page_metrics(site, start: str, end: str) -> dict:
    """
    {url without trailing slash: Search Analytics row}. Empty without
    credentials — which is a state, not a failure.
    """
    if not (start and end and config.credentials_available()):
        return {}
    out = {}
    for row in gsc.search_analytics(site.gsc_property, start, end, ["page"],
                                    row_limit=500):
        url = (row.get("page") or "").rstrip("/")
        if url:
            out[url] = row
    return out


def _performance_summary(metrics: dict, keywords: list) -> dict:
    """Site-wide totals from rows we actually fetched. No metrics → empty dict."""
    if not metrics:
        return {}
    clicks = sum(int(r.get("clicks", 0) or 0) for r in metrics.values())
    impressions = sum(int(r.get("impressions", 0) or 0) for r in metrics.values())
    positions = [float(r.get("position", 0) or 0) for r in metrics.values()
                 if r.get("position")]
    return {
        "clicks": clicks,
        "impressions": impressions,
        "pages": len(metrics),
        "avg_position": round(sum(positions) / len(positions), 1) if positions else 0.0,
        "queries": len(keywords),
    }


def _row_metrics(metrics: dict, url: str) -> dict:
    return metrics.get(url.rstrip("/"), {})


# ── The winners table — which of your pages actually earn something ────────
MAX_PAGES = 12          # how many rows the Overview's winners table draws


def _keyword_for_page(url: str, keywords: list):
    """
    The best striking-distance query this exact page ranks for, or None. It's
    what turns "this page does well" into "this page is one push from page one
    on *this* search", which is what the writer needs to be handed.
    """
    target = url.rstrip("/")
    best = None
    for keyword in kw.striking_distance(keywords or []):
        if (keyword.page or "").rstrip("/") != target:
            continue
        if best is None or keyword.impressions > best.impressions:
            best = keyword
    return best


def ranked_pages(coverage_df, metrics: dict, keywords: list = None,
                 limit: int = MAX_PAGES) -> list:
    """
    Your pages, best-performing first — the list the Overview is built around.

    With Search Console figures this is a real ranking on impressions. Without
    them there is nothing to rank on, so it returns the pages Google has
    accepted or discovered, in coverage order, every row flagged `has_metrics
    = False`. It never fills a blank with a zero that reads like a measurement.
    """
    if coverage_df is None or coverage_df.empty:
        return []

    rows = []
    for _, row in coverage_df.iterrows():
        m = _row_metrics(metrics, row["URL"])
        stat = PageStat(
            url=row["URL"], page=row["Page"], bucket=row["Bucket"],
            coverage=row["Coverage"],
            clicks=int(m.get("clicks", 0) or 0),
            impressions=int(m.get("impressions", 0) or 0),
            position=float(m.get("position", 0) or 0),
            ctr=float(m.get("ctr", 0) or 0),
            has_metrics=bool(m),
        )
        match = _keyword_for_page(stat.url, keywords)
        if match:
            stat.keyword = match.keyword
            stat.keyword_position = match.position
            stat.keyword_impressions = match.impressions
        rows.append(stat)

    if metrics:
        # A real ranking: what earns impressions, most first. Pages Search
        # Console said nothing about sink to the bottom rather than tying at 0.
        earning = [r for r in rows if r.has_metrics]
        earning.sort(key=lambda r: (-r.impressions, -r.clicks, r.page))
        rest = [r for r in rows if not r.has_metrics and r.can_link]
        rest.sort(key=lambda r: r.page)
        return (earning + rest)[:limit]

    # No performance data at all — offer the link-eligible pages, unranked.
    eligible = [r for r in rows if r.can_link]
    eligible.sort(key=lambda r: (r.bucket != HEALTHY, r.page))
    return eligible[:limit]


# ── The recommendation builders ────────────────────────────────────────────
def _fix_recommendations(coverage_df, metrics: dict) -> list:
    """Broken URLs, worst first. The classifier already wrote the action."""
    out = []
    rows = coverage_df[coverage_df["Bucket"] == PLUMBING]
    flag_counts = {}
    for _, row in rows.iterrows():
        for flag in _flags(row):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    for _, row in rows.iterrows():
        m = _row_metrics(metrics, row["URL"])
        flags = _flags(row)
        evidence = [f"Search Console says: **{row['Coverage']}**.", row["Action"]]
        if "relative-link-bug" in flags and flag_counts.get("relative-link-bug", 0) > 1:
            evidence.append(
                f"{flag_counts['relative-link-bug']} pages share this relative-link bug — "
                "fixing the template link once should clear them together.")
        if "wp-junk" in flags:
            evidence.append("This is a WordPress default page. Deleting or noindexing it "
                            "is a fix too — not everything is worth restoring.")
        out.append(Recommendation(
            kind=FIX, url=row["URL"], page=row["Page"], bucket=PLUMBING,
            why="Google can't reach this page at all, so no content or link can help it.",
            evidence=evidence,
            clicks=int(m.get("clicks", 0) or 0),
            impressions=int(m.get("impressions", 0) or 0),
            position=float(m.get("position", 0) or 0),
            has_metrics=bool(m),
            score=100 + int(m.get("impressions", 0) or 0),
        ))
    out.sort(key=lambda r: (-r.score, r.page))
    return out


def _rewrite_recommendations(coverage_df, metrics: dict, keywords: list) -> list:
    """
    Pages Google crawled and declined on quality — the writer's job, not the
    linker's. Except the ones that aren't articles at all: a feed, an author
    archive or a category page doesn't need a rewrite, it needs deleting or a
    noindex, so those come back as PRUNE and never reach the writer.
    """
    out = []
    for _, row in coverage_df[coverage_df["Bucket"] == CONTENT].iterrows():
        m = _row_metrics(metrics, row["URL"])
        topic = topic_from_url(row["URL"])
        if not topic:
            out.append(_prune_recommendation(row, m))
            continue
        match = _closest_keyword(topic, keywords)
        evidence = [f"Search Console says: **{row['Coverage']}**.", row["Action"]]
        if match:
            evidence.append(f"You already get impressions for “{match.keyword}” "
                            f"({match.impressions:,} impressions) — write to that.")
        if "stuffed-slug" in _flags(row):
            evidence.append("The slug is keyword-stuffed, which is a low-quality signal "
                            "on its own. Shorten it and 301 the old URL.")
        out.append(Recommendation(
            kind=REWRITE, url=row["URL"], page=row["Page"], bucket=CONTENT,
            why="Google crawled this and declined to index it on quality. Only a real "
                "rewrite changes that verdict.",
            evidence=evidence,
            clicks=int(m.get("clicks", 0) or 0),
            impressions=int(m.get("impressions", 0) or 0),
            position=float(m.get("position", 0) or 0),
            has_metrics=bool(m),
            keyword=match.keyword if match else "",
            topic=topic,
            notes=(f"This rewrites an existing page: {row['URL']}. Google crawled it and "
                   "declined to index it on quality, so it needs real use-cases, one "
                   "worked example and an FAQ — not more of the same."),
            score=50 + int(m.get("impressions", 0) or 0),
        ))
    out.sort(key=lambda r: (-r.score, r.page))
    return out


def _prune_recommendation(row, m: dict) -> Recommendation:
    """A rejected page that was never an article. Rewriting it would be wasted work."""
    return Recommendation(
        kind=PRUNE, url=row["URL"], page=row["Page"], bucket=CONTENT,
        why="This isn't an article — it's a WordPress archive, author or feed page. "
            "It doesn't need writing, it needs taking out of the way.",
        # Deliberately not the classifier's action here: it says "rewrite", which
        # is exactly the advice this page should not be given.
        evidence=[f"Search Console says: **{row['Coverage']}**.",
                  "Delete it or set noindex, and drop it from the sitemap. Pages like "
                  "this spend crawl budget that your real pages need."],
        clicks=int(m.get("clicks", 0) or 0),
        impressions=int(m.get("impressions", 0) or 0),
        position=float(m.get("position", 0) or 0),
        has_metrics=bool(m),
        score=40 + int(m.get("impressions", 0) or 0),
    )


def _link_recommendations(site, coverage_df, start: str, end: str,
                          metrics: dict) -> list:
    """
    Pages worth a link, straight from the Backlinks page's own ranking — so the
    order Overview shows is the order the targeter will show.
    """
    targets, _ = bl.rank_targets(site, coverage_df, start, end, metrics=metrics)
    out = []
    for target in targets:
        evidence = [target.reason]
        if target.bucket == CRAWL_BUDGET:
            evidence.append("This is the one bucket where a backlink genuinely changes "
                            "indexing rather than just ranking.")
        out.append(Recommendation(
            kind=LINK, url=target.url, page=target.page, bucket=target.bucket,
            why=("A link here rescues a page Google has never crawled."
                 if target.bucket == CRAWL_BUDGET
                 else "This page is indexed, so links to it compound."),
            evidence=evidence,
            clicks=target.clicks, impressions=target.impressions,
            position=target.position, has_metrics=target.has_metrics,
            score=target.score,
        ))
    return out


def _strengthen_recommendations(keywords: list, coverage_df) -> list:
    """
    Striking-distance queries: a page of yours already ranks 5th-20th on real
    impressions. Strengthening that page beats starting a new article.
    """
    out = []
    known = set()
    if coverage_df is not None and not coverage_df.empty:
        known = {u.rstrip("/") for u in coverage_df["URL"]}

    for keyword in kw.striking_distance(keywords)[:MAX_PER_KIND * 2]:
        page = keyword.page or ""
        display = page.rstrip("/").split("/")[-1] or "/"
        out.append(Recommendation(
            kind=STRENGTHEN, url=page, page=f"/{display}" if page else "",
            bucket=HEALTHY if page.rstrip("/") in known else "",
            why=f"“{keyword.keyword}” sits at position {keyword.position} on "
                f"{keyword.impressions:,} impressions — one push from page one.",
            evidence=[keyword.reason] if keyword.reason else [],
            clicks=keyword.clicks, impressions=keyword.impressions,
            position=keyword.position, has_metrics=True,
            keyword=keyword.keyword,
            topic=keyword.keyword,
            notes=(f"Target the query “{keyword.keyword}”, which already earns "
                   f"{keyword.impressions:,} impressions at position "
                   f"{keyword.position}."
                   + (f" Strengthen the page that already ranks: {page}." if page else
                      " No page of yours ranks for it yet, so this is a new article.")),
            score=keyword.score,
        ))
    return out


def _flags(row) -> list:
    return [f.strip() for f in str(row.get("Flags", "") or "").split(",") if f.strip()]


def _closest_keyword(topic: str, keywords: list, floor: float = 0.3):
    """The real query closest to a topic, or None. Never invents one."""
    best, best_rel = None, floor
    for keyword in keywords or []:
        rel = kw.overlap(topic, keyword.keyword)
        if rel > best_rel:
            best, best_rel = keyword, rel
    return best


# ── The ordered to-do list ─────────────────────────────────────────────────
def _count(n: int, singular: str, plural: str = "") -> str:
    """'1 broken URL' / '30 broken URLs' — the list reads like a person wrote it."""
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def _steps(counts: dict, recommendations: list) -> list:
    """
    Turn the bucket counts into the short, ordered list Overview draws. The
    order is the honest one: plumbing → rewrites → crawl budget → links.
    """
    per_kind = {}
    for rec in recommendations:
        per_kind[rec.kind] = per_kind.get(rec.kind, 0) + 1

    steps = []
    if counts.get(PLUMBING):
        steps.append(Step(
            "🔴", f"Fix {_count(counts[PLUMBING], 'broken URL')}",
            "Redirect errors and 404s. Google can't reach these at all, so no amount "
            "of content or links will help until they resolve. Cheapest win on the list.",
            "Analysis", "Fix Plan", FIX, PLUMBING, counts[PLUMBING]))
    if per_kind.get(REWRITE):
        steps.append(Step(
            "🟠", f"Rewrite {_count(per_kind[REWRITE], 'rejected page')}",
            "Google crawled these and declined to index them on quality. They need real "
            "use-cases, a worked example and an FAQ — not more links.",
            "Content", "Write", REWRITE, "", per_kind[REWRITE]))
    if per_kind.get(PRUNE):
        steps.append(Step(
            "🗑️", f"Clear {_count(per_kind[PRUNE], 'archive or feed page')}",
            "Rejected too, but these were never articles — author archives, category "
            "pages, the RSS feed. Delete them or set noindex and drop them from the "
            "sitemap, so crawl budget goes to pages that can earn something.",
            "Analysis", "Fix Plan", PRUNE, "", per_kind[PRUNE]))
    if counts.get(CRAWL_BUDGET):
        steps.append(Step(
            "🟡", f"Get {_count(counts[CRAWL_BUDGET], 'page')} crawled",
            "Discovered but never crawled. Internal links from strong pages, plus a "
            "couple of genuine backlinks. This is the one bucket where link-building "
            "actually moves the needle.",
            "Backlinks", "Backlinks", LINK, CRAWL_BUDGET, counts[CRAWL_BUDGET]))
    if counts.get(HEALTHY):
        steps.append(Step(
            "🟢", f"Build links to {_count(counts[HEALTHY], 'healthy page')}",
            "These are indexed, so links to them compound. Auto-publish to platforms "
            "you own; pitch guest posts by hand.",
            "Backlinks", "Backlinks", LINK, HEALTHY, counts[HEALTHY]))
    if per_kind.get(STRENGTHEN):
        steps.append(Step(
            "🎯", f"Push {_count(per_kind[STRENGTHEN], 'striking-distance query', 'striking-distance queries')} onto page one",
            "Pages of yours already ranking 5th-20th on real impressions. Strengthening "
            "a page that nearly ranks is the fastest traffic you own.",
            "Content", "Write", STRENGTHEN, "", per_kind[STRENGTHEN]))
    steps.append(Step(
        "💡", "Decide what to write next",
        "The Opportunity Finder compares your coverage with your competitors' and with "
        "the queries you already rank for, then hands the topic straight to the writer.",
        "Opportunities", "Opportunities", "", "", 0))
    return steps


# ── The run ────────────────────────────────────────────────────────────────
def run(site, coverage_df, start: str = "", end: str = "", live: bool = True,
        use_keywords: bool = True, coverage_source: str = "seed",
        progress=None) -> Report:
    """
    The whole analysis, in one call. Never raises: every source that isn't
    available leaves a note and the rest of the report is still built.

    `live=False` skips the network entirely, which is what the page uses for its
    first paint — the ordering from coverage alone is still useful.
    """
    def step(fraction: float, message: str) -> None:
        if progress:
            progress(min(fraction, 1.0), message)

    report = Report(
        site_key=site.key,
        coverage_source=coverage_source,
        range=f"{start} → {end}" if start and end else "",
        generated_at=dt.datetime.now().isoformat(timespec="seconds"),
    )

    if coverage_df is None or coverage_df.empty:
        report.ok = False
        report.detail = ("No coverage data for this site yet, so there's nothing to "
                         "triage. Add the Google service-account file in Settings and "
                         "press Refresh live data.")
        report.steps = _steps({}, [])
        report.health = health(coverage_df)
        return report

    report.health = health(coverage_df)
    counts = report.health["counts"]

    # ── Performance, fetched once and shared with every builder below ──────
    metrics = {}
    if live:
        step(0.15, "Reading Search Console performance…")
        metrics = page_metrics(site, start, end)
        if not metrics:
            report.notes.append(
                "No Search Console performance figures for this range, so pages are "
                "ordered by what needs doing rather than by traffic. That ordering is "
                "unvalidated — connect Search Console in Settings to rank on real "
                "impressions."
                if config.credentials_available() else
                "No Google service-account file, so there are no performance figures. "
                "Everything below is read from your coverage snapshot alone.")
    report.source = "live" if metrics else "coverage-only"

    # ── Your real queries (only when the keyword engine is on) ─────────────
    if live and use_keywords and kw.enabled():
        step(0.4, "Reading the queries you already rank for…")
        found = kw.gsc_keywords(site, start, end) if (start and end) else {
            "ok": False, "keywords": [], "detail": "No date range selected."}
        report.keywords = found["keywords"]
        if not found["ok"]:
            report.notes.append(found["detail"])
    elif not kw.enabled():
        report.notes.append("The keyword engine is off, so this report has no "
                            "striking-distance section. Turn it on in Settings → "
                            "Content tools.")

    # ── Build the recommendations ─────────────────────────────────────────
    step(0.7, "Sorting your pages into what each one needs…")
    recommendations = []
    recommendations += _fix_recommendations(coverage_df, metrics)
    recommendations += _rewrite_recommendations(coverage_df, metrics, report.keywords)
    recommendations += _link_recommendations(site, coverage_df, start, end, metrics)
    recommendations += _strengthen_recommendations(report.keywords, coverage_df)
    report.recommendations = recommendations

    report.pages = ranked_pages(coverage_df, metrics, report.keywords)
    report.performance = _performance_summary(metrics, report.keywords)
    report.steps = _steps(counts, recommendations)

    step(1.0, "Done.")
    report.ok = True
    report.detail = _detail(report)
    return report


def _detail(report: Report) -> str:
    """One line summarising what the run found — shown under the button."""
    h = report.health
    parts = [f"{h['healthy']} of {h['total']} pages indexed ({h['pct']}%)"]
    per_kind = {k: len(report.of_kind(k)) for k in KIND_ORDER}
    if per_kind[FIX]:
        parts.append(f"{per_kind[FIX]} to fix")
    if per_kind[REWRITE]:
        parts.append(f"{per_kind[REWRITE]} to rewrite")
    if per_kind[PRUNE]:
        parts.append(f"{per_kind[PRUNE]} to clear out")
    if per_kind[LINK]:
        parts.append(f"{per_kind[LINK]} worth linking to")
    if per_kind[STRENGTHEN]:
        parts.append(f"{per_kind[STRENGTHEN]} striking-distance queries")
    return " · ".join(parts) + "."


# ── The optional written briefing ──────────────────────────────────────────
_SYSTEM = (
    "You are an SEO analyst writing a short status note for the site's owner. "
    "You are given a set of measured facts. Use ONLY those numbers. Never invent a "
    "statistic, a keyword volume, a competitor or a date. If something isn't in the "
    "facts, say it isn't known. Plain English, no jargon, no bullet lists, no "
    "headings — three or four sentences, at most 120 words. Say what the numbers "
    "mean and what to do first. Do not promise results."
)


def facts_block(report: Report, site) -> str:
    """The only thing the briefing model is allowed to work from."""
    h = report.health
    lines = [
        f"Site: {site.label} ({site.homepage})",
        f"Date range: {report.range or 'not set'}",
        f"Coverage data source: {report.coverage_source} "
        f"({'live Search Console' if report.coverage_source == 'live' else 'saved snapshot'})",
        f"Pages tracked: {h.get('total', 0)}",
        f"Pages indexed: {h.get('healthy', 0)} ({h.get('pct', 0)}%)",
    ]
    for bucket, count in (h.get("counts") or {}).items():
        lines.append(f"Pages in bucket '{bucket}': {count}")
    if report.performance:
        p = report.performance
        lines.append(f"Clicks in range: {p['clicks']}")
        lines.append(f"Impressions in range: {p['impressions']}")
        lines.append(f"Pages with impressions: {p['pages']}")
        lines.append(f"Average position across those pages: {p['avg_position']}")
        lines.append(f"Distinct queries with impressions: {p['queries']}")
    else:
        lines.append("Performance figures: NOT AVAILABLE (no Search Console data). "
                     "Do not estimate traffic.")
    for rec in report.of_kind(STRENGTHEN)[:5]:
        lines.append(f"Striking-distance query: '{rec.keyword}' at position "
                     f"{rec.position} with {rec.impressions} impressions")
    for step in report.steps:
        lines.append(f"Recommended step: {step.title}")
    return "\n".join(lines)


def briefing(report: Report, site) -> dict:
    """
    A plain-English paragraph over the numbers above, written by ANALYSIS_MODEL
    (the cheap one — this is summarising, not writing). Optional in every sense:
    with no key it returns a plain refusal and the page shows the deterministic
    list on its own, which is the authority either way.
    """
    result = openrouter.chat(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": "Measured facts:\n" + facts_block(report, site)
          + "\n\nWrite the status note."}],
        model=config.get("ANALYSIS_MODEL"),
        temperature=0.3, max_tokens=400,
    )
    return {"ok": result["ok"], "text": result.get("text", ""),
            "detail": result["detail"]}
