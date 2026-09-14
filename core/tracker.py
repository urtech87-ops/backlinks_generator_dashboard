"""
The backlink tracker — a plain CSV in `data/`, so it survives restarts, opens
in a spreadsheet, and is trivially auditable.

One row per event (failures included — a link you *thought* you built is worse
than one you know failed). All three lanes share this one file:

  lane="owned"      Lane A: one row per publish attempt to a platform you own.
  lane="guest"      Lane B: one row per *stage change* for a guest-post prospect,
                    so the file is an append-only history — prospected → pitched →
                    accepted → live — and `guest_board()` folds it into the current
                    stage per prospect. For guest rows the `platform` column holds
                    the host's domain.
  lane="community"  A manual tracker for community/directory submissions (Reddit,
                    Hacker News, Product Hunt, AlternativeTo, an "awesome" list...).
                    Same append-only-history-folded-into-a-board shape as Lane B,
                    but nothing here is ever posted anywhere — every row is typed
                    in by hand. For community rows the `platform` column holds the
                    platform/directory name.
"""

import csv
import datetime as dt
from pathlib import Path

import pandas as pd

from . import config

PATH: Path = config.ROOT / "data" / "backlinks.csv"

FIELDS = ["logged_at", "site", "lane", "target_url", "platform", "status",
          "post_url", "title", "detail", "contact"]

LANE_OWNED = "owned"
LANE_GUEST = "guest"
LANE_COMMUNITY = "community"

# The stages a guest prospect moves through, in order. "declined" is a real
# outcome, not a failure — most pitches get one, and hiding them would make the
# board lie about how outreach actually goes.
GUEST_STAGES = ["prospected", "pitched", "accepted", "declined", "live"]

# The stages a manual community/directory submission moves through.
COMMUNITY_STAGES = ["planned", "submitted", "live"]

# What the `status` column can say, in plain language for the UI.
STATUS_LABEL = {
    # Lane A
    "live": "Live",
    "draft": "Draft — needs your click",
    "failed": "Failed",
    # Lane B
    "prospected": "Prospected — not contacted",
    "pitched": "Pitch sent — waiting",
    "accepted": "Accepted — host said yes",
    "declined": "Declined",
    # Community tracker
    "planned": "Planned",
    "submitted": "Submitted — waiting",
}

GUEST_STAGE_HELP = {
    "prospected": "Found and shortlisted. Nothing has been sent.",
    "pitched": "You approved and sent the pitch. The host decides next.",
    "accepted": "The host said yes. Send the draft they asked for.",
    "declined": "A no, or no reply worth chasing. Keep it — it stops you pitching twice.",
    "live": "The host published it. The link exists.",
}

COMMUNITY_STAGE_HELP = {
    "planned": "On your list. Nothing posted yet.",
    "submitted": "You've posted or submitted it — waiting to see if it sticks.",
    "live": "It's up: approved, live, or listed.",
}

# A starting point for the platform picker — free text is always allowed too.
COMMUNITY_PLATFORM_PRESETS = [
    "Reddit", "Hacker News", "Product Hunt", "AlternativeTo",
    "An \"awesome\" list", "Other directory or community",
]


def _ensure_header() -> None:
    """
    Bring an older CSV up to the current columns before appending.

    Lane A wrote a narrower header, and appending new fields to that file would
    silently misalign every column. So when the header differs, rewrite the file
    once with the full set, defaulting old rows to the owned lane.
    """
    if not PATH.exists():
        return
    try:
        with open(PATH, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames == FIELDS:
                return
            rows = list(reader)
    except Exception:
        return

    for row in rows:
        row.setdefault("lane", "")
        if not (row.get("lane") or "").strip():
            row["lane"] = LANE_OWNED          # everything written before Lane B
    try:
        with open(PATH, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (row.get(k) or "") for k in FIELDS})
    except Exception:
        pass


