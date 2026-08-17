"""
The backlink tracker — a plain CSV in `data/`, so it survives restarts, opens
in a spreadsheet, and is trivially auditable.

One row per publish attempt (failures included — a link you *thought* you built
is worse than one you know failed). Lane B in Phase 4 adds its own stages to the
same file via the `status` column.
"""

import csv
import datetime as dt
from pathlib import Path

import pandas as pd

from . import config

PATH: Path = config.ROOT / "data" / "backlinks.csv"

FIELDS = ["logged_at", "site", "target_url", "platform", "status", "post_url",
          "title", "detail"]

# What the `status` column can say, in plain language for the UI.
STATUS_LABEL = {
    "live": "Live",
    "draft": "Draft — needs your click",
    "failed": "Failed",
}


def log(site_key: str, target_url: str, platform: str, status: str,
        post_url: str = "", title: str = "", detail: str = "") -> None:
    """Append one row. Never raises — a tracker write must not lose a publish."""
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        new_file = not PATH.exists()
        with open(PATH, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({
                "logged_at": dt.datetime.now().isoformat(timespec="seconds"),
                "site": site_key,
                "target_url": target_url,
                "platform": platform,
                "status": status,
                "post_url": post_url,
                "title": title,
                "detail": detail,
            })
    except Exception:
        pass


def log_result(site_key: str, target_url: str, result, title: str = "") -> None:
    """Log a `publishers.PublishResult` straight from the publish call."""
    if not result.ok:
        status = "failed"
    elif result.draft:
        status = "draft"
    else:
        status = "live"
    log(site_key, target_url, result.platform, status,
        post_url=result.url, title=title, detail=result.detail)


def load(site_key: str = "") -> pd.DataFrame:
    """
    The tracker as a DataFrame, newest first. Empty (with the right columns) when
    nothing has been published yet, so callers can treat it uniformly.
    """
    if not PATH.exists():
        return pd.DataFrame(columns=FIELDS)
    try:
        df = pd.read_csv(PATH)
    except Exception:
        return pd.DataFrame(columns=FIELDS)
    for col in FIELDS:                       # tolerate an older/partial file
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    if site_key:
        df = df[df["site"] == site_key]
    return df.sort_values("logged_at", ascending=False).reset_index(drop=True)


def summary(site_key: str = "") -> dict:
    """Headline counts for the tracker's metric row."""
    df = load(site_key)
    if df.empty:
        return {"total": 0, "live": 0, "drafts": 0, "failed": 0, "pages": 0}
    counts = df["status"].value_counts().to_dict()
    return {
        "total": len(df),
        "live": int(counts.get("live", 0)),
        "drafts": int(counts.get("draft", 0)),
        "failed": int(counts.get("failed", 0)),
        "pages": int(df[df["status"] != "failed"]["target_url"].nunique()),
    }
