"""
The Backlink agent — Lane B: human-gated guest-post outreach.

Lane A publishes to platforms you own. Lane B never publishes anything at all.
It does the work that is safe to automate — finding relevant sites, judging
whether they're worth your time, and writing a tailored article and a personal
pitch — and then stops. You read the pitch, you press send, and the host decides
whether to publish. That division is the whole point: scaled auto guest-posting
is a Google link-spam penalty, and there is deliberately no code path here that
posts to a site you don't own (see `publishers/__init__.py` — that registry is
owned platforms only, and this module never touches it).

  1. find_prospects()      searches "write for us"-style footprints in your
                           niche, then reads each candidate page.
  2. score()               relevance + quality from what's actually on the page.
                           No DA/DR, no invented metrics — the score is only
                           ever the signals listed in `Prospect.reasons`.
  3. draft_pitch()         a short, personal email for that one site.
  4. draft_guest_article() the article you'd be offering them, with exactly one
                           contextual link to your target page.

Everything reuses Lane A: the same `Target` ranking, the same page reader, the
same JSON parsing and the same tracker file.
"""

import re
import urllib.parse
from dataclasses import dataclass, field

import requests

from core import config, openrouter, search
# Lane A already solved these — same ranking, same page reader, same JSON
# handling, same anti-fabrication system prompt. Reuse rather than re-write.
from agents.backlink import (
    DraftResult, Target, _SYSTEM, _parse_json, page_facts,
)
from publishers.base import Article

TIMEOUT = 12
UA = "seo-command-center (guest-post research)"

# Search footprints. `{niche}` is your topic; the quoted phrase is how sites
# that WANT contributors describe themselves.
FOOTPRINTS = [
    '"write for us" {niche}',
    '"guest post guidelines" {niche}',
    '"submit a guest post" {niche}',
    '"become a contributor" {niche}',
    '"contribute to our blog" {niche}',
]

# Never prospect these: social networks, Q&A and aggregator sites, freelancer
# marketplaces, and the publishing platforms Lane A already owns.
EXCLUDED_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "pinterest.com", "reddit.com", "quora.com", "youtube.com", "tiktok.com",
    "medium.com", "dev.to", "blogger.com", "blogspot.com", "wordpress.com",
    "substack.com", "tumblr.com", "wixsite.com", "fiverr.com", "upwork.com",
    "indeed.com", "glassdoor.com", "google.com", "bing.com", "duckduckgo.com",
    "amazon.com", "wikipedia.org", "github.com",
}

# Wording that means the site sells links. Buying links breaks Google's
# guidelines, so these are disqualifying rather than merely low-scoring.
PAID_SIGNALS = [
    "paid guest post", "paid post", "sponsored post fee", "publication fee",
    "posting fee", "per post fee", "pay for a guest post", "buy a guest post",
    "guest post service", "guest posting service", "buy backlink", "sell link",
    "link building service", "pbn", "da 50", "da50", "dr 50", "casino", "cbd links",
]

# Wording that means a real editor reads submissions.
EDITORIAL_SIGNALS = [
    "editorial", "guidelines", "original content", "plagiar", "we do not accept",
    "we don't accept", "pitch", "word count", "author bio", "byline",
    "not accept promotional", "no promotional", "reject", "review process",
]

# Wording in a URL or title that says this really is a contributor page.
GUEST_PAGE_SIGNALS = ["write-for-us", "write for us", "guest-post", "guest post",
                      "contribute", "contributor", "submit", "guest author",
                      "become-an-author", "write-for-me"]

COMMON_TLDS = {"com", "net", "org", "io", "co", "dev", "blog", "tech", "info",
               "app", "ai", "me", "us", "uk", "ca", "au", "in", "de", "eu"}

STOPWORDS = {"the", "and", "for", "with", "that", "this", "your", "you", "from",
             "have", "how", "what", "are", "our", "best", "free", "online",
             "tools", "tool", "site", "website", "blog", "page"}

