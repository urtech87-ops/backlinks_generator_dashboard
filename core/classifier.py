"""
The brain of the Fix Plan.

Takes a page's live GSC coverage state (or a seeded one) and decides:
  - which bucket it belongs to
  - how urgent it is
  - what you should actually do about it

Bucket logic follows the strategist reading of your Search Console data:

  PLUMBING   -> Google can't index it because the URL redirects wrong / 404s.
                Fix the URL. Highest leverage, fastest win. No backlink helps here.
  CONTENT    -> Google crawled it and rejected it on quality. Rewrite required.
                No backlink overrides a quality verdict.
  CRAWL_BUDGET -> Google hasn't crawled it yet. Internal links + sitemap + a
                  couple of real backlinks help. This is the ONLY bucket where
                  link-building does anything.
  HEALTHY    -> Indexed. Eligible for the backlink / outreach stage.
  OTHER      -> Intentional or informational (noindex, robots, unknown).
  UNKNOWN    -> Search Console COULDN'T be checked (an API error, quota, or it
                simply hasn't been checked yet). This is NOT "not indexed" —
                it's "we don't know", and it must never be silently read as a
                real verdict. See ui/data.py::refresh_live().
"""

from dataclasses import dataclass
import re

PLUMBING = "Plumbing"
CONTENT = "Content"
CRAWL_BUDGET = "Crawl budget"
HEALTHY = "Healthy"
OTHER = "Other"
UNKNOWN = "Couldn't check"

BUCKET_ORDER = [UNKNOWN, PLUMBING, CONTENT, CRAWL_BUDGET, OTHER, HEALTHY]

# Priority: lower number = deal with it sooner. UNKNOWN sits with PLUMBING:
# until it's resolved you don't actually know what this page needs.
BUCKET_PRIORITY = {
    UNKNOWN: 1,
    PLUMBING: 1,
    CONTENT: 2,
    CRAWL_BUDGET: 3,
    OTHER: 4,
    HEALTHY: 5,
}

# Map the raw coverageState strings the URL Inspection API returns to a bucket.
# ORDER MATTERS: every "... not indexed" / error state must be matched BEFORE any
# generic "indexed" rule, because the word "indexed" is a substring of "not
# indexed". The bare "indexed -> HEALTHY" case is handled in the fallback below,
# guarded so it can never fire when "not indexed" is present.
_COVERAGE_MAP = [
    # Couldn't check (an inspection error, marked by ui/data.py::refresh_live()
    # as "Couldn't check: <error>"). MUST be matched first: an API error message
    # can legitimately contain words like "not found" or "404" describing the
    # HTTP failure itself, which must never be mistaken for a real coverage verdict.
    ("couldn't check", UNKNOWN),
    # Plumbing (broken URLs)
    ("redirect error", PLUMBING),
    ("page with redirect", PLUMBING),
    ("not found (404)", PLUMBING),
    ("submitted url not found", PLUMBING),
    ("soft 404", PLUMBING),
    ("server error", PLUMBING),
    # Content (crawled + rejected)
    ("crawled - currently not indexed", CONTENT),
    # Crawl budget (not yet crawled)
    ("discovered - currently not indexed", CRAWL_BUDGET),
    ("url is unknown to google", CRAWL_BUDGET),
    # Other / intentional
    ("blocked by robots", OTHER),
    ("excluded by 'noindex'", OTHER),
    ("alternate page with proper canonical", OTHER),
    ("duplicate", OTHER),
    ("noindex", OTHER),
    # Healthy — specific phrases only (generic "indexed" is the guarded fallback)
    ("submitted and indexed", HEALTHY),
    ("indexed, not submitted", HEALTHY),
]

# WordPress default junk that should be deleted or noindexed, never fought for.
_WP_JUNK = re.compile(
    r"(/sample-page/?$|/category/uncategorized/?$|/author/|/feed/?$|/wp-|/\*$)",
    re.IGNORECASE,
)


