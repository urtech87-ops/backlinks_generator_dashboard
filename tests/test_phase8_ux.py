"""
Phase 8 — the UX pass, driven through Streamlit's own AppTest.

These tests exist because Phase 8's claims are all claims about what you *see*:
that a disconnected dashboard says its numbers are samples, that connecting
Google replaces them, and that the Overview's rows really do fill in the agent
that does the job. A unit test of the agent wouldn't catch any of that.

Run:  pytest -q            (needs `pip install -r requirements-dev.txt`)

Nothing here touches a real Google API. `_connected()` swaps `core.gsc`'s three
network functions for stubs, which is also the only way this repo has ever been
able to exercise the live path — there are no credentials in the dev
environment, and inventing some would be exactly the sin the app refuses to
commit.
"""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
sys.path.insert(0, str(ROOT))

from core import config, gsc  # noqa: E402

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
    """Stubbed Search Analytics: one winner page, one deep page, one query."""
    if dimensions == ["page"]:
        return [
            {"page": INDEXED, "clicks": 12, "impressions": 900, "ctr": 1.3,
             "position": 8.4},
            {"page": REJECTED, "clicks": 0, "impressions": 40, "ctr": 0.0,
             "position": 33.0},
        ]
    if dimensions == ["page", "query"]:
        return [{"page": INDEXED, "query": "json formatter online", "clicks": 12,
                 "impressions": 900, "ctr": 1.3, "position": 8.4}]
    return [{"query": "json formatter online", "clicks": 12, "impressions": 900,
             "ctr": 1.3, "position": 8.4}]


@pytest.fixture
def disconnected(monkeypatch):
    """No Google key file — the state a new user actually starts in."""
    monkeypatch.setattr(config, "credentials_available", lambda: False)
    return _run()


@pytest.fixture
def connected(monkeypatch):
    """Credentials present and Search Console answering, all stubbed."""
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls",
                        lambda sitemap, limit=500: [u for u, _ in LIVE_COVERAGE])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(u, cov, "") for u, cov in LIVE_COVERAGE])
    monkeypatch.setattr(gsc, "search_analytics", _search_analytics)
    return _run


def _run(page: str = "Overview") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    if page != "Overview":
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
    """Everything written to the page, as one searchable blob."""
    parts = [el.value for el in at.markdown]
    parts += [el.value for el in at.caption]
    parts += [el.value for el in at.info]
    parts += [el.value for el in at.warning]
    parts += [el.value for el in at.success]
    return " ".join(str(p) for p in parts)


def _labels(at: AppTest) -> list:
    return [b.label for b in at.button]


def _state(at: AppTest, key: str, default=None):
    """session_state has no .get(), and popped hand-off keys are legitimately absent."""
    try:
        return at.session_state[key]
    except Exception:
        return default


# ── The landing page ───────────────────────────────────────────────────────
def test_overview_is_the_landing_page(disconnected):
    assert disconnected.session_state["nav"] == "Overview"
    assert "Overview · ToolsVenue" in _text(disconnected)


def test_every_page_renders(monkeypatch):
    monkeypatch.setattr(config, "credentials_available", lambda: False)
    for page in ("Overview", "Analysis", "Opportunities", "Content", "Backlinks",
                 "Settings"):
        _run(page)          # _run asserts no exception escaped


# ── Not-connected state ────────────────────────────────────────────────────
def test_disconnected_pages_say_the_numbers_are_samples(monkeypatch):
    monkeypatch.setattr(config, "credentials_available", lambda: False)
    for page in ("Overview", "Analysis", "Opportunities", "Content", "Backlinks"):
        at = _run(page)
        assert "SAMPLE data" in _text(at), f"{page} doesn't say its numbers are samples"
        assert "🔌 Connect Search Console + GA4" in _labels(at), \
            f"{page} has no connect button"


def test_connect_button_jumps_to_the_google_section(disconnected):
    connect = next(b for b in disconnected.button
                   if b.label == "🔌 Connect Search Console + GA4")
    connect.click().run()
    assert disconnected.session_state["nav"] == "Settings"
    assert disconnected.session_state["settings_section"] == "🔑 Google APIs"


def test_settings_itself_carries_no_banner(monkeypatch):
    """The page that *is* the fix shouldn't nag about needing the fix."""
    monkeypatch.setattr(config, "credentials_available", lambda: False)
    assert "SAMPLE data" not in _text(_run("Settings"))