WORTH = "Worth pitching"
MAYBE = "Check it yourself"
SKIP = "Skip"


@dataclass
class Prospect:
    """One site that says it accepts guest posts, judged on what it actually says."""
    domain: str
    url: str                       # the guidelines / "write for us" page found
    title: str = ""
    snippet: str = ""              # from the search result
    description: str = ""          # the page's own meta description
    contact: str = ""              # an email printed on that page, if any
    relevance: int = 0             # 0-50
    quality: int = 0               # 0-50
    score: int = 0                 # 0-100, after penalties
    verdict: str = MAYBE
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fetched: bool = False          # did the page actually load?
    query: str = ""                # which footprint found it


@dataclass
class Pitch:
    """A personal email you have to read and approve before it goes anywhere."""
    ok: bool
    subject: str = ""
    body: str = ""
    ideas: list = field(default_factory=list)
    detail: str = ""


# ── Small helpers ──────────────────────────────────────────────────────────
def domain_of(url: str) -> str:
    """Bare registrable-looking domain, lowercased and without www."""
    if "//" not in url:
        url = "https://" + url
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _is_excluded(domain: str) -> bool:
    return any(domain == bad or domain.endswith("." + bad) for bad in EXCLUDED_DOMAINS)


def own_domains() -> set:
    """Your own sites — never pitch yourself a guest post."""
    return {domain_of(s.homepage) for s in config.SITES if s.homepage}


def _terms(text: str) -> set:
    """The meaningful words in a phrase, used for relevance matching."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def _visible_text(html: str) -> str:
    """Rough page text — enough to read guidelines wording, not a parser."""
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EMAIL_JUNK = ("example.com", "sentry.io", "wixpress.com", "domain.com",
               "yourdomain", "email.com", ".png", ".jpg", ".jpeg", ".gif", ".webp")


def _emails(html: str, domain: str) -> str:
    """
    The best contact address printed on a page that is inviting submissions.
    Prefers one on the host's own domain, and editor/content addresses over
    generic ones. Returns "" when the page only offers a contact form.
    """
    found, seen = [], set()
    for match in _EMAIL_RE.findall(html):
        address = match.strip(".").lower()
        if address in seen or any(junk in address for junk in _EMAIL_JUNK):
            continue
        seen.add(address)
        found.append(address)
    if not found:
        return ""

    def rank(address: str) -> tuple:
        local, _, host = address.partition("@")
        on_domain = host.endswith(domain)
        editorial = any(word in local for word in
                        ("editor", "content", "submit", "guest", "write", "pitch"))
        generic = local in ("info", "hello", "contact", "admin", "support")
        return (not on_domain, not editorial, not generic)

    return sorted(found, key=rank)[0]


def _fetch(url: str, timeout: int = TIMEOUT) -> str:
    """The page's HTML, or "" if it won't load. Never raises."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
        r.raise_for_status()
        return r.text[:400_000]
    except Exception:
        return ""


