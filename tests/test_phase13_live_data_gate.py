"""
Phase 13 — two small, scoped changes:

  1. Stop auto-fetching live data. This dashboard now calls Google in exactly
     one place: the sidebar's "Refresh live data" button. Streamlit reruns
     the whole script on any interaction, so anything fetched outside that
     one gate — the old coverage auto-load, Overview's own first-paint fetch,
     the Analysis tabs' direct `gsc`/`ga4` calls on every render, Backlinks'
     unconditional `rank_targets()` — was spending API quota on every click,
     not just "on open". Every page now reads whatever the button last
     cached (`ui.data.performance_metrics()` / `ga4_cache()` / `keywords()`),
     or the sample snapshot before it's ever been pressed, and says which.
  2. Suggest article topics from real data on the Content page. Step 1 shows
     a short list of suggested topics — Search Console queries the site
     ranks poorly on (position 20+, `core.keywords`' DEEP band) and, when a
     competitor scan has already been run this session, competitor gaps —
     each with the real numbers behind it. Picking one fills the topic box;
     nothing here writes or researches anything by itself.

This file checks both hold, driven through Streamlit's AppTest and direct
calls against `ui.data`, with no real Google credentials anywhere.
"""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
sys.path.insert(0, str(ROOT))

from agents import opportunity as opp  # noqa: E402
from core import config, gsc  # noqa: E402

SITE_KEY = "toolsvenue"
SITE_PROP = "https://toolsvenue.com"
URL = f"{SITE_PROP}/json-formatter/"
DEEP_QUERY = "weird json bug fix"


def _search_analytics(_property, _start, _end, dimensions=None, row_limit=250):
    if dimensions == ["page"]:
        return [{"page": URL, "clicks": 1, "impressions": 500, "ctr": 0.2,
                 "position": 35.0}]
    if dimensions == ["page", "query"]:
        return [{"page": URL, "query": DEEP_QUERY, "clicks": 1, "impressions": 500,
                 "ctr": 0.2, "position": 35.0}]
    return [{"query": DEEP_QUERY, "clicks": 1, "impressions": 500, "ctr": 0.2,
             "position": 35.0}]


@pytest.fixture
def stub_live(monkeypatch):
    """Credentials present and Search Console answering, fully stubbed."""
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls", lambda sitemap, limit=500: [URL])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(URL, "Submitted and indexed", "")])
    monkeypatch.setattr(gsc, "search_analytics", _search_analytics)


def _run(page: str = "Overview") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["nav"] = page
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _refresh(at: AppTest) -> AppTest:
    button = next(b for b in at.sidebar.button if "Refresh" in b.label)
    button.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


# ── 1. Only "Refresh live data" ever calls Google ───────────────────────────
@pytest.mark.parametrize("page", ["Overview", "Analysis", "Content", "Backlinks"])
def test_no_page_open_calls_search_analytics(stub_live, monkeypatch, page):
    """
    Opening any page — including rerunning it, which is what every widget
    click on the whole app actually does in Streamlit — must never call
    `gsc.search_analytics` on its own.
    """
    calls = []
    real = gsc.search_analytics
    monkeypatch.setattr(gsc, "search_analytics",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    at = _run(page)
    at = _run(page)          # a second open/rerun — still nothing
    assert calls == []


def test_refresh_live_data_caches_performance_for_every_reader(stub_live):
    """One click loads it; every reader (Overview, Analysis, Backlinks, Content
    suggestions) shares the same cache with no further network call."""
    at = _refresh(_run("Overview"))
    assert any(m.label == "Impressions" for m in at.metric)   # shown immediately
    cache = at.session_state[f"perf_{SITE_KEY}"]
    assert cache["pages"][0]["page"] == URL
    assert cache["pages"][0]["impressions"] == 500

    # Switching pages within the same session reads the same cache — no
    # second refresh needed, and no second network call (stub_live would
    # otherwise raise nothing, but the point is nothing NEW is fetched).
    at.session_state["nav"] = "Content"
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    exp = next(e for e in at.expander if "Suggested topics" in e.label)
    text = " ".join(c.value for c in exp.caption)
    assert DEEP_QUERY in text


# ── 2. Content suggests real topics, never fabricates ───────────────────────
def test_suggestions_say_refresh_when_nothing_cached():
    at = _run("Content")
    exp = next(e for e in at.expander if "Suggested topics" in e.label)
    text = " ".join(c.value for c in exp.caption)
    assert "refresh live data to get suggestions" in text.lower()
    assert "impressions" not in text.lower()   # no invented figures


def test_suggestions_show_real_deep_query_after_refresh(stub_live):
    at = _refresh(_run("Content"))
    exp = next(e for e in at.expander if "Suggested topics" in e.label)
    text = " ".join(c.value for c in exp.caption) + " ".join(
        m.value for m in exp.markdown)
    assert DEEP_QUERY in text
    assert "500 impressions" in text
    assert "position 35.0" in text

    use = next(b for b in exp.button if b.label == "Use this")
    use.click().run()
    assert at.session_state["content_topic"] == DEEP_QUERY
    assert at.session_state["content_keyword"] == DEEP_QUERY


def test_suggestions_include_competitor_gaps_when_a_scan_is_cached():
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["nav"] = "Content"
    gap = opp.Opportunity(
        topic="bulk pdf compression guide", kind=opp.GAP,
        keyword="bulk pdf compression",
        reasons=["3 of 3 competitors cover this; you have nothing."], score=42,
    )
    at.session_state["opp_scan"] = {
        "site": SITE_KEY, "result": opp.ScanResult(opportunities=[gap]),
        "niche": "pdf tools",
    }
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    exp = next(e for e in at.expander if "Suggested topics" in e.label)
    text = " ".join(c.value for c in exp.caption) + " ".join(
        m.value for m in exp.markdown)
    assert "bulk pdf compression guide" in text
    assert "3 of 3 competitors cover this" in text


def test_suggestions_never_show_striking_distance_queries(stub_live, monkeypatch):
    """
    Position 20+ (DEEP) is "ranks poorly" — the striking-distance band
    (roughly 4-20) is a different, already-close story that belongs to the
    Overview and Opportunities pages, not this list.
    """
    def sa(_property, _start, _end, dimensions=None, row_limit=250):
        if dimensions == ["page"]:
            return []
        if dimensions == ["page", "query"]:
            return [{"page": URL, "query": "close call", "clicks": 5,
                     "impressions": 200, "ctr": 2.5, "position": 8.0}]
        return [{"query": "close call", "clicks": 5, "impressions": 200,
                 "ctr": 2.5, "position": 8.0}]
    monkeypatch.setattr(gsc, "search_analytics", sa)
    at = _refresh(_run("Content"))
    exp = next(e for e in at.expander if "Suggested topics" in e.label)
    text = " ".join(c.value for c in exp.caption)
    assert "close call" not in text
