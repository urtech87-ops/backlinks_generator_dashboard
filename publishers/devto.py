"""
dev.to (Forem) publisher — a platform you own an account on.

Posts an article under your own dev.to account with the Forem API. dev.to takes
markdown directly, so no conversion is needed.

API key: dev.to → Settings → Extensions → DEV Community API Keys, saved as
DEVTO_API_KEY in Settings.
"""

import requests

from core import config
from .base import Article, PublishResult, clean_tags, missing_keys

API_URL = "https://dev.to/api/articles"
LABEL = "dev.to"
TIMEOUT = 60


def missing(site=None) -> list:
    """Which settings are still empty. [] means ready to publish."""
    return missing_keys([("dev.to API key", config.is_set("DEVTO_API_KEY"))])


def publish(article: Article, site=None, as_draft: bool = False) -> PublishResult:
    """
    Create the article on dev.to. `as_draft=True` saves it unpublished so you
    can eyeball it on dev.to before it goes live — useful for a first run.
    """
    gaps = missing()
    if gaps:
        return PublishResult(False, LABEL, detail=f"Not set up yet — missing: {', '.join(gaps)}.")

    payload = {
        "article": {
            "title": article.title,
            "body_markdown": article.body_markdown,
            "published": not as_draft,
            "tags": clean_tags(article.tags, limit=4, alnum_only=True),
        }
    }
    if article.canonical_url:
        payload["article"]["canonical_url"] = article.canonical_url

    try:
        r = requests.post(
            API_URL,
            headers={"api-key": config.get("DEVTO_API_KEY"),
                     "Content-Type": "application/json"},
            json=payload, timeout=TIMEOUT,
        )
        if r.status_code == 401:
            return PublishResult(False, LABEL,
                                 detail="dev.to rejected the API key (401). Re-copy it "
                                        "from dev.to → Settings → Extensions.")
        if r.status_code == 422:
            return PublishResult(False, LABEL,
                                 detail=f"dev.to refused the article (422): {r.text[:300]}")
        r.raise_for_status()
        data = r.json()
        url = data.get("url") or data.get("canonical_url", "")
        return PublishResult(
            ok=True, platform=LABEL, url=url, draft=as_draft,
            detail=("Saved as an unpublished dev.to draft — open it on dev.to to publish."
                    if as_draft else "Published live on dev.to."),
        )
    except Exception as e:
        return PublishResult(False, LABEL, detail=f"Couldn't reach dev.to: {e}")
