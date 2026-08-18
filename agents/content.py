"""
The Content + SEO agent — the volume path (Phase 5).

The *quality* path already exists as the skills in `.claude/skills/`: you run it
in Claude Code, it researches deeply and produces a piece meant to rank. This is
the fast path that lives inside the dashboard — a topic in, a WordPress draft
out — held to the same rules as the writer skill so the two can't drift apart:

  research()      real web research through the same pluggable search adapter
                  Lane B prospects with. Every stat the article uses has to come
                  from something found here.
  write()         one OpenRouter call on CONTENT_MODEL that returns the article
                  *and* its meta.json (title, meta title/description, slug,
                  tags, categories, FAQ, schema, sources, internal links).
  check()         the writer skill's rules, enforced in code rather than hoped
                  for: answer-first opening, question-shaped headings, FAQ,
                  short slug, meta lengths, internal links, and — the important
                  one — every cited source URL traced back to the research.
  make_images()   the existing pluggable image adapter (briefs when no API).
  save_run()      the orchestrator's `outputs/<slug>/` layout, so a run is
                  auditable and the standalone publisher skill can also read it.
  publish_draft() the existing WordPress publisher. Status is hard-coded to
                  draft in there and stays that way.

Guardrails (CLAUDE.md): nothing is invented — the prompt bans made-up statistics,
volumes and quotes, and `check()` names any source the research never returned.
WordPress is always a draft. No image API is not an error.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from core import config, images, openrouter, search
from core.classifier import HEALTHY
from publishers import wordpress
from publishers.base import Article, PublishResult

from .backlink import _parse_json, page_facts        # reuse, don't re-solve

OUTPUT_ROOT = config.ROOT / "outputs"

# How the research step searches. `{topic}` is filled in; the second and third
# exist to surface pages that actually carry figures and sources.
RESEARCH_QUERIES = [
    "{topic}",
    "{topic} statistics",
    "{topic} report data study",
    "how to {topic}",
]

MAX_SOURCES = 14
SNIPPET_CHARS = 400


@dataclass
class Research:
    """What the web actually gave us. Empty is allowed — it just limits claims."""
    topic: str
    sources: list = field(default_factory=list)     # [{title, url, snippet}]
    questions: list = field(default_factory=list)   # question-shaped result titles
    ok: bool = True
    detail: str = ""

    @property
    def urls(self) -> set:
        return {s["url"] for s in self.sources}


@dataclass
class Draft:
    """One finished article plus its meta.json payload and image specs."""
    topic: str
    title: str
    body_markdown: str
    meta: dict = field(default_factory=dict)
    image_specs: list = field(default_factory=list)  # [{role, prompt, alt, filename}]
    detail: str = ""

    @property
    def slug(self) -> str:
        return (self.meta.get("slug") or slugify(self.title))[:80]


@dataclass
class WriteResult:
    ok: bool
    draft: Draft = None
    detail: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────
def slugify(text: str, words: int = 5) -> str:
    """Short, clean, hyphenated — the writer skill's slug rule, in code."""
    cleaned = re.sub(r"[^a-z0-9\s-]", "", (text or "").lower())
    parts = [p for p in re.split(r"[\s-]+", cleaned) if p]
    return "-".join(parts[:words]) or "untitled"


def _domain(url: str) -> str:
    return re.sub(r"^www\.", "", re.sub(r"https?://([^/]+).*", r"\1", url or "").lower())


def internal_link_options(coverage_df, site, limit: int = 30) -> list:
    """
    Real pages on the user's own site an article may link to, taken from the
    shared coverage frame. Only indexed (Healthy) pages are offered: linking a
    new article to a page Google has rejected spreads the problem rather than
    fixing it, and the Fix Plan is where those belong.
    """
    if coverage_df is None or getattr(coverage_df, "empty", True):
        return []
    healthy = coverage_df[coverage_df["Bucket"] == HEALTHY]
    return [{"url": row["URL"], "page": row["Page"]}
            for _, row in healthy.head(limit).iterrows()]