def log(site_key: str, target_url: str, platform: str, status: str,
        post_url: str = "", title: str = "", detail: str = "",
        lane: str = LANE_OWNED, contact: str = "", logged_at: str = "") -> None:
    """
    Append one row. Never raises — a tracker write must not lose a publish.

    `logged_at` defaults to now; the community tracker passes a user-chosen
    date instead, since a submission is often logged after the fact.
    """
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        _ensure_header()
        new_file = not PATH.exists()
        with open(PATH, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({
                "logged_at": logged_at or dt.datetime.now().isoformat(timespec="seconds"),
                "site": site_key,
                "lane": lane,
                "target_url": target_url,
                "platform": platform,
                "status": status,
                "post_url": post_url,
                "title": title,
                "detail": detail,
                "contact": contact,
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
        post_url=result.url, title=title, detail=result.detail,
        lane=LANE_OWNED)


def log_guest(site_key: str, target_url: str, domain: str, status: str,
              title: str = "", detail: str = "", contact: str = "",
              post_url: str = "") -> None:
    """
    Record one guest-outreach stage change. Called only from a human action in
    the UI — finding a prospect never writes here on its own.
    """
    log(site_key, target_url, domain, status, post_url=post_url, title=title,
        detail=detail, lane=LANE_GUEST, contact=contact)


def log_community(site_key: str, target_url: str, platform: str, status: str,
                   date: str = "", detail: str = "", post_url: str = "") -> None:
    """
    Record one community/directory submission or stage change (planned →
    submitted → live). This is a pure log — nothing calls it except a human
    filling in the form on the Backlinks page. `platform` is a name, not an
    account: "Reddit", "Hacker News", "Product Hunt", an "awesome" list, etc.
    """
    log(site_key, target_url, platform, status, post_url=post_url,
        detail=detail, lane=LANE_COMMUNITY, logged_at=date)


def load(site_key: str = "", lane: str = "") -> pd.DataFrame:
    """
    The tracker as a DataFrame, newest first. Empty (with the right columns) when
    nothing has been logged yet, so callers can treat it uniformly.

    `lane` filters to one lane; blank returns both. Rows written before Lane B
    existed have no lane and count as owned.
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
    df["lane"] = df["lane"].replace("", LANE_OWNED)
    if site_key:
        df = df[df["site"] == site_key]
    if lane:
        df = df[df["lane"] == lane]
    # Two rows can share a timestamp (log a stage, log the next one a moment
    # later), so file order is the real tie-breaker: reverse first, then sort
    # with a stable kind, and the newest row is genuinely first.
    df = df.iloc[::-1]
    return (df.sort_values("logged_at", ascending=False, kind="stable")
              .reset_index(drop=True))


def summary(site_key: str = "", lane: str = LANE_OWNED) -> dict:
    """Headline counts for Lane A's metric row."""
    df = load(site_key, lane=lane)
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


def link_history(site_key: str, target_url: str, lane: str = LANE_OWNED) -> dict:
    """
    How many times this page already has a non-failed link attempt logged, and
    when the most recent one was. This is the active half of the tracker: the
    Backlinks page warns with it before you publish again, the same way Lane B
    warns before you re-pitch a domain — informational only, never a block.
    """
    df = load(site_key, lane=lane)
    if df.empty:
        return {"count": 0, "latest": ""}
    prior = df[(df["target_url"] == target_url) & (df["status"] != "failed")]
    if prior.empty:
        return {"count": 0, "latest": ""}
    # `load()` already sorts newest first, so row 0 is the most recent.
    return {"count": int(len(prior)), "latest": str(prior.iloc[0]["logged_at"])[:10]}


# ── Lane B: fold the history into one row per prospect ─────────────────────
def guest_board(site_key: str = "") -> pd.DataFrame:
    """
    One row per (host domain, target page) with its CURRENT stage, taken from
    the newest row for that pair. Columns: domain, target_url, stage, contact,
    post_url, title, detail, first_seen, updated.
    """
    columns = ["domain", "target_url", "stage", "contact", "post_url", "title",
               "detail", "first_seen", "updated"]
    df = load(site_key, lane=LANE_GUEST)
    if df.empty:
        return pd.DataFrame(columns=columns)

    rows = []                                    # `df` is newest-first from load()
    for (domain, target_url), group in df.groupby(["platform", "target_url"],
                                                  sort=False):
        newest = group.iloc[0]

        def latest(col: str) -> str:
            """The most recent non-empty value — a stage change needn't repeat it."""
            values = [v for v in group[col].tolist() if str(v).strip()]
            return str(values[0]) if values else ""

        rows.append({
            "domain": domain,
            "target_url": target_url,
            "stage": newest["status"],
            "contact": latest("contact"),
            "post_url": latest("post_url"),
            "title": latest("title"),
            "detail": str(newest["detail"]),
            "first_seen": str(group.iloc[-1]["logged_at"]),
            "updated": str(newest["logged_at"]),
        })

    board = pd.DataFrame(rows, columns=columns)
    order = {stage: i for i, stage in enumerate(GUEST_STAGES)}
    board["_order"] = board["stage"].map(order).fillna(len(GUEST_STAGES))
    return (board.sort_values(["_order", "updated"], ascending=[True, False])
                 .drop(columns="_order").reset_index(drop=True))


def guest_summary(site_key: str = "") -> dict:
    """How many prospects sit in each stage right now, plus the total."""
    board = guest_board(site_key)
    counts = {stage: 0 for stage in GUEST_STAGES}
    if not board.empty:
        for stage, count in board["stage"].value_counts().items():
            counts[stage] = int(count)
    counts["total"] = int(len(board))
    return counts


# ── Community tracker: fold the history into one row per submission ────────
def community_board(site_key: str = "") -> pd.DataFrame:
    """
    One row per (platform, target page) with its CURRENT stage, taken from the
    newest row for that pair. Same fold as `guest_board()` — a submission can
    move planned → submitted → live over several visits to the page, and this
    is what turns that history into one line per submission.
    """
    columns = ["platform", "target_url", "stage", "post_url", "detail",
               "first_seen", "updated"]
    df = load(site_key, lane=LANE_COMMUNITY)
    if df.empty:
        return pd.DataFrame(columns=columns)

    rows = []                                    # `df` is newest-first from load()
    for (platform, target_url), group in df.groupby(["platform", "target_url"],
                                                     sort=False):
        newest = group.iloc[0]

        def latest(col: str) -> str:
            """The most recent non-empty value — an update needn't repeat it."""
            values = [v for v in group[col].tolist() if str(v).strip()]
            return str(values[0]) if values else ""

        rows.append({
            "platform": platform,
            "target_url": target_url,
            "stage": newest["status"],
            "post_url": latest("post_url"),
            "detail": str(newest["detail"]),
            "first_seen": str(group.iloc[-1]["logged_at"]),
            "updated": str(newest["logged_at"]),
        })

    board = pd.DataFrame(rows, columns=columns)
    order = {stage: i for i, stage in enumerate(COMMUNITY_STAGES)}
    board["_order"] = board["stage"].map(order).fillna(len(COMMUNITY_STAGES))
    return (board.sort_values(["_order", "updated"], ascending=[True, False])
                 .drop(columns="_order").reset_index(drop=True))


def community_summary(site_key: str = "") -> dict:
    """How many submissions sit in each stage right now, plus the total."""
    board = community_board(site_key)
    counts = {stage: 0 for stage in COMMUNITY_STAGES}
    if not board.empty:
        for stage, count in board["stage"].value_counts().items():
            counts[stage] = int(count)
    counts["total"] = int(len(board))
    return counts

