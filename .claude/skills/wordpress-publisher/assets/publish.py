"""
WordPress draft publisher (self-hosted, REST API + Application Password).

Reads an orchestrator output folder (content/ + images/) and creates a DRAFT.
Never publishes live. Works for both toolsvenue.com and toolacademy.com — pass the
matching WP_* env vars for the site you're publishing to.

Usage:
    python publish.py outputs/how-much-does-llm-optimization-cost/

Requires: requests, python-dotenv, markdown
    pip install requests python-dotenv markdown
"""

import os
import sys
import json
import base64
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    import markdown as md_lib
except ImportError:
    md_lib = None

load_dotenv()

WP_SITE_URL = os.environ["WP_SITE_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

_auth = base64.b64encode(f"{WP_USERNAME}:{WP_APP_PASSWORD}".encode()).decode()
HEADERS = {"Authorization": f"Basic {_auth}"}
API = f"{WP_SITE_URL}/wp-json/wp/v2"


def md_to_html(md_text: str) -> str:
    if md_lib:
        return md_lib.markdown(md_text, extensions=["extra", "sane_lists"])
    # crude fallback so the script still runs without the markdown package
    return "<p>" + md_text.replace("\n\n", "</p><p>") + "</p>"


def upload_media(path: Path, alt_text: str = "") -> int | None:
    """Upload one image, return its media id (or None on failure)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        ext = path.suffix.lstrip(".").lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}.get(ext, "application/octet-stream")
        r = requests.post(
            f"{API}/media",
            headers={**HEADERS,
                     "Content-Disposition": f'attachment; filename="{path.name}"',
                     "Content-Type": mime},
            data=data, timeout=60,
        )
        r.raise_for_status()
        mid = r.json()["id"]
        if alt_text:                       # set alt text for image SEO
            requests.post(f"{API}/media/{mid}", headers=HEADERS,
                          json={"alt_text": alt_text}, timeout=30)
        return mid
    except Exception as e:
        print(f"  ! media upload failed for {path.name}: {e}")
        return None


def resolve_terms(names: list[str], taxonomy: str) -> list[int]:
    """Look up tag/category ids by name, creating any that don't exist."""
    ids = []
    for name in names or []:
        try:
            got = requests.get(f"{API}/{taxonomy}", headers=HEADERS,
                               params={"search": name}, timeout=30).json()
            match = next((t for t in got if t["name"].lower() == name.lower()), None)
            if match:
                ids.append(match["id"])
            else:
                created = requests.post(f"{API}/{taxonomy}", headers=HEADERS,
                                        json={"name": name}, timeout=30).json()
                ids.append(created["id"])
        except Exception as e:
            print(f"  ! could not resolve {taxonomy} '{name}': {e}")
    return ids


def publish_draft(folder: Path) -> str:
    content_dir, images_dir = folder / "content", folder / "images"
    meta = json.loads((content_dir / "meta.json").read_text(encoding="utf-8"))
    body_md = (content_dir / "article.md").read_text(encoding="utf-8")

    # 1. images
    alt_map = {}
    alt_path = images_dir / "alt-text.json"
    if alt_path.exists():
        alt_map = json.loads(alt_path.read_text(encoding="utf-8"))

    featured_id = None
    if images_dir.exists():
        for img in sorted(images_dir.glob("*")):
            if img.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                mid = upload_media(img, alt_map.get(img.name, ""))
                if mid and featured_id is None and "featured" in img.name:
                    featured_id = mid

    # 2. taxonomies
    tag_ids = resolve_terms(meta.get("tags"), "tags")
    cat_ids = resolve_terms(meta.get("categories"), "categories")

    # 3. draft
    payload = {
        "title": meta["title"],
        "content": md_to_html(body_md),
        "status": "draft",                 # ALWAYS draft
        "slug": meta.get("slug", ""),
        "excerpt": meta.get("meta_description", ""),
        "tags": tag_ids,
        "categories": cat_ids,
    }
    if featured_id:
        payload["featured_media"] = featured_id

    r = requests.post(f"{API}/posts", headers=HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    post_id = r.json()["id"]
    edit_url = f"{WP_SITE_URL}/wp-admin/post.php?post={post_id}&action=edit"
    print(f"  \u2713 Draft created: {edit_url}")
    if meta.get("schema"):
        print(f"  note: add {meta['schema']} JSON-LD on review (SEO plugin or a block).")
    return edit_url


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python publish.py <output-folder>")
        sys.exit(1)
    publish_draft(Path(sys.argv[1]))