# ── 2. Scoring ─────────────────────────────────────────────────────────────
def score(prospect: Prospect, niche: str, page_text: str = "") -> Prospect:
    """
    Judge one prospect on relevance to your niche and on whether it looks like a
    real, editorially-run site. Fills in `score`, `verdict`, `reasons` and
    `warnings` — and every point is traceable to a line in `reasons`, because
    there is no authority metric here to hide behind.
    """
    reasons, warnings = [], []
    haystack = " ".join([prospect.domain, prospect.title, prospect.snippet,
                         prospect.description, page_text[:8000]]).lower()
    header = f"{prospect.domain} {prospect.title} {prospect.url}".lower()

    # ── Relevance (0-50) ──
    wanted = _terms(niche)
    matched = {t for t in wanted if t in haystack}
    relevance = 0
    if wanted:
        relevance = round(len(matched) / len(wanted) * 38)
        if matched:
            reasons.append(f"Mentions {len(matched)} of your {len(wanted)} niche terms "
                           f"({', '.join(sorted(matched)[:5])}).")
        else:
            warnings.append("None of your niche words appear on this page — it may "
                            "accept guest posts about something else entirely.")
    if any(t in header for t in matched):
        relevance += 12
        reasons.append("Your topic is in the site's own name or page title, so its "
                       "audience is likely to be yours.")
    relevance = min(relevance, 50)

    # ── Quality (0-50) ──
    quality = 0
    if prospect.url.startswith("https://"):
        quality += 4
        reasons.append("Served over HTTPS.")
    if prospect.fetched:
        quality += 8
        reasons.append("The guidelines page loads and could be read.")
    else:
        warnings.append("The page wouldn't load from here, so this is scored on the "
                        "search result alone — open it yourself before pitching.")

    if any(sig in header for sig in GUEST_PAGE_SIGNALS):
        quality += 10
        reasons.append("The page is openly a contributor / write-for-us page.")

    editorial_hits = [sig for sig in EDITORIAL_SIGNALS if sig in page_text.lower()]
    if editorial_hits:
        quality += min(len(editorial_hits), 4) * 3
        reasons.append(f"Reads like a real editorial process ({len(editorial_hits)} "
                       "guideline signals: submission rules, word counts, rejections).")
    elif prospect.fetched:
        warnings.append("No editorial guidelines wording on the page. Sites that accept "
                        "anything pass their lack of standards on to you.")

    if prospect.contact:
        quality += 6
        reasons.append(f"A contact address is printed on the page ({prospect.contact}).")

    tld = prospect.domain.rsplit(".", 1)[-1]
    if tld in COMMON_TLDS and prospect.domain.count("-") <= 1:
        quality += 5
        reasons.append("Ordinary domain name — not the hyphen-stuffed pattern link "
                       "farms use.")
    if len(page_text) > 1500:
        quality += 5
        reasons.append("The page has real content on it, not a stub.")
    quality = min(quality, 50)

    # ── Disqualifiers ──
    total = relevance + quality
    paid = [sig for sig in PAID_SIGNALS if sig in haystack]
    if paid:
        warnings.append(f"This page talks about paying for placement (\"{paid[0]}\"). "
                        "Buying links breaks Google's guidelines — skip it.")
        total -= 60
    if prospect.domain.count("-") >= 3 or any(
            word in prospect.domain for word in ("guestpost", "backlink", "seoblog",
                                                 "writeforus", "linkbuilding")):
        warnings.append("The domain itself is built around selling guest posts. A link "
                        "from a site like this is worth nothing, or worse.")
        total -= 25

    prospect.relevance = relevance
    prospect.quality = quality
    prospect.score = max(0, min(100, total))
    prospect.reasons = reasons
    prospect.warnings = warnings
    if paid:
        prospect.verdict = SKIP
    elif prospect.score >= 65:
        prospect.verdict = WORTH
    elif prospect.score >= 40:
        prospect.verdict = MAYBE
    else:
        prospect.verdict = SKIP
    return prospect


# ── 1. Prospecting ─────────────────────────────────────────────────────────
def queries_for(niche: str, extra: list = None) -> list:
    """The footprints that will be searched, so the UI can show them first."""
    niche = niche.strip()
    out = [fp.format(niche=niche) for fp in FOOTPRINTS] if niche else []
    return out + [q.strip() for q in (extra or []) if q.strip()]