# ── 1. Research ────────────────────────────────────────────────────────────
def research(topic: str, site=None, per_query: int = 8,
             max_sources: int = MAX_SOURCES) -> Research:
    """
    Search the web for what's actually been written about `topic`.

    Uses `core.search`, so it honours the provider chosen in Settings and needs
    no key on the default one. Failure is not fatal: the article can still be
    written, it just has to stay qualitative — `check()` and the UI both say so.
    """
    topic = (topic or "").strip()
    if not topic:
        return Research(topic, ok=False, detail="No topic given.")

    own = _domain(site.homepage) if site else ""
    seen, sources, questions, failures = set(), [], [], []

    for template in RESEARCH_QUERIES:
        if len(sources) >= max_sources:
            break
        result = search.search(template.format(topic=topic), limit=per_query)
        if not result["ok"]:
            failures.append(result["detail"])
            continue
        for hit in result["results"]:
            url = (hit.url or "").strip()
            key = url.rstrip("/")
            if not url.startswith("http") or key in seen:
                continue
            if own and _domain(url) == own:
                continue                    # your own pages are internal links, not sources
            seen.add(key)
            sources.append({"title": hit.title, "url": url,
                            "snippet": (hit.snippet or "")[:SNIPPET_CHARS]})
            title = (hit.title or "").strip()
            if title.endswith("?") and title not in questions:
                questions.append(title)
            if len(sources) >= max_sources:
                break

    if not sources:
        detail = failures[0] if failures else (
            "The search returned nothing usable for this topic. Try wording it the way "
            "someone would search for it.")
        return Research(topic, ok=False, detail=detail)

    detail = f"{len(sources)} sources found via {search.PROVIDERS[search.provider()]}."
    if failures:
        detail += f" Some searches failed: {failures[0]}"
    return Research(topic, sources=sources, questions=questions, detail=detail)


# ── 2. Write ───────────────────────────────────────────────────────────────
_SYSTEM = (
    "You are a careful SEO/AEO/GEO writer. You write for humans first and for "
    "answer engines second: answer-first openings, question-shaped headings, "
    "self-contained answer blocks. You are strictly factual — you never invent "
    "statistics, search volumes, benchmarks, study results, dates, prices or "
    "quotes, and you never attribute a figure to a source that does not carry "
    "it. If you cannot support a number from the research you are given, you "
    "make the point qualitatively instead. You never pad and never use AI "
    "filler openings. You return only JSON when asked for JSON."
)


def _sources_block(res: Research) -> str:
    if not res.sources:
        return ("NO RESEARCH WAS AVAILABLE for this topic. You therefore may not state a "
                "single statistic, percentage, price, date or study result, and `sources` "
                "must be an empty list. Write the piece qualitatively — it can still be "
                "genuinely useful. Where a figure would help, say plainly that the number "
                "is unvalidated rather than inventing one.")
    lines = ["RESEARCH — these are the ONLY sources you may cite. Use a figure only if it "
             "appears in the snippet below, and cite it with that exact URL:"]
    for i, s in enumerate(res.sources, 1):
        lines.append(f"{i}. {s['title']}\n   URL: {s['url']}\n   Snippet: {s['snippet']}")
    if res.questions:
        lines.append("\nQuestions real pages are answering (good FAQ candidates):")
        lines.extend(f"- {q}" for q in res.questions[:8])
    return "\n".join(lines)


def _internal_block(site, links: list, brand: dict) -> str:
    if not links:
        return (f"The article is for {site.label} ({site.homepage}). No internal link "
                f"targets were supplied, so link only to {site.homepage} once, naturally, "
                "and leave `internal_links` otherwise empty. Do not invent URLs on this "
                "domain — a link to a page that does not exist is a 404.")
    described = "\n".join(f"- {l['url']}  ({l.get('page', '')})" for l in links[:20])
    brand_line = ""
    if brand.get("title") or brand.get("description"):
        brand_line = (f"\nWhat the site says it is: {brand.get('title', '')} — "
                      f"{brand.get('description', '')}")
    return (f"The article is for {site.label} ({site.homepage}).{brand_line}\n"
            f"Link to two or three of these REAL pages, only where they are the genuinely "
            f"useful next step, with varied descriptive anchor text (never 'click here', "
            f"never the bare URL). Do not invent any other URL on this domain:\n{described}")


