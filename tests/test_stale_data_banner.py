"""
Phase 11-fix, continued — "stale coverage shown as if it were live".

Bug report this closes: on a session where Search Console credentials were
already saved, the Analysis tabs kept showing the OLD sample snapshot as if
it were live — pages read "Not indexed" purely because the tab was reading
stale sample coverage — until the user thought to press "Refresh live data"
by hand. Nothing on screen said the numbers were stale, so a non-expert user
had no reason to distrust them.

Phase 11-fix-2's original fix made a connected session auto-load live
coverage the first time a site's data was read. Phase 13 removed that: this
dashboard now calls Google in exactly one place — the sidebar's "Refresh
live data" button — because auto-loading "on first open" actually meant
"on every rerun" (Streamlit reruns the whole script on any interaction),
which spent API quota far more than the name suggested. The original bug
this file guards against is closed a different way instead:
  1. `ui.components.stale_coverage_banner()` is a loud, in-content warning
     (not just the small badge `data_source_note()` already drew) that fires
     in the ordinary state a connected session starts every page in: nobody
     has pressed "Refresh live data" *this session* yet, so every number on
     screen is still the sample snapshot.
  2. Verdicts computed from sample coverage are marked "(sample)" wherever
     they're shown, so a sample-derived verdict can never look exactly like
     a live one — on the Overview's winners list and the Analysis
     Performance tab alike.

This file drives both through Streamlit's AppTest, across the Overview,
Analysis and Backlinks pages named in the original bug report.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
sys.path.insert(0, str(ROOT))

from core import config, gsc  # noqa: E402
from core.classifier import HEALTHY  # noqa: E402
from ui import data as d  # noqa: E402
from ui.views import analysis as av  # noqa: E402

SITE = "https://toolsvenue.com"
INDEXED = f"{SITE}/json-formatter/"
UNCRAWLED = f"{SITE}/compress-pdf/"
REJECTED = f"{SITE}/blogs/thin-post/"
BROKEN = f"{SITE}/currency-converter"

LIVE_COVERAGE = [
    (INDEXED, "Submitted and indexed"),
    (UNCRAWLED, "Discovered - currently not indexed"),
    (REJECTED, "Crawled - currently not indexed"),
    (BROKEN, "Redirect error"),
]


def _search_analytics(_property, _start, _end, dimensions=None, row_limit=250):
    if dimensions == ["page"]:
        return [{"page": INDEXED, "clicks": 12, "impressions": 900, "ctr": 1.3,
                 "position": 8.4}]
    if dimensions == ["page", "query"]:
        return []
    return [{"query": "json formatter online", "clicks": 12, "impressions": 900,
             "ctr": 1.3, "position": 8.4}]


def _run(page: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["nav"] = page
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _refresh(at: AppTest) -> AppTest:
    """Press the sidebar's 'Refresh live data', as a user would."""
    button = next(b for b in at.sidebar.button if "Refresh" in b.label)
    button.click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _text(at: AppTest) -> str:
    parts = [el.value for el in at.markdown]
    parts += [el.value for el in at.caption]
    parts += [el.value for el in at.info]
    parts += [el.value for el in at.warning]
    parts += [el.value for el in at.success]
    parts += [el.value for el in at.error]
    return " ".join(str(p) for p in parts)


@pytest.fixture
def stub_live(monkeypatch):
    """Credentials present and Search Console answering, fully stubbed."""
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls",
                        lambda sitemap, limit=500: [u for u, _ in LIVE_COVERAGE])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(u, cov, "") for u, cov in LIVE_COVERAGE])
    monkeypatch.setattr(gsc, "search_analytics", _search_analytics)


@pytest.fixture
def stub_broken(monkeypatch):
    """Credentials present, but the sitemap can't be read — the refresh fails."""
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls", lambda sitemap, limit=500: [])
    monkeypatch.setattr(gsc, "search_analytics", _search_analytics)


# ── 1. No data screen ever calls Google before you press the one button ────
@pytest.mark.parametrize("page", ["Overview", "Analysis", "Backlinks"])
def test_connected_screens_never_auto_load_live_coverage(stub_live, page):
    """
    Credentials on disk must never, on their own, trigger a live call —
    every data screen shows the loud stale-sample banner and nothing on
    session_state until you press Refresh live data. (Streamlit reruns the
    whole script on any interaction, so "loads on open" would actually mean
    "loads on every click" — the exact quota burn this closes.)
    """
    at = _run(page)
    assert "coverage_toolsvenue" not in at.session_state
    text = _text(at)
    assert "Live data from Search Console" not in text
    assert "Showing sample data" in text


