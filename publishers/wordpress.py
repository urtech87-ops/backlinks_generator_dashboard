"""
WordPress publisher — your own site, via the REST API + an Application Password.

Ported from `.claude/skills/wordpress-publisher/assets/publish.py`, with two
changes for dashboard use:
  - credentials are passed in per site (`config.wp_credentials`) instead of being
    read from the environment at import time, so a missing key can't crash the app
  - it takes an `Article` in memory rather than an output folder on disk

HARD GUARDRAIL (CLAUDE.md): status is ALWAYS "draft". `as_draft` is accepted for
a consistent publisher signature and is ignored — there is no code path here that
publishes live.
"""

import base64

import requests

from core import config
from .base import Article, PublishResult, clean_tags, md_to_html, missing_keys

LABEL = "Your WordPress"
TIMEOUT = 60


def _creds(site) -> dict:
    return config.wp_credentials(site) if site else {"url": "", "username": "",
                                                     "app_password": ""}


def missing(site=None) -> list:
    """Which settings are still empty for this site. [] means ready."""
    wp = _creds(site)
    return missing_keys([
        ("WordPress site URL", bool(wp["url"])),
        ("WordPress username", bool(wp["username"])),
        ("WordPress application password", bool(wp["app_password"])),
    ])


def _headers(wp: dict) -> dict:
    token = base64.b64encode(f"{wp['username']}:{wp['app_password']}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _resolve_terms(api: str, headers: dict, names: list, taxonomy: str) -> list:
    """Look up tag/category ids by name, creating any that don't exist yet."""
    ids = []
    for name in names or []:
        try:
            got = requests.get(f"{api}/{taxonomy}", headers=headers,
                               params={"search": name}, timeout=30).json()
            match = next((t for t in got if t["name"].lower() == name.lower()), None)
            if match:
                ids.append(match["id"])
            else:
                created = requests.post(f"{api}/{taxonomy}", headers=headers,
                                        json={"name": name}, timeout=30).json()
                if "id" in created:
                    ids.append(created["id"])
        except Exception:
            continue        # a missing tag is never worth failing the post over
    return ids


def publish(article: Article, site=None, as_draft: bool = True) -> PublishResult:
    """Create a DRAFT post on the site's own WordPress. Never publishes live."""
    gaps = missing(site)
    if gaps:
        return PublishResult(False, LABEL, detail=f"Not set up yet — missing: {', '.join(gaps)}.")

    wp = _creds(site)
    api = f"{wp['url'].rstrip('/')}/wp-json/wp/v2"
    headers = _headers(wp)

    payload = {
        "title": article.title,
        "content": md_to_html(article.body_markdown),
        "status": "draft",              # ALWAYS draft — see the module docstring
        "excerpt": article.summary,
        "tags": _resolve_terms(api, headers, clean_tags(article.tags, limit=6), "tags"),
    }

    try:
        r = requests.post(f"{api}/posts", headers=headers, json=payload, timeout=TIMEOUT)
        if r.status_code == 401:
            return PublishResult(False, LABEL,
                                 detail="WordPress rejected the login (401). Use an "
                                        "Application Password, not the account password.")
        if r.status_code == 404:
            return PublishResult(False, LABEL,
                                 detail=f"No REST API at {api}. Check the site URL and "
                                        "that permalinks aren't set to Plain.")
        r.raise_for_status()
        post_id = r.json()["id"]
        edit_url = f"{wp['url'].rstrip('/')}/wp-admin/post.php?post={post_id}&action=edit"
        return PublishResult(
            ok=True, platform=LABEL, url=edit_url, draft=True,
            detail="Draft created — review it in WP Admin and publish it yourself.",
        )
    except Exception as e:
        return PublishResult(False, LABEL, detail=f"WordPress draft failed: {e}")