def find_prospects(niche: str, limit: int = 12, per_query: int = 10,
                   extra_queries: list = None, read_pages: bool = True,
                   footprints: list = None, progress=None) -> dict:
    """
    Search the footprints, dedupe to one entry per domain, read each candidate
    page and score it.

    Returns {'ok', 'prospects', 'detail', 'searched', 'failures'}. `ok` is False
    only when no search ran at all — a partial result is still a result, and the
    UI names the queries that failed.
    """
    queries = footprints or queries_for(niche, extra_queries)
    if not queries:
        return {"ok": False, "prospects": [], "searched": [], "failures": [],
                "detail": "Describe your niche first — the search needs a topic."}

    skip = own_domains()
    best: dict = {}
    searched, failures = [], []

    for i, query in enumerate(queries):
        if progress:
            progress((i) / len(queries), f"Searching: {query}")
        result = search.search(query, limit=per_query)
        if not result["ok"]:
            failures.append(f"`{query}` — {result['detail']}")
            continue
        searched.append(query)
        for hit in result["results"]:
            domain = domain_of(hit.url)
            if not domain or domain in skip or _is_excluded(domain):
                continue
            if domain in best:                 # keep the first (highest-ranked) page
                continue
            best[domain] = Prospect(domain=domain, url=hit.url, title=hit.title,
                                    snippet=hit.snippet, query=query)

    if not searched:
        return {"ok": False, "prospects": [], "searched": [], "failures": failures,
                "detail": "No search ran. " + (failures[0].split("— ", 1)[-1]
                                               if failures else "")}

    prospects = list(best.values())[: max(limit * 2, limit)]
    for i, prospect in enumerate(prospects):
        if progress:
            progress(0.5 + (i / max(len(prospects), 1)) / 2,
                     f"Reading {prospect.domain}…")
        _enrich_and_score(prospect, niche, read_pages)

    prospects.sort(key=lambda p: -p.score)
    detail = (f"Searched {len(searched)} of {len(queries)} queries and found "
              f"{len(prospects)} candidate sites.")
    return {"ok": True, "prospects": prospects[:limit], "searched": searched,
            "failures": failures, "detail": detail}


def _enrich_and_score(prospect: Prospect, niche: str, read_page: bool = True) -> Prospect:
    """Read the prospect's page once, then score it on what it says."""
    text = ""
    if read_page:
        html = _fetch(prospect.url)
        if html:
            prospect.fetched = True
            facts = page_facts(prospect.url, html=html)      # Lane A's reader
            prospect.title = prospect.title or facts.get("title", "")
            prospect.description = facts.get("description", "")
            prospect.contact = _emails(html, prospect.domain)
            text = _visible_text(html)
    return score(prospect, niche, text)


def prospect_from_url(url: str, niche: str = "", read_page: bool = True) -> Prospect:
    """
    Score a single site you already know about — the manual way in, for when
    search is throttled or an editor was recommended to you.
    """
    url = url.strip()
    if not url:
        return None
    if not url.startswith("http"):
        url = "https://" + url
    prospect = Prospect(domain=domain_of(url), url=url, query="added by hand")
    return _enrich_and_score(prospect, niche, read_page)


# ── 3. The pitch ───────────────────────────────────────────────────────────
def _host_context(prospect: Prospect) -> str:
    known = [f"- Site: {prospect.domain}",
             f"- The page inviting contributors: {prospect.url}"]
    if prospect.title:
        known.append(f"- That page's title: {prospect.title}")
    if prospect.description:
        known.append(f"- Its description: {prospect.description}")
    if prospect.snippet:
        known.append(f"- How it appeared in search: {prospect.snippet}")
    if not prospect.fetched:
        known.append("- The page could not be read, so you know nothing beyond the "
                     "above. Do not imply you have read their articles.")
    return "\n".join(known)


