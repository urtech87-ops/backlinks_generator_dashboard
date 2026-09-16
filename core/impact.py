"""
Before/after impact tracking (Phase 17).

A page enters this file two ways:
  (a) automatically, the moment the Content or Backlink agent generates
      something for it, or
  (b) manually, via "I worked on this page" for work done outside the tool.

Either way, the FIRST time a page is seen its current metrics are snapshotted
as the baseline — impressions, clicks, average position, and the date — read
from whatever the sidebar's "Refresh live data" last cached (`ui.data`'s
`performance_metrics()` / `last_refreshed()`). This module never calls Google
itself; that would reopen the exact "call Google in exactly one place" rule
`ui/data.py` exists to enforce.

Honesty rules this module exists to enforce, not just state in the UI:
  - the baseline is set ONCE per page — generating a second article or link
    for an already-tracked page must not overwrite the point it actually
    started being worked on.
  - "no live data cached yet" and "measured, and it's zero" are kept apart
    (`baseline_live` / `has_latest`) rather than collapsed into a silent 0,
    the same distinction the rest of this app draws everywhere else.
  - a comparison under ~14 days is flagged, never presented as a verdict.
"""

import csv
import datetime as dt

import pandas as pd

from . import config

PATH = config.ROOT / "data" / "tracked_pages.csv"

FIELDS = ["site", "url", "reason", "added_at", "baseline_date",
          "baseline_impressions", "baseline_clicks", "baseline_position",
          "baseline_live"]

REASON_ARTICLE = "article"
REASON_BACKLINK = "backlink"
REASON_MANUAL = "manual"

REASON_LABEL = {
    REASON_ARTICLE: "Article generated",
    REASON_BACKLINK: "Backlink built",
    REASON_MANUAL: "Worked on by hand",
}

# Under this many days, a change is noise more often than signal — SEO moves
# slowly and unevenly. The UI shows the raw numbers either way and never
# prints a confident verdict itself; this is just the threshold for the
# caution line.
MIN_DAYS_FOR_A_READ = 14


def _load_raw() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=FIELDS)
    try:
        df = pd.read_csv(PATH)
    except Exception:
        return pd.DataFrame(columns=FIELDS)
    for col in FIELDS:
        if col not in df.columns:
            df[col] = ""
    return df.fillna("")


def is_tracked(site_key: str, url: str) -> bool:
    df = _load_raw()
    if df.empty:
        return False
    key = (url or "").rstrip("/")
    return bool(((df["site"] == site_key) & (df["url"].str.rstrip("/") == key)).any())


def start_tracking(site_key: str, url: str, reason: str, baseline: dict,
                    baseline_date: str = "") -> bool:
    """
    Snapshot this page's current metrics as its baseline, unless it's already
    tracked. Returns True when a new row was written, False when the page was
    already tracked — a no-op, not an error, so every call site can call this
    unconditionally every time an article/backlink is generated.
    """
    url = (url or "").strip()
    if not url or is_tracked(site_key, url):
        return False
    baseline = baseline or {}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not PATH.exists()
    with open(PATH, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "site": site_key, "url": url, "reason": reason,
            "added_at": dt.datetime.now().isoformat(timespec="seconds"),
            "baseline_date": baseline_date or dt.date.today().isoformat(),
            "baseline_impressions": int(baseline.get("impressions", 0) or 0),
            "baseline_clicks": int(baseline.get("clicks", 0) or 0),
            "baseline_position": float(baseline.get("position", 0) or 0),
            "baseline_live": bool(baseline),
        })
    return True


def tracked_pages(site_key: str = "") -> pd.DataFrame:
    """Every tracked page for a site, newest-added first."""
    df = _load_raw()
    if site_key:
        df = df[df["site"] == site_key]
    if df.empty:
        return df
    return df.sort_values("added_at", ascending=False).reset_index(drop=True)


def days_elapsed(baseline_date: str, as_of: str = "") -> int:
    try:
        base = dt.date.fromisoformat(str(baseline_date)[:10])
    except ValueError:
        return 0
    try:
        end = dt.date.fromisoformat(as_of[:10]) if as_of else dt.date.today()
    except ValueError:
        end = dt.date.today()
    return max((end - base).days, 0)


def compare(site_key: str, url: str, latest: dict, latest_date: str = "") -> dict | None:
    """
    One tracked page's baseline vs. latest. `latest` is {impressions, clicks,
    position} for this URL from whatever the sidebar's Refresh live data most
    recently cached — {} before that's ever been pressed (or if this page
    simply has no measured impressions right now), in which case this
    returns baseline-only with `has_latest=False` rather than inventing a
    zero "latest".
    """
    df = _load_raw()
    if df.empty:
        return None
    key = (url or "").rstrip("/")
    rows = df[(df["site"] == site_key) & (df["url"].str.rstrip("/") == key)]
    if rows.empty:
        return None
    row = rows.iloc[0]

    baseline = {
        "impressions": int(row["baseline_impressions"] or 0),
        "clicks": int(row["baseline_clicks"] or 0),
        "position": float(row["baseline_position"] or 0),
    }
    elapsed = days_elapsed(row["baseline_date"], latest_date)
    result = {
        "site": site_key, "url": url, "reason": row["reason"],
        "baseline": baseline, "baseline_date": str(row["baseline_date"]),
        "baseline_live": str(row.get("baseline_live", "")).strip() == "True",
        "days_elapsed": elapsed,
        "too_early": elapsed < MIN_DAYS_FOR_A_READ,
        "has_latest": bool(latest),
    }
    if latest:
        result["latest"] = latest
        result["latest_date"] = latest_date
        result["change"] = {
            "impressions": int(latest.get("impressions", 0) or 0) - baseline["impressions"],
            "clicks": int(latest.get("clicks", 0) or 0) - baseline["clicks"],
            "position": round(float(latest.get("position", 0) or 0) - baseline["position"], 1),
        }
    return result
