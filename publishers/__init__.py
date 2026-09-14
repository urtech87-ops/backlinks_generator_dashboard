"""
Publishers — one module per platform the Backlink agent may post to.

THE GUARDRAIL LIVES HERE. This registry is the complete list of destinations,
and every one of them is a platform the user OWNS (their dev.to account, their
Blogger blog, their own WordPress). There is deliberately no publisher for
third-party sites: guest posts are drafted and tracked in Lane B, then a human
sends the pitch and the host decides whether to publish.

Every publisher exposes the same three things:

    missing(site) -> list[str]                  which settings are still empty
    publish(article, site, as_draft) -> PublishResult
    LABEL                                       the human name

so the UI can loop over `PLATFORMS` without knowing anything platform-specific.
"""

from dataclasses import dataclass
from typing import Callable

from .base import Article, PublishResult, md_to_html, clean_tags   # noqa: F401
from . import blogger, devto, hashnode, medium, wordpress


@dataclass
class Platform:
    key: str                       # stable id used in session state + the tracker
    label: str                     # human name
    blurb: str                     # one line: what publishing here does
    missing: Callable              # (site) -> list[str]
    publish: Callable              # (article, site, as_draft) -> PublishResult
    style: str                     # a hint for the drafting prompt
    always_draft: bool = False     # True = this platform can never go live


PLATFORMS = {
    "devto": Platform(
        key="devto", label=devto.LABEL,
        blurb="Publishes an article under your own dev.to account.",
        missing=devto.missing, publish=devto.publish,
        style=("dev.to — practising developers. Technical, concrete, first-person. "
               "Short paragraphs, a real code block or worked example, no marketing tone."),
    ),
    "blogger": Platform(
        key="blogger", label=blogger.LABEL,
        blurb="Posts to a Blogger blog you own.",
        missing=blogger.missing, publish=blogger.publish,
        style=("Blogger — a general reader who searched for this problem. Plain "
               "language, step-by-step, explain any jargon the first time it appears."),
    ),
    "wordpress": Platform(
        key="wordpress", label=wordpress.LABEL,
        blurb="Creates a post on your own site — always as a draft, never live.",
        missing=wordpress.missing, publish=wordpress.publish,
        style=("your own site — an existing reader who already trusts the brand. "
               "Useful and specific; it has to be good enough to rank on its own."),
        always_draft=True,
    ),
    "hashnode": Platform(
        key="hashnode", label=hashnode.LABEL,
        blurb="Publishes to a Hashnode publication you own.",
        missing=hashnode.missing, publish=hashnode.publish,
        style=("Hashnode — a technical blogging audience close to dev.to's. Practical, "
               "example-driven, with a real code snippet or worked example where it helps."),
    ),
    "medium": Platform(
        key="medium", label=medium.LABEL,
        blurb="Publishes to your own Medium account. Its API can't edit or delete a post "
              "afterwards, so review carefully before publishing live.",
        missing=medium.missing, publish=medium.publish,
        style=("Medium — a general, curious-reader audience. Narrative and clear, light "
               "on jargon, built around one strong concrete example."),
    ),
}


def ready(key: str, site=None) -> bool:
    """True when this platform has everything it needs to publish."""
    platform = PLATFORMS.get(key)
    return bool(platform) and not platform.missing(site)


def ready_keys(site=None) -> list:
    """The platforms that can publish right now, in registry order."""
    return [k for k in PLATFORMS if ready(k, site)]