def _prompt(topic: str, site, res: Research, links: list, brand: dict,
            keyword: str, notes: str) -> str:
    today = dt.date.today().isoformat()
    return f"""Write one complete article on this topic:

TOPIC: {topic}
{f"PRIMARY KEYWORD (use it naturally in the H1, meta title and opening): {keyword}" if keyword.strip() else "PRIMARY KEYWORD: choose the phrase a person would actually search for this."}

{_internal_block(site, links, brand)}

{_sources_block(res)}

HOW TO WRITE IT
1. Answer-first opening of 120-200 words that COMPLETELY answers the main question.
   A reader — or an AI engine quoting you — should get the whole answer from it.
   Do not warm up, do not restate the title, no "in today's fast-paced world".
2. Question-shaped H2/H3 headings, phrased the way people ask them. Under each,
   open with a self-contained 40-60 word answer block that still makes sense if an
   engine lifts it out on its own, then expand.
3. One worked, concrete example with realistic numbers, clearly framed as an example
   rather than as measured data.
4. Cite sources inline as markdown links, on the claims that need them.
5. A short FAQ of 3-6 real questions, each answered in 2-4 tight sentences.
6. Name {site.label} consistently and describe what it is in one clean sentence
   somewhere natural. Finish with a short conclusion and one clear call to action.
7. 1,200-1,800 words. If the topic is fully answered in less, stop — padding hurts.
   Vary sentence length. Write like a knowledgeable person, not a template.

HARD RULES
- Invent nothing: no statistic, percentage, price, ranking, study, search volume or
  quote that is not in the research above. No fabricated sources, no plausible-looking
  URLs. If it is not in the research, say it qualitatively or leave it out.
- The slug must be 3-5 words, hyphenated, lowercase, no keyword stuffing.
- No keyword stuffing anywhere. Fluent, substantive language only.
{f"- Extra direction from the user: {notes.strip()}" if notes.strip() else ""}

RETURN
Only a JSON object, no code fence, with exactly these keys:
{{"title": "the H1",
  "meta_title": "60 characters or fewer, keyword near the front",
  "meta_description": "155 characters or fewer, answers the query and invites the click",
  "slug": "three-to-five-words",
  "primary_keyword": "...",
  "tags": ["up to 5 short tags"],
  "categories": ["one or two real categories"],
  "faq": [{{"q": "...", "a": "..."}}],
  "schema": ["Article", "FAQPage"],
  "sources": [{{"claim": "the claim this supports", "url": "the exact research URL"}}],
  "internal_links": [{{"anchor": "the anchor text used", "url": "..."}}],
  "date_modified": "{today}",
  "body_markdown": "the full article in markdown, starting at the opening paragraph — no H1, the title is separate. Include the FAQ as a '## Frequently asked questions' section.",
  "images": [
    {{"role": "featured", "filename": "keyword-slug-featured.png",
      "prompt": "a clean, modern, uncluttered illustration brief — no text baked in, no fake charts, no real logos or people",
      "alt": "8-15 words describing what is actually in the image"}},
    {{"role": "inline", "filename": "keyword-slug-inline-1.png",
      "prompt": "...", "alt": "..."}}
  ]}}"""


