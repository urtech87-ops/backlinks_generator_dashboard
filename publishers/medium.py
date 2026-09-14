"""
Medium publisher — your own Medium account, via its integration-token API.

Auth is a Medium integration token (Medium → Settings → Security and apps →
Integration tokens — Medium stopped issuing new ones in 2023, but an existing
token still works). Saved as MEDIUM_TOKEN in Settings.

NOTE: Medium's API is publish-only. There is no endpoint to edit or delete a
post once it's created — the only knob is `publishStatus` at creation time,
so `as_draft=True` (Medium's own "draft" status) is the only way to keep a
first run reversible; anything else has to be fixed or removed on Medium's
own site afterwards.
"""

import requests

from core import config
from .base import Article, PublishResult, clean_tags, missing_keys

API_BASE = "https://api.medium.com/v1"
LABEL = "Medium"
TIMEOUT = 60


def missing(site=None) -> list:
    """Which settings are still empty. [] means ready to publish."""
    return missing_keys([("Medium integration token", config.is_set("MEDIUM_TOKEN"))])


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.get('MEDIUM_TOKEN')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Charset": "utf-8"}


def _author_id() -> tuple:
    """Medium posts are created under a user id, read from /me. Returns (id, error)."""
    try:
        r = requests.get(f"{API_BASE}/me", headers=_headers(), timeout=30)
        if r.status_code == 401:
            return "", ("Medium rejected the token (401). Re-issue an integration token "
                        "from Medium → Settings → Security and apps.")
        r.raise_for_status()
        author_id = r.json().get("data", {}).get("id", "")
        if not author_id:
            return "", "Medium returned no user id for that token."
        return author_id, ""
    except Exception as e:
        return "", f"Couldn't reach Medium: {e}"


def publish(article: Article, site=None, as_draft: bool = False) -> PublishResult:
    """
    Create the post on your Medium account. `as_draft=True` uses Medium's own
    "draft" publish status — the only safety net, since the API can't edit or
    delete a post after it exists.
    """
    gaps = missing()
    if gaps:
        return PublishResult(False, LABEL, detail=f"Not set up yet — missing: {', '.join(gaps)}.")

    author_id, err = _author_id()
    if err:
        return PublishResult(False, LABEL, detail=err)

    payload = {
        "title": article.title,
        "contentFormat": "markdown",
        "content": article.body_markdown,
        "tags": clean_tags(article.tags, limit=5),
        "publishStatus": "draft" if as_draft else "public",
    }
    if article.canonical_url:
        payload["canonicalUrl"] = article.canonical_url

    try:
        r = requests.post(f"{API_BASE}/users/{author_id}/posts",
                          headers=_headers(), json=payload, timeout=TIMEOUT)
        if r.status_code == 401:
            return PublishResult(False, LABEL,
                                 detail="Medium rejected the token (401) on publish.")
        if r.status_code == 400:
            return PublishResult(False, LABEL,
                                 detail=f"Medium refused the post (400): {r.text[:300]}")
        r.raise_for_status()
        data = r.json().get("data", {})
        return PublishResult(
            ok=True, platform=LABEL, url=data.get("url", ""), draft=as_draft,
            detail=("Saved as a Medium draft — the API can't edit or delete it "
                    "afterwards, so publish or discard it from Medium itself."
                    if as_draft else
                    "Published live on Medium. There is no edit/delete endpoint — "
                    "changes after this happen on Medium's site."),
        )
    except Exception as e:
        return PublishResult(False, LABEL, detail=f"Medium post failed: {e}")