def _pitch_prompt(site, target: Target, prospect: Prospect, facts: dict,
                  sender: str, notes: str) -> str:
    target_desc = facts.get("title") or facts.get("description") or ""
    return f"""Write one guest-post pitch email to the editor of {prospect.domain}.

THE SITE YOU ARE WRITING TO
{_host_context(prospect)}

WHO IS WRITING
- {sender or "the sender (sign off with [your name])"}, who runs {site.label} ({site.homepage}).
- The resource they would link to, once, where it genuinely helps the reader:
  {target.url}{f" — {target_desc}" if target_desc else ""}

WHAT THE EMAIL MUST DO
1. Be a real email from one person to another: short, specific, no flattery
   template ("I love your blog!"), no marketing voice. Under 180 words.
2. Say in one line who is writing and why this site in particular — using only
   what you were told above. Never claim to have read a specific article, met
   anyone, or seen their traffic.
3. Offer THREE concrete article ideas that fit that site's audience. Titles a
   reader would click, not keyword strings.
4. Say plainly that the draft would include one contextual link to
   {target.url} where it's useful, and that the editor is free to cut it.
5. Ask one clear question: would any of these be useful, and what are their
   guidelines.
6. End with a normal sign-off{f" from {sender}" if sender else " ending [your name]"}.

HARD RULES
- Invent NOTHING: no statistics, no traffic numbers, no client names, no awards,
  no "I have written for X" claims, no fake deadlines or urgency.
- Never offer or ask for payment, link exchanges, or "do-follow" links. Never
  mention SEO, backlinks, domain authority or rankings — you are offering an
  article, not buying a link.
- No mail-merge placeholders other than a name you were actually given.
{f"- Extra direction from the user: {notes}" if notes.strip() else ""}

RETURN
Only a JSON object, no code fence, with exactly these keys:
{{"subject": "a short, specific subject line — no exclamation marks",
  "body": "the plain-text email, with real line breaks",
  "ideas": ["the three article titles you offered"]}}"""


def draft_pitch(site, target: Target, prospect: Prospect, notes: str = "",
                sender: str = "") -> Pitch:
    """Write one personalised pitch. Sends nothing — this only returns text."""
    facts = page_facts(target.url)
    sender = sender or config.get("OUTREACH_FROM_NAME")
    result = openrouter.chat(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": _pitch_prompt(site, target, prospect, facts,
                                                   sender, notes)}],
        model=config.get("BACKLINK_MODEL"),
        temperature=0.6,
        max_tokens=1200,
    )
    if not result["ok"]:
        return Pitch(False, detail=result["detail"])

    data = _parse_json(result["text"])
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    if not subject or not body:
        return Pitch(False, detail="The model's reply wasn't usable JSON. Try again, or "
                                   "pick a different BACKLINK_MODEL in Settings.")
    return Pitch(True, subject=subject, body=body,
                 ideas=[str(i) for i in (data.get("ideas") or [])],
                 detail=result["detail"])


# Wording that makes a pitch read like a mailshot or a link buy. Checked in the
# UI so you see it before you send, not after.
_PITCH_FLAGS = [
    ("dear sir", "\"Dear Sir/Madam\" reads as a mail-merge. Use their name, or 'Hi there'."),
    ("dear webmaster", "\"Dear Webmaster\" is template wording — editors bin these."),
    ("do-follow", "Asking for a do-follow link is a link request, not a pitch. Cut it."),
    ("dofollow", "Asking for a dofollow link is a link request, not a pitch. Cut it."),
    ("domain authority", "Talking about domain authority tells the editor you want a "
                         "link, not a byline."),
    ("backlink", "Saying 'backlink' out loud in a pitch is a fast no. Cut it."),
    ("link exchange", "Link exchanges are a Google guidelines violation. Cut it."),
    ("i will pay", "Never offer payment for a link."),
]


def pitch_checks(subject: str, body: str) -> list:
    """Plain-language warnings about a pitch, for the UI to show before sending."""
    problems = []
    text = f"{subject}\n{body}".lower()
    for needle, message in _PITCH_FLAGS:
        if needle in text:
            problems.append(message)
    words = len(body.split())
    if words > 260:
        problems.append(f"{words} words — long for a cold email. Editors skim; "
                        "under 180 gets read.")
    if re.search(r"\[(?!your name)[^\]]{2,}\]", body):
        problems.append("There's an unfilled [placeholder] left in the text.")
    if not subject.strip():
        problems.append("No subject line.")
    return problems