@pytest.mark.parametrize("page", ["Overview", "Analysis", "Backlinks"])
def test_connected_screens_load_live_coverage_on_refresh(stub_live, page):
    at = _run(page)
    at = _refresh(at)
    assert at.session_state["coverage_toolsvenue"] == LIVE_COVERAGE
    text = _text(at)
    # Phase 15: the badge now names when it was refreshed, not just "live".
    assert "Live data (last refreshed" in text
    assert "Showing sample data" not in text


@pytest.mark.parametrize("page", ["Overview", "Analysis", "Backlinks"])
def test_connected_screens_warn_loudly_when_refresh_fails(stub_broken, page):
    """
    A refresh can't always succeed (bad sitemap URL, quota, auth). When it
    doesn't, the page must say so loudly and keep saying the coverage on
    screen is the sample snapshot — never fall back to a quiet, unmarked
    sample view that looks the same as a genuinely live one.
    """
    at = _refresh(_run(page))
    text = _text(at)
    assert "Couldn't read any URLs" in text
    assert "Showing sample data" in text


# ── 2. Sample-derived verdicts are marked, never shown as confident live ───
def test_with_verdicts_marks_sample_when_coverage_is_stale():
    coverage = pd.DataFrame([{
        "URL": INDEXED, "Page": "/json-formatter/", "Coverage": "Submitted and indexed",
        "Bucket": HEALTHY, "Priority": 5, "Action": "", "Flags": "",
    }])
    pdf = pd.DataFrame([{"page": INDEXED, "clicks": 12, "impressions": 900,
                        "ctr": 1.3, "position": 8.4}])

    live_out = av._with_verdicts(coverage, pdf, coverage_source="live")
    assert "(sample)" not in live_out.iloc[0]["Verdict"]

    seed_out = av._with_verdicts(coverage, pdf, coverage_source="seed")
    assert "(sample)" in seed_out.iloc[0]["Verdict"]
    assert "sample snapshot" in seed_out.iloc[0]["Why"]


def test_with_verdicts_empty_coverage_is_not_mislabelled_sample():
    """
    An empty coverage frame is "nothing loaded", not "stale sample data" —
    that page already reads honestly as "Couldn't check yet"
    (see test_phase11fix_indexing_verdict.py); it must not also claim to be
    a sample verdict, which would be a different, wrong story.
    """
    empty = pd.DataFrame(columns=["URL", "Page", "Coverage", "Bucket",
                                  "Priority", "Action", "Flags"])
    pdf = pd.DataFrame([{"page": INDEXED, "clicks": 12, "impressions": 900,
                        "ctr": 1.3, "position": 8.4}])
    out = av._with_verdicts(empty, pdf, coverage_source="seed")
    assert "(sample)" not in out.iloc[0]["Verdict"]


# ── 4. The exact reported site: ToolsHall, which has no seed at all ────────
def test_toolshall_starts_empty_then_loads_live_on_refresh(monkeypatch):
    """
    ToolsHall has no entry in `core.seed.SEED_BY_SITE`, so a fresh session
    starts from an EMPTY coverage frame — not even a stale sample, just
    nothing — until "Refresh live data" is pressed by hand. That's read
    honestly as "Couldn't check yet" (Phase 11-fix), never as a confirmed
    "not indexed" — and pressing the button replaces it with the real thing.
    """
    import streamlit as st
    st.session_state.clear()

    site = config.SITES_BY_KEY["toolshall"]
    ts_url = "https://toolshall.com/pdf-compressor/"
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls", lambda sitemap, limit=500: [ts_url])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(ts_url, "Submitted and indexed", "")])

    rows, source = d.coverage_rows(site)
    assert source == "seed"
    assert rows == []

    count, _ = d.refresh_live(site)
    assert count == 1

    rows, source = d.coverage_rows(site)
    assert source == "live"
    assert rows == [(ts_url, "Submitted and indexed")]

    df, frame_source = d.coverage_frame(site)
    assert frame_source == "live"
    assert not df.empty
    assert df.iloc[0]["Bucket"] == HEALTHY


# ── 5. Overview's winners list catches "live performance, stale coverage" ──
def test_stale_coverage_banner_quiet_when_not_connected(monkeypatch):
    """
    The not-connected state already has its own loud banner
    (`connect_banner`) — `stale_coverage_banner` must not pile a second,
    overlapping warning on top of it.
    """
    monkeypatch.setattr(config, "credentials_available", lambda: False)
    at = _run("Analysis")
    text = _text(at)
    assert "These numbers are SAMPLE data" in text     # connect_banner
    assert "Showing sample data — press Refresh live data" not in text