def write(topic: str, site, res: Research = None, internal_links: list = None,
          keyword: str = "", notes: str = "", brand: dict = None) -> WriteResult:
    """
    Write the article with CONTENT_MODEL. Never raises — a failure comes back as
    `ok=False` with a plain-language reason for the UI.
    """
    topic = (topic or "").strip()
    if not topic:
        return WriteResult(False, detail="Give the agent a topic first.")

    res = res or Research(topic, ok=False, detail="No research was run.")
    if brand is None:
        brand = page_facts(site.homepage) if site else {}

    result = openrouter.chat(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": _prompt(topic, site, res, internal_links or [],
                                             brand, keyword, notes)}],
        model=config.get("CONTENT_MODEL"),
        temperature=0.6,
        max_tokens=8000,
        timeout=300,
    )
    if not result["ok"]:
        return WriteResult(False, detail=result["detail"])

    data = _parse_json(result["text"])
    body = (data.get("body_markdown") or "").strip()
    title = (data.get("title") or "").strip()
    if not body or not title:
        return WriteResult(False, detail="The model's reply wasn't usable JSON. Try again, "
                                         "or pick a different Content model in Settings.")

    meta = {
        "title": title,
        "meta_title": (data.get("meta_title") or title).strip(),
        "meta_description": (data.get("meta_description") or "").strip(),
        "slug": slugify(data.get("slug") or title),
        "primary_keyword": (data.get("primary_keyword") or keyword).strip(),
        "tags": [str(t).strip() for t in (data.get("tags") or []) if str(t).strip()][:5],
        "categories": [str(c).strip() for c in (data.get("categories") or [])
                       if str(c).strip()][:2],
        "faq": [f for f in (data.get("faq") or []) if isinstance(f, dict) and f.get("q")],
        "schema": data.get("schema") or ["Article", "FAQPage"],
        "sources": [s for s in (data.get("sources") or [])
                    if isinstance(s, dict) and s.get("url")],
        "internal_links": [l for l in (data.get("internal_links") or [])
                           if isinstance(l, dict) and l.get("url")],
        "date_modified": data.get("date_modified") or dt.date.today().isoformat(),
    }
    specs = [s for s in (data.get("images") or []) if isinstance(s, dict) and s.get("prompt")]

    detail = result["detail"]
    if not res.sources:
        detail += (" No research was available, so the piece is deliberately qualitative — "
                   "any figure in it is unvalidated.")
    return WriteResult(True, draft=Draft(topic=topic, title=title, body_markdown=body,
                                         meta=meta, image_specs=specs, detail=detail),
                       detail=detail)


# ── 3. Check it against the writer skill's rules ───────────────────────────
_HEADING = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_NUMBER = re.compile(r"(?<![\w-])(\d[\d,.]*\s?%|\$\s?\d[\d,.]*|\b\d{1,3}(?:,\d{3})+\b|"
                     r"\b\d+(?:\.\d+)?\s?(?:x|times|million|billion|percent)\b)",
                     re.IGNORECASE)


