"""
Phase 17 — saving generated items, and before/after impact tracking.

Both are plain, on-disk modules (`core.saved_items`, `core.impact`) with no
Streamlit or network dependency, so these are direct unit tests rather than
AppTest passes — the fastest way to pin down the actual contract each
`ui/views/*.py` caller relies on: a save must reload byte-for-byte, a
baseline must be set exactly once, and a comparison's numbers/dates/caution
must be arithmetically right.
"""

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import impact, saved_items  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch, tmp_path):
    """Every test gets its own throwaway files — never the repo's real
    `data/saved_items/` or `data/tracked_pages.csv`."""
    monkeypatch.setattr(saved_items, "ROOT", tmp_path / "saved_items")
    monkeypatch.setattr(saved_items, "INDEX_PATH", tmp_path / "saved_items" / "index.csv")
    monkeypatch.setattr(impact, "PATH", tmp_path / "tracked_pages.csv")


# ── Feature 1: saving persists + reloads ────────────────────────────────────
def test_save_item_persists_and_reloads():
    payload = saved_items.save_item(
        "toolsvenue", saved_items.TYPE_ARTICLE, "How to compress a JPEG",
        "# How to compress a JPEG\n\nFull article body here.",
        target_url="", model="anthropic/claude-3.5", fmt="toolsvenue_html",
        extra={"topic": "compress a jpeg"},
    )
    assert Path(payload["id"])  # got an id back

    items = saved_items.list_items(site_key="toolsvenue")
    assert len(items) == 1
    row = items[0]
    assert row["title"] == "How to compress a JPEG"
    assert row["type"] == saved_items.TYPE_ARTICLE
    assert row["model"] == "anthropic/claude-3.5"

    full = saved_items.load_item(row["path"])
    assert full is not None
    assert full["content"] == "# How to compress a JPEG\n\nFull article body here."
    assert full["topic"] == "compress a jpeg"


def test_save_item_survives_a_fresh_process_read():
    """The point of writing to disk rather than session state: a brand new
    read (no shared in-memory object) still finds it."""
    saved_items.save_item("toolshall", saved_items.TYPE_BACKLINK, "Guest post draft",
                          "Body text", target_url="https://toolshall.com/x",
                          platform="dev.to")
    items = saved_items.list_items()  # no filter — everything
    assert any(r["title"] == "Guest post draft" and r["platform"] == "dev.to"
               for r in items)


def test_list_items_filters_by_site_and_type():
    saved_items.save_item("toolsvenue", saved_items.TYPE_ARTICLE, "A", "body a")
    saved_items.save_item("toolshall", saved_items.TYPE_BACKLINK, "B", "body b")

    only_tv = saved_items.list_items(site_key="toolsvenue")
    assert [r["title"] for r in only_tv] == ["A"]

    only_backlinks = saved_items.list_items(item_type=saved_items.TYPE_BACKLINK)
    assert [r["title"] for r in only_backlinks] == ["B"]


def test_load_item_returns_none_for_a_missing_file():
    assert saved_items.load_item("saved_items/nope/does-not-exist.json") is None


# ── Feature 2: starting tracking snapshots a baseline ───────────────────────
def test_start_tracking_snapshots_baseline():
    started = impact.start_tracking(
        "toolsvenue", "https://toolsvenue.com/json-formatter/", impact.REASON_BACKLINK,
        {"impressions": 340, "clicks": 12, "position": 8.4}, baseline_date="2026-08-01",
    )
    assert started is True
    assert impact.is_tracked("toolsvenue", "https://toolsvenue.com/json-formatter/")

    rows = impact.tracked_pages("toolsvenue")
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["reason"] == impact.REASON_BACKLINK
    assert int(row["baseline_impressions"]) == 340
    assert int(row["baseline_clicks"]) == 12
    assert float(row["baseline_position"]) == 8.4
    assert row["baseline_date"] == "2026-08-01"