# ── 4. The guest article ───────────────────────────────────────────────────
def _article_prompt(site, target: Target, prospect: Prospect, facts: dict,
                    angle: str, notes: str) -> str:
    if facts.get("title") or facts.get("description"):
        known = (f"- Its page title: {facts.get('title', '')}\n"
                 f"- Its meta description: {facts.get('description', '')}\n"
                 f"- Its main heading: {facts.get('heading', '')}")
    else:
        known = ("- The page could not be fetched, so infer its topic from the URL and "
                 "stay general enough that you cannot be wrong about what it contains.")

    return f"""Write one guest article, offered to the editor of {prospect.domain}.

THE SITE THAT WOULD PUBLISH IT
{_host_context(prospect)}
Write for that site's readers, in a voice that would sit naturally on it. This
has to be good enough that an editor who owes you nothing still wants it.

{f"THE ANGLE THE EDITOR AGREED TO{chr(10)}{angle}{chr(10)}" if angle.strip() else ""}
THE PAGE THIS ARTICLE SHOULD LINK TO
- URL: {target.url}
- It lives on {site.label} ({site.homepage})
{known}

WHAT THE ARTICLE MUST DO
1. Earn its place. Teach something concrete — a real problem, how to approach
   it, and a worked example or step-by-step walkthrough. A reader who never
   clicks the link should still finish it glad they read it.
2. Contain EXACTLY ONE link to {target.url}, in markdown, at the point where
   that page is genuinely the useful next step. Descriptive anchor text that
   reads naturally in the sentence — never "click here", never the raw URL.
3. Be 900-1300 words. No filler, no "in today's fast-paced world", no restating
   the title as the first sentence.
4. Use question-shaped H2 headings where they fit, and end with a short FAQ of
   two or three questions a reader would really type.

HARD RULES
- Invent nothing. No made-up statistics, percentages, study results, quotes or
  tool names. Anything you are not sure of, say qualitatively or leave out.
- No keyword stuffing. No other links to {site.homepage}. No promotional copy
  about {site.label} — one contextual link is the whole of it.
- Do not mention SEO, backlinks, or that this article exists to link somewhere.
{f"- Extra direction from the user: {notes}" if notes.strip() else ""}

RETURN
Only a JSON object, no code fence, with exactly these keys:
{{"title": "the article title, under 70 characters",
  "summary": "one sentence for the editor, under 160 characters",
  "tags": ["3-4 short lowercase topic tags"],
  "body_markdown": "the full article in markdown, starting at the first paragraph (no H1 — the title is separate)"}}"""


def draft_guest_article(site, target: Target, prospect: Prospect, angle: str = "",
                        notes: str = "") -> DraftResult:
    """
    Write the article you would be offering. It is never published from here —
    if the host says yes, they publish it, or you send it to them.
    """
    facts = page_facts(target.url)
    result = openrouter.chat(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": _article_prompt(site, target, prospect, facts,
                                                     angle, notes)}],
        model=config.get("BACKLINK_MODEL"),
        temperature=0.7,
    )
    if not result["ok"]:
        return DraftResult(False, detail=result["detail"])

    data = _parse_json(result["text"])
    body = (data.get("body_markdown") or "").strip()
    title = (data.get("title") or "").strip()
    if not body or not title:
        return DraftResult(False, detail="The model's reply wasn't usable JSON. Try "
                                         "again, or pick a different BACKLINK_MODEL in "
                                         "Settings.")

    article = Article(
        title=title,
        body_markdown=body,
        tags=data.get("tags") or [],
        summary=(data.get("summary") or "").strip(),
        target_url=target.url,
    )
    detail = result["detail"]
    if target.url not in body:
        detail += (" ⚠️ The draft doesn't contain the target link — add it before you "
                   "send it, or regenerate.")
    if not facts:
        detail += " (Your target page wouldn't load, so the topic came from its URL.)"
    return DraftResult(True, article=article, detail=detail)