def _row(name: str, state: str, detail: str) -> dict:
    return {"name": name, "state": state, "detail": detail}


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def check(draft: Draft, res: Research = None, site=None) -> list:
    """
    The writer skill's non-negotiables, checked against what the model actually
    produced. Returns [{'name', 'state': ok|warn|bad, 'detail'}] — the UI shows
    every row, so a weak draft is visible before it becomes a draft post.
    """
    body, meta = draft.body_markdown, draft.meta
    rows = []

    # Answer-first opening
    first = next((p.strip() for p in body.split("\n\n")
                  if p.strip() and not p.strip().startswith("#")), "")
    opening = word_count(first)
    if 90 <= opening <= 260:
        rows.append(_row("Answer-first opening", "ok",
                         f"{opening} words that answer the question up front — this is the "
                         "part answer engines lift."))
    elif opening < 90:
        rows.append(_row("Answer-first opening", "warn",
                         f"Only {opening} words. The opening should completely answer the "
                         "main question on its own (120-200 words)."))
    else:
        rows.append(_row("Answer-first opening", "warn",
                         f"{opening} words — long for an opening. Tighten it so the answer "
                         "arrives immediately."))

    # Question-shaped headings
    headings = _HEADING.findall(body)
    questions = [h for h in headings if h.strip().endswith("?")]
    if headings and len(questions) >= max(1, len(headings) // 3):
        rows.append(_row("Question-shaped headings", "ok",
                         f"{len(questions)} of {len(headings)} headings are phrased as "
                         "questions people actually ask."))
    elif headings:
        rows.append(_row("Question-shaped headings", "warn",
                         f"Only {len(questions)} of {len(headings)} headings are questions. "
                         "Question headings are what win answer boxes."))
    else:
        rows.append(_row("Question-shaped headings", "bad",
                         "No H2/H3 headings at all — the piece has no structure for an "
                         "engine to lift."))

    # FAQ
    faq = meta.get("faq") or []
    if 3 <= len(faq) <= 6:
        rows.append(_row("FAQ", "ok", f"{len(faq)} questions — feeds FAQPage schema and AEO."))
    elif faq:
        rows.append(_row("FAQ", "warn", f"{len(faq)} FAQ questions. Three to six is the "
                                        "range that reads as useful rather than padded."))
    else:
        rows.append(_row("FAQ", "bad", "No FAQ. It's the cheapest AEO win there is."))

    # Sources — the important one
    stats = _NUMBER.findall(body)
    sources = meta.get("sources") or []
    known = res.urls if res else set()
    unverified = [s["url"] for s in sources
                  if known and s["url"].rstrip("/") not in {u.rstrip("/") for u in known}]
    if unverified:
        rows.append(_row("Sources", "bad",
                         "These cited URLs were not in the research, so they may be "
                         "invented — open each one before publishing: "
                         + ", ".join(unverified[:4])))
    elif sources:
        rows.append(_row("Sources", "ok",
                         f"{len(sources)} claims cited, every URL traced back to the "
                         "research this run actually found."))
    elif stats:
        rows.append(_row("Sources", "bad",
                         f"The body carries figures ({', '.join(str(s) for s in stats[:4])}) "
                         "but cites no source. Remove them or source them — unsourced "
                         "numbers are exactly what this project doesn't do."))
    else:
        rows.append(_row("Sources", "warn",
                         "No statistics and no sources. Honest, but a sourced figure is the "
                         "single biggest lift for getting cited by AI engines."))

    # Internal links
    home = _domain(site.homepage) if site else ""
    body_links = _MD_LINK.findall(body)
    internal = [u for _, u in body_links if home and _domain(u) == home]
    if len(internal) >= 2:
        rows.append(_row("Internal links", "ok",
                         f"{len(internal)} links to your own pages, which is how a new "
                         "article passes value to the pages you care about."))
    elif internal:
        rows.append(_row("Internal links", "warn",
                         "One internal link. Two or three relevant ones is the norm."))
    else:
        rows.append(_row("Internal links", "warn",
                         "No links to your own site. Add one to the tool or page this "
                         "article naturally leads to."))

    # Slug
    slug = meta.get("slug", "")
    slug_words = len([p for p in slug.split("-") if p])
    if slug and slug_words <= 5:
        rows.append(_row("Slug", "ok", f"`/{slug}/` — {slug_words} words, short and clean."))
    else:
        rows.append(_row("Slug", "bad",
                         f"`/{slug}/` is {slug_words} words. Long, stuffed slugs correlate "
                         "with 'Discovered – not indexed'. Shorten it to 3-5."))

    # Meta lengths
    mt, md = meta.get("meta_title", ""), meta.get("meta_description", "")
    problems = []
    if len(mt) > 60:
        problems.append(f"meta title is {len(mt)} characters (limit 60)")
    if len(md) > 155:
        problems.append(f"meta description is {len(md)} characters (limit 155)")
    if not md:
        problems.append("meta description is empty")
    rows.append(_row("Meta title + description", "warn" if problems else "ok",
                     "; ".join(problems).capitalize() + "." if problems else
                     f"Title {len(mt)}/60, description {len(md)}/155 — both fit in the "
                     "search result."))

    # Length
    words = word_count(body)
    if words < 700:
        rows.append(_row("Length", "warn", f"{words:,} words. Thin pieces are what Google "
                                           "rejected before — go deeper or narrow the topic."))
    elif words > 2200:
        rows.append(_row("Length", "warn", f"{words:,} words. Check none of it is padding."))
    else:
        rows.append(_row("Length", "ok", f"{words:,} words."))

    return rows


def blocking(rows: list) -> list:
    """The checks that should stop a draft going anywhere. [] means good to go."""
    return [r for r in rows if r["state"] == "bad"]


# ── 4. Images ──────────────────────────────────────────────────────────────
def _default_specs(draft: Draft) -> list:
    """A featured image spec, for when the model didn't return any."""
    slug = draft.slug
    return [{
        "role": "featured", "filename": f"{slug}-featured.png",
        "prompt": (f"A clean, modern, uncluttered editorial illustration for an article "
                   f"titled '{draft.title}'. Flat vector style, generous whitespace, no "
                   f"text, no logos, no charts with numbers, no recognisable people."),
        "alt": f"Illustration representing {draft.title}",
    }]


def make_images(draft: Draft, folder: Path) -> list:
    """
    Generate (or brief) the article's images into `folder/images/`.

    Returns [{path, alt, featured, brief}] and also writes `alt-text.json`, the
    filename → alt map the publisher skill reads. Never raises: with no image
    API this writes briefs and the run carries on (CLAUDE.md).
    """
    specs = draft.image_specs or _default_specs(draft)
    out_dir = Path(folder) / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    made, alt_map = [], {}
    for i, spec in enumerate(specs[:3]):
        role = (spec.get("role") or ("featured" if i == 0 else f"inline-{i}")).strip()
        name = spec.get("filename") or f"{draft.slug}-{role}.png"
        name = re.sub(r"[^a-z0-9.\-]", "-", name.lower())
        if not name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            name += ".png"
        alt = (spec.get("alt") or draft.title).strip()
        size = "1200x630" if role == "featured" else "1200x800"

        result = images.generate(spec["prompt"], out_dir / name, size=size, alt_text=alt)
        made.append({"path": result["path"], "alt": alt, "featured": role == "featured",
                     "brief": result["brief"], "detail": result["detail"],
                     "prompt": spec["prompt"]})
        if not result["brief"]:
            alt_map[Path(result["path"]).name] = alt

    if alt_map:
        (out_dir / "alt-text.json").write_text(
            json.dumps(alt_map, indent=2), encoding="utf-8")
    return made


# ── 5. Save the run ────────────────────────────────────────────────────────
def run_folder(draft: Draft) -> Path:
    return OUTPUT_ROOT / draft.slug


def save_run(site, draft: Draft, res: Research = None, image_files: list = None,
             draft_url: str = "") -> Path:
    """
    Write the run to `outputs/<slug>/` in the same layout the orchestrator skill
    uses, so the folder is auditable and the standalone `publish.py` can read it.
    Returns the folder.
    """
    folder = run_folder(draft)
    (folder / "content").mkdir(parents=True, exist_ok=True)
    (folder / "research").mkdir(parents=True, exist_ok=True)

    (folder / "content" / "article.md").write_text(
        f"# {draft.title}\n\n{draft.body_markdown}\n", encoding="utf-8")
    (folder / "content" / "meta.json").write_text(
        json.dumps(draft.meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if res:
        lines = [f"# Research — {res.topic}", "", res.detail, "", "## Sources found"]
        lines += [f"- [{s['title']}]({s['url']})\n  {s['snippet']}" for s in res.sources]
        if res.questions:
            lines += ["", "## Question-shaped results (FAQ candidates)"]
            lines += [f"- {q}" for q in res.questions]
        (folder / "research" / "research-brief.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    (folder / "run.json").write_text(json.dumps({
        "topic": draft.topic,
        "title": draft.title,
        "slug": draft.slug,
        "site": getattr(site, "key", ""),
        "model": config.get("CONTENT_MODEL"),
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sources": len(res.sources) if res else 0,
        "images": [{"path": i["path"], "brief": i["brief"]} for i in (image_files or [])],
        "wordpress_draft_url": draft_url,
    }, indent=2), encoding="utf-8")
    return folder


def recent_runs(limit: int = 8) -> list:
    """The last few saved runs, newest first — what the Content page lists."""
    if not OUTPUT_ROOT.exists():
        return []
    runs = []
    for path in OUTPUT_ROOT.glob("*/run.json"):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")) | {
                "folder": str(path.parent)})
        except Exception:
            continue
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[:limit]


# ── 6. Publish (always a draft) ────────────────────────────────────────────
def to_article(draft: Draft, image_files: list = None) -> Article:
    """The draft as the publishers' `Article`, pictures included."""
    pictures = [i for i in (image_files or []) if not i.get("brief")]
    return Article(
        title=draft.title,
        body_markdown=draft.body_markdown,
        tags=draft.meta.get("tags") or [],
        summary=draft.meta.get("meta_description", ""),
        slug=draft.meta.get("slug", ""),
        categories=draft.meta.get("categories") or [],
        images=[{"path": i["path"], "alt": i.get("alt", ""),
                 "featured": bool(i.get("featured"))} for i in pictures],
    )


def publish_draft(site, draft: Draft, image_files: list = None) -> PublishResult:
    """
    Create the WordPress DRAFT through the existing publisher. Status is
    hard-coded to `draft` inside `publishers/wordpress.py` — there is no live
    publish path here, by design.
    """
    return wordpress.publish(to_article(draft, image_files), site)