def test_a_page_only_gets_one_baseline_ever():
    """Generating a second article/backlink for an already-tracked page must
    not overwrite the point it actually started being worked on."""
    url = "https://toolsvenue.com/pdf-merger/"
    impact.start_tracking("toolsvenue", url, impact.REASON_ARTICLE,
                          {"impressions": 100, "clicks": 5, "position": 15.0},
                          baseline_date="2026-08-01")
    started_again = impact.start_tracking(
        "toolsvenue", url, impact.REASON_BACKLINK,
        {"impressions": 9999, "clicks": 999, "position": 1.0}, baseline_date="2026-09-01",
    )
    assert started_again is False

    rows = impact.tracked_pages("toolsvenue")
    assert len(rows) == 1
    assert int(rows.iloc[0]["baseline_impressions"]) == 100   # the FIRST snapshot
    assert rows.iloc[0]["baseline_date"] == "2026-08-01"


def test_baseline_with_no_cached_data_is_marked_not_live():
    """No performance cached yet at tracking time -> baseline is 0, but the
    module remembers that 0 wasn't a real measurement."""
    impact.start_tracking("toolshall", "https://toolshall.com/new-page/",
                          impact.REASON_MANUAL, {}, baseline_date="2026-09-01")
    cmp = impact.compare("toolshall", "https://toolshall.com/new-page/", {}, "")
    assert cmp["baseline_live"] is False
    assert cmp["baseline"]["impressions"] == 0


# ── Feature 2: the comparison's change + elapsed days ───────────────────────
def test_compare_computes_change_and_elapsed_days_correctly():
    impact.start_tracking(
        "toolsvenue", "https://toolsvenue.com/csv-viewer/", impact.REASON_BACKLINK,
        {"impressions": 200, "clicks": 10, "position": 18.0}, baseline_date="2026-08-01",
    )
    cmp = impact.compare(
        "toolsvenue", "https://toolsvenue.com/csv-viewer/",
        {"impressions": 350, "clicks": 22, "position": 11.5}, "2026-09-16",
    )
    assert cmp is not None
    assert cmp["has_latest"] is True
    assert cmp["days_elapsed"] == 46          # 1 Aug -> 16 Sep 2026
    assert cmp["change"]["impressions"] == 150
    assert cmp["change"]["clicks"] == 12
    assert cmp["change"]["position"] == pytest.approx(-6.5)   # moved up (lower is better)


def test_compare_with_no_latest_data_says_so_instead_of_inventing_a_zero():
    impact.start_tracking(
        "toolsvenue", "https://toolsvenue.com/no-refresh-yet/", impact.REASON_ARTICLE,
        {"impressions": 50, "clicks": 2, "position": 30.0}, baseline_date="2026-09-01",
    )
    cmp = impact.compare("toolsvenue", "https://toolsvenue.com/no-refresh-yet/", {}, "")
    assert cmp["has_latest"] is False
    assert "latest" not in cmp
    assert "change" not in cmp
    assert cmp["baseline"]["impressions"] == 50   # baseline itself is untouched


def test_compare_returns_none_for_an_untracked_page():
    assert impact.compare("toolsvenue", "https://toolsvenue.com/never-tracked/", {}) is None


# ── Feature 2: the <14-day caution ───────────────────────────────────────────
def test_under_fourteen_days_is_flagged_too_early():
    impact.start_tracking(
        "toolsvenue", "https://toolsvenue.com/fresh-link/", impact.REASON_BACKLINK,
        {"impressions": 10, "clicks": 1, "position": 25.0}, baseline_date="2026-09-10",
    )
    cmp = impact.compare(
        "toolsvenue", "https://toolsvenue.com/fresh-link/",
        {"impressions": 12, "clicks": 1, "position": 24.0}, "2026-09-16",
    )
    assert cmp["days_elapsed"] == 6
    assert cmp["too_early"] is True


def test_fourteen_days_or_more_is_not_flagged_too_early():
    impact.start_tracking(
        "toolsvenue", "https://toolsvenue.com/settled-link/", impact.REASON_BACKLINK,
        {"impressions": 10, "clicks": 1, "position": 25.0}, baseline_date="2026-09-01",
    )
    cmp = impact.compare(
        "toolsvenue", "https://toolsvenue.com/settled-link/",
        {"impressions": 40, "clicks": 5, "position": 15.0}, "2026-09-16",
    )
    assert cmp["days_elapsed"] == 15
    assert cmp["too_early"] is False


def test_days_elapsed_defaults_to_today_with_no_latest_date():
    today = dt.date.today().isoformat()
    assert impact.days_elapsed(today) == 0