def bucket_for_coverage(coverage_state: str) -> str:
    if not coverage_state:
        return OTHER
    cs = coverage_state.strip().lower()
    for needle, bucket in _COVERAGE_MAP:
        if needle in cs:
            return bucket
    # Guarded fallback: a bare "indexed" is healthy ONLY if it's not a
    # "... not indexed" state we didn't explicitly list.
    if "not indexed" in cs:
        return CRAWL_BUDGET
    if "indexed" in cs:
        return HEALTHY
    return OTHER


def _last_segment(url: str) -> str:
    path = re.sub(r"https?://[^/]+", "", url).strip("/")
    return path.split("/")[-1] if path else ""


def slug_is_stuffed(url: str) -> bool:
    """Long, keyword-stuffed slug — a low-quality signal to Google on its own."""
    seg = _last_segment(url)
    return len(seg) > 55 or seg.count("-") >= 7


def looks_malformed(url: str) -> bool:
    """
    The tell-tale nested paths from a relative-link bug, e.g.
      /image-watermarker/contact-us   /privacy-policy/privacy-policy
      /home/ai-code-explainer         /ascii-art-generator/contact-us
    A tool-looking segment followed by a boilerplate page, a doubled segment,
    or a stray /home/ prefix almost always means links are written relative
    instead of absolute.
    """
    path = re.sub(r"https?://[^/]+", "", url).strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        boilerplate = {"contact-us", "privacy-policy", "about", "about-us", "terms"}
        if parts[-1] in boilerplate and parts[-2] not in ("blogs", "pages"):
            return True
        if len(parts) >= 2 and parts[-1] == parts[-2]:      # doubled segment
            return True
    if parts and parts[0] == "home" and len(parts) > 1:      # stray /home/ prefix
        return True
    return False


def is_wp_junk(url: str) -> bool:
    return bool(_WP_JUNK.search(url))


@dataclass
class PageVerdict:
    url: str
    coverage: str
    bucket: str
    priority: int
    action: str
    flags: list


def recommend(url: str, coverage_state: str) -> PageVerdict:
    bucket = bucket_for_coverage(coverage_state)
    flags = []
    if slug_is_stuffed(url):
        flags.append("stuffed-slug")
    if looks_malformed(url):
        flags.append("relative-link-bug")
    if is_wp_junk(url):
        flags.append("wp-junk")

    # Build a concrete action string per bucket, sharpened by the flags.
    if "wp-junk" in flags and bucket in (PLUMBING, OTHER):
        action = "WordPress default / archive page — delete it or set noindex; drop from sitemap. Not worth fixing."
    elif bucket == UNKNOWN:
        action = ("Search Console couldn't be checked for this URL last refresh — an API "
                  "error (auth, quota, or a property/URL mismatch), not a real verdict from "
                  "Google. This page's actual indexing status is still unknown. Press "
                  "Refresh live data again; if it keeps failing, run Settings → Test "
                  "connections to see exactly which step is failing.")
    elif bucket == PLUMBING:
        if "relative-link-bug" in flags:
            action = ("Malformed nested URL. Root cause is almost certainly relative links "
                      "(href=\"contact-us\" instead of \"/contact-us\"). Fix the template link once "
                      "and several of these clear together.")
        else:
            action = ("Broken redirect / 404. Point the redirect at the correct live URL, or restore "
                      "the page. If it's a real tool page, this is urgent — Google can't reach it at all.")
    elif bucket == CONTENT:
        action = ("Google crawled and rejected on quality. Rewrite: real use-cases, one worked example, "
                  "an FAQ, remove AI filler. Then request indexing (after it settles).")
    elif bucket == CRAWL_BUDGET:
        base = ("Not crawled yet. Add internal links from the homepage and strong pages, confirm it's "
                "in the sitemap. This is the one bucket where 1-2 real backlinks help.")
        if "stuffed-slug" in flags:
            base += " Slug is keyword-stuffed — shorten it and 301 the old URL first."
        action = base
    elif bucket == HEALTHY:
        action = "Indexed and healthy. Eligible for the backlink / outreach stage. Track its clicks + position."
    else:
        action = "Intentional or informational (noindex/robots/canonical). Usually no action needed."

    return PageVerdict(
        url=url,
        coverage=coverage_state or "unknown",
        bucket=bucket,
        priority=BUCKET_PRIORITY[bucket],
        action=action,
        flags=flags,
    )