def test_onboarding_strip_is_present_and_tracks_state(disconnected):
    text = _text(disconnected)
    for title in ("Connect your data", "Review what's ranking",
                  "Generate backlinks + content"):
        assert title in text
    assert "you are here" in text          # step 1, because nothing is connected


# ── Connecting replaces the sample with live data ──────────────────────────
def test_refresh_replaces_sample_coverage_with_live(connected):
    at = connected()
    assert "SAMPLE data" in _text(at)

    _refresh(at)

    rows = at.session_state["coverage_toolsvenue"]
    assert rows == LIVE_COVERAGE
    text = _text(at)
    assert "Live data from Search Console" in text
    assert "SAMPLE data" not in text

    tracked = next(m for m in at.metric if m.label == "Pages tracked")
    assert tracked.value == str(len(LIVE_COVERAGE))


def test_live_performance_shows_without_pressing_run(connected):
    """
    The Phase 8 fix for the worst trap in Phase 7: landing on a connected
    dashboard used to show an empty performance panel until you found the
    button.
    """
    at = _refresh(connected())
    values = {m.label: m.value for m in at.metric}
    assert values["Impressions"] == "940"       # 900 + 40, straight from the stub
    assert values["Clicks"] == "12"
    assert "ranked on live Search Console figures" in _text(at)


def test_ga4_is_not_reported_as_connected_without_a_property_id(connected):
    """One key file serves both APIs, but no property ID means no GA4."""
    at = _refresh(connected())
    assert not config.ga4_ready(config.SITES_BY_KEY["toolsvenue"])
    assert "no property ID" in _text(at)


# ── The winners table and its three actions ────────────────────────────────
def test_every_ranked_row_offers_all_three_actions(connected):
    at = _refresh(connected())
    labels = _labels(at)
    for action in ("🔗 Build backlinks", "✍️ Write article", "🔧 Fix"):
        assert labels.count(action) >= 1, f"no {action} button on any row"
    # One button of each kind per row, so the counts have to match.
    assert (labels.count("🔗 Build backlinks") >= labels.count("🔧 Fix")
            and labels.count("✍️ Write article") == labels.count("🔧 Fix"))


def test_actions_are_disabled_where_they_would_be_wasted(connected):
    """A backlink to a broken page earns nothing, and the row says so."""
    at = _refresh(connected())
    link_buttons = [b for b in at.button if b.label == "🔗 Build backlinks"]
    fix_buttons = [b for b in at.button if b.label == "🔧 Fix"]
    assert any(b.disabled for b in link_buttons), \
        "the broken/rejected pages should not offer a backlink"
    assert any(not b.disabled for b in fix_buttons), \
        "a page with a problem should offer Fix"
    assert any(b.disabled for b in fix_buttons), \
        "a healthy page has nothing to fix"


def test_build_backlinks_preselects_the_page_on_the_backlinks_page(connected):
    at = _refresh(connected())
    next(b for b in at.button
         if b.label == "🔗 Build backlinks" and not b.disabled).click().run()
    assert at.session_state["nav"] == "Backlinks"
    assert any("Preselected" in s.value for s in at.success)


def test_write_article_fills_the_writer_in(connected):
    at = _refresh(connected())
    next(b for b in at.button
         if b.label == "✍️ Write article" and not b.disabled).click().run()
    assert at.session_state["nav"] == "Content"
    # The striking-distance query wins over the slug, because it's the search
    # the page is actually close on.
    assert _state(at, "content_topic") == "json formatter online"
    assert INDEXED in _state(at, "content_notes", "")
    assert any("Filled in from the Overview" in s.value for s in at.success)


def test_fix_opens_the_fix_plan_filtered_to_that_problem(connected):
    at = _refresh(connected())
    next(b for b in at.button if b.label == "🔧 Fix" and not b.disabled).click().run()
    assert at.session_state["nav"] == "Analysis"
    assert at.session_state["analysis_bucket"] in ("Plumbing", "Content")


def test_striking_distance_queries_are_offered_on_the_landing_page(connected):
    at = _refresh(connected())
    text = _text(at)
    assert "json formatter online" in text
    assert "✍️ Write for this" in _labels(at)


# ── No invented numbers (CLAUDE.md's hardest rule) ─────────────────────────
def test_without_search_console_the_ranking_says_it_is_not_a_ranking(disconnected):
    text = _text(disconnected)
    assert "not** a performance ranking" in text or "not a performance ranking" in text
    assert "coverage only — no performance figures" in text
