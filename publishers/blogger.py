"""
Blogger publisher — a blog you own, via the Blogger v3 API.

Auth is the installed-app refresh-token flow: a long-lived refresh token is
exchanged for a short-lived access token on every run, so nothing needs a
browser login. The four settings it needs (blog id, client id, client secret,
refresh token) already exist in Settings → Backlink platforms.

    ┌─────────────────────────────────────────────────────────────────────┐
    │ NOTE FOR THE NEXT PERSON                                            │
    │ `daily_backlink_job.py` was meant to be ported here verbatim, but   │
    │ it never reached the repo — so `_access_token()` below is the       │
    │ standard Google refresh-token exchange written from scratch. If the │
    │ original does anything different (a different token endpoint,       │
    │ extra scopes, a cached token file), replace ONLY `_access_token()`  │
    │ with the original — nothing else in this module touches auth.       │
    └─────────────────────────────────────────────────────────────────────┘
"""

import requests

from core import config
from .base import Article, PublishResult, clean_tags, md_to_html, missing_keys

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/blogger/v3"
LABEL = "Blogger"
TIMEOUT = 60


def missing(site=None) -> list:
    """Which settings are still empty. [] means ready to publish."""
    return missing_keys([
        ("Blogger blog ID", config.is_set("BLOGGER_BLOG_ID")),
        ("Blogger OAuth client ID", config.is_set("BLOGGER_CLIENT_ID")),
        ("Blogger OAuth client secret", config.is_set("BLOGGER_CLIENT_SECRET")),
        ("Blogger refresh token", config.is_set("BLOGGER_REFRESH_TOKEN")),
    ])


def _access_token() -> tuple:
    """
    Trade the stored refresh token for a fresh access token.
    Returns (token, error) — exactly one of the two is set.
    """
    try:
        r = requests.post(TOKEN_URL, data={
            "client_id": config.get("BLOGGER_CLIENT_ID"),
            "client_secret": config.get("BLOGGER_CLIENT_SECRET"),
            "refresh_token": config.get("BLOGGER_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        }, timeout=30)
        if r.status_code in (400, 401):
            # The usual causes, in the order they actually happen.
            return "", ("Google rejected the refresh token. It expires if the OAuth "
                        "consent screen is still in Testing mode (7 days), or if the "
                        "client secret was rotated. Re-issue it and paste it into "
                        "Settings → Backlink platforms.")
        r.raise_for_status()
        token = r.json().get("access_token", "")
        if not token:
            return "", "Google returned no access token for that refresh token."
        return token, ""
    except Exception as e:
        return "", f"Couldn't reach Google's token endpoint: {e}"


def check_auth() -> dict:
    """A standalone 'do these four settings work?' test for the UI."""
    gaps = missing()
    if gaps:
        return {"ok": False, "detail": f"Missing: {', '.join(gaps)}."}
    token, err = _access_token()
    if err:
        return {"ok": False, "detail": err}
    try:
        r = requests.get(f"{API_BASE}/blogs/{config.get('BLOGGER_BLOG_ID')}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code == 404:
            return {"ok": False, "detail": "That blog ID doesn't exist, or this Google "
                                           "account doesn't own it."}
        r.raise_for_status()
        blog = r.json()
        return {"ok": True, "detail": f"Connected to “{blog.get('name', 'your blog')}” "
                                      f"({blog.get('url', '')})."}
    except Exception as e:
        return {"ok": False, "detail": f"Token worked, but the blog lookup failed: {e}"}


def publish(article: Article, site=None, as_draft: bool = False) -> PublishResult:
    """Create the post on your Blogger blog. Blogger wants HTML, not markdown."""
    gaps = missing()
    if gaps:
        return PublishResult(False, LABEL, detail=f"Not set up yet — missing: {', '.join(gaps)}.")

    token, err = _access_token()
    if err:
        return PublishResult(False, LABEL, detail=err)

    body = {
        "kind": "blogger#post",
        "title": article.title,
        "content": md_to_html(article.body_markdown),
        "labels": clean_tags(article.tags, limit=6),
    }
    try:
        r = requests.post(
            f"{API_BASE}/blogs/{config.get('BLOGGER_BLOG_ID')}/posts/",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            params={"isDraft": "true" if as_draft else "false"},
            json=body, timeout=TIMEOUT,
        )
        if r.status_code == 403:
            return PublishResult(False, LABEL,
                                 detail="Blogger returned 403. Check the Blogger API is "
                                        "enabled in that Google Cloud project and the "
                                        "token was issued for the blogger scope.")
        r.raise_for_status()
        data = r.json()
        return PublishResult(
            ok=True, platform=LABEL, url=data.get("url", ""), draft=as_draft,
            detail=("Saved as a Blogger draft — publish it from the Blogger dashboard."
                    if as_draft else "Published live on Blogger."),
        )
    except Exception as e:
        return PublishResult(False, LABEL, detail=f"Blogger post failed: {e}")
