"""
Shared pieces every publisher needs.

An `Article` is what the Backlink agent produces; a `PublishResult` is what a
publisher hands back. Both are deliberately plain so the UI can render a result
without knowing which platform produced it.

House rule (CLAUDE.md): publishers fail soft. A missing key, a dead network or
an unhappy API returns `PublishResult(ok=False, detail=...)` — it never raises
into the dashboard.
"""

import re
from dataclasses import dataclass, field

try:
    import markdown as md_lib
except ImportError:                     # optional — see the fallback below
    md_lib = None


@dataclass
class Article:
    """One platform-ready post, on its way to a platform you own."""
    title: str
    body_markdown: str
    tags: list = field(default_factory=list)
    summary: str = ""
    target_url: str = ""                # the page on your site this links to
    canonical_url: str = ""             # normally blank: the post is original here


@dataclass
class PublishResult:
    ok: bool
    platform: str                       # human label, e.g. "dev.to"
    url: str = ""                       # the live post (or the WP edit screen)
    detail: str = ""                    # plain-language outcome, good or bad
    draft: bool = False                 # True when nothing went live


def md_to_html(md_text: str) -> str:
    """Markdown → HTML for the platforms that don't take markdown."""
    if md_lib:
        return md_lib.markdown(md_text, extensions=["extra", "sane_lists"])
    # Crude fallback so a missing `markdown` package degrades instead of breaking.
    paragraphs = [p.strip() for p in md_text.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def clean_tags(tags, limit: int = 4, alnum_only: bool = False) -> list:
    """
    Normalise model-written tags. dev.to only accepts lowercase alphanumeric
    tags and caps them at four, so `alnum_only` strips anything else out.
    """
    out = []
    for tag in tags or []:
        t = str(tag).strip().lower()
        if alnum_only:
            t = re.sub(r"[^a-z0-9]", "", t)
        else:
            # Keep words and hyphens, drop punctuation, collapse spaces.
            t = re.sub(r"[^a-z0-9\s-]", "", t)
            t = re.sub(r"[\s-]+", "-", t).strip("-")
        if t and t not in out:
            out.append(t[:24])
    return out[:limit]


def missing_keys(pairs) -> list:
    """
    Given [(label, is_set), ...] return the labels that aren't set — used to
    tell the user exactly which box in Settings is still empty.
    """
    return [label for label, ok in pairs if not ok]
