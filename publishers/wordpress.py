"""
WordPress publisher — your own site, via the REST API + an Application Password.

Ported from `.claude/skills/wordpress-publisher/assets/publish.py`, with two
changes for dashboard use:
  - credentials are passed in per site (`config.wp_credentials`) instead of being
    read from the environment at import time, so a missing key can't crash the app
  - it takes an `Article` in memory rather than an output folder on disk

Phase 5 brought the rest of that skill's publisher across, because a full article
needs it: media upload with alt text, a featured image, the slug, and categories.
An `Article` without any of those (a Lane A backlink post) behaves exactly as
before — the extra fields are all optional.

HARD GUARDRAIL (CLAUDE.md): status is ALWAYS "draft". `as_draft` is accepted for
a consistent publisher signature and is ignored — there is no code path here that
publishes live.
"""

import base64
import mimetypes
from pathlib import Path

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


MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif"}


def _upload_media(api: str, headers: dict, path: Path, alt_text: str = ""):
    """
    Upload one image and return its media id, or None. A picture that won't
    upload is never worth failing the whole draft over — the post still gets
    created, and the result says which image didn't make it.
    """
    try:
        data = path.read_bytes()
        mime = MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] \
            or "application/octet-stream"
        r = requests.post(
            f"{api}/media",
            headers={**headers,
                     "Content-Disposition": f'attachment; filename="{path.name}"',
                     "Content-Type": mime},
            data=data, timeout=TIMEOUT,
        )
        r.raise_for_status()
        media_id = r.json()["id"]
        if alt_text:                    # alt text is what image search actually reads
            requests.post(f"{api}/media/{media_id}", headers=headers,
                          json={"alt_text": alt_text}, timeout=30)
        return media_id
    except Exception:
        return None


def _upload_images(api: str, headers: dict, items: list) -> tuple:
    """
    Upload an article's images. Returns (featured_media_id, uploaded_count,
    [names that failed]).
    """
    featured, uploaded, failed = None, 0, []
    for item in items or []:
        path = Path(item.get("path", ""))
        if not path.exists() or path.suffix.lower() not in MIME:
            continue                    # image briefs are .md — nothing to upload
        media_id = _upload_media(api, headers, path, item.get("alt", ""))
        if media_id is None:
            failed.append(path.name)
            continue
        uploaded += 1
        if featured is None and item.get("featured"):
            featured = media_id
    return featured, uploaded, failed


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

    featured, uploaded, failed_images = _upload_images(api, headers, article.images)

    payload = {
        "title": article.title,
        "content": md_to_html(article.body_markdown),
        "status": "draft",              # ALWAYS draft — see the module docstring
        "excerpt": article.summary,
        "tags": _resolve_terms(api, headers, clean_tags(article.tags, limit=6), "tags"),
    }
    if article.slug:
        payload["slug"] = article.slug
    if article.categories:
        payload["categories"] = _resolve_terms(api, headers, article.categories,
                                               "categories")
    if featured:
        payload["featured_media"] = featured

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
        detail = "Draft created — review it in WP Admin and publish it yourself."
        if uploaded:
            detail += (f" {uploaded} image(s) uploaded to the media library"
                       f"{' (featured image set)' if featured else ''};"
                       " place the in-body ones as you review.")
        if failed_images:
            detail += f" These images wouldn't upload: {', '.join(failed_images)}."
        return PublishResult(ok=True, platform=LABEL, url=edit_url, draft=True,
                             detail=detail)
    except Exception as e:
        return PublishResult(False, LABEL, detail=f"WordPress draft failed: {e}")
