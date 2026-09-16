"""
Saved items — a manual, on-disk archive of generated content (Phase 17).

Generation costs money (OpenRouter calls, web research), so anything the
Content or Backlink agent writes has to survive between sessions even if it's
never published. Saving is MANUAL only — nothing in this module is ever
called except by a "Save" button the user pressed; nothing here auto-saves a
draft just because it was generated.

Mirrors `core/tracker.py`'s spirit (plain files under `data/`, readable
outside this app) but not its exact shape: a saved item can be a full
article, so this writes one JSON file per item — organized by site and date,
per the brief — plus a light CSV index (`data/saved_items/index.csv`) so the
browsing view can list everything without opening every file just to show a
title and a date.
"""

import csv
import datetime as dt
import json
import re
from pathlib import Path

from . import config

ROOT = config.ROOT / "data" / "saved_items"
INDEX_PATH = ROOT / "index.csv"

INDEX_FIELDS = ["id", "site", "type", "title", "target_url", "model",
                "format", "platform", "saved_at", "path"]

TYPE_ARTICLE = "article"
TYPE_BACKLINK = "backlink"

TYPE_LABEL = {TYPE_ARTICLE: "Article", TYPE_BACKLINK: "Backlink"}


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s-]", "", (text or "").lower())
    parts = [p for p in re.split(r"[\s-]+", cleaned) if p]
    return "-".join(parts[:6]) or "untitled"


def save_item(site_key: str, item_type: str, title: str, content: str, *,
              target_url: str = "", model: str = "", fmt: str = "",
              platform: str = "", extra: dict | None = None) -> dict:
    """
    Persist one generated item to disk, organized `data/saved_items/<site>/
    <YYYY-MM-DD>/`, and add it to the CSV index. Returns the full payload
    written (including its `id` and `path`), so the caller can confirm the
    save and, for `_append_index`'s sake, so the UI never has to guess the id.
    """
    now = dt.datetime.now()
    day_dir = ROOT / site_key / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    item_id = f"{now.strftime('%H%M%S')}-{_slug(title)}"
    path = day_dir / f"{item_id}.json"
    # Two saves in the same second, same title, would otherwise collide.
    n = 2
    while path.exists():
        path = day_dir / f"{item_id}-{n}.json"
        n += 1

    payload = {
        "id": path.stem, "site": site_key, "type": item_type, "title": title,
        "content": content, "target_url": target_url, "model": model,
        "format": fmt, "platform": platform,
        "saved_at": now.isoformat(timespec="seconds"),
        **(extra or {}),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _append_index(payload, path)
    return payload


def _append_index(payload: dict, path: Path) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    new_file = not INDEX_PATH.exists()
    try:
        rel = str(path.relative_to(config.ROOT))
    except ValueError:
        rel = str(path)
    with open(INDEX_PATH, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "id": payload["id"], "site": payload["site"], "type": payload["type"],
            "title": payload["title"], "target_url": payload.get("target_url", ""),
            "model": payload.get("model", ""), "format": payload.get("format", ""),
            "platform": payload.get("platform", ""), "saved_at": payload["saved_at"],
            "path": rel,
        })


def list_items(site_key: str = "", item_type: str = "") -> list[dict]:
    """
    Every saved item's index row, newest first — title/date/type/target only,
    never the full content (that's `load_item()`, called only when one is
    opened, so browsing a long list stays cheap).
    """
    if not INDEX_PATH.exists():
        return []
    try:
        with open(INDEX_PATH, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        return []
    if site_key:
        rows = [r for r in rows if r.get("site") == site_key]
    if item_type:
        rows = [r for r in rows if r.get("type") == item_type]
    rows.sort(key=lambda r: r.get("saved_at", ""), reverse=True)
    return rows


def load_item(path) -> dict | None:
    """The full saved item (including its content) from an index row's `path`."""
    p = Path(path)
    if not p.is_absolute():
        p = config.ROOT / p
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
