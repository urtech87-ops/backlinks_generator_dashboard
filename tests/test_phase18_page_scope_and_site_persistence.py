"""
Phase 18 — two scoped bug fixes, both reported live, driven through
Streamlit's own AppTest.

  1. "Write article" from a page's row on Overview opened the Content page
     with generic, site-wide "Suggested topics" and keyword picker instead
     of ones scoped to the page that was actually clicked. The page context
     was already being passed for the "Anything the writer should know"
     field (`content_notes`) — it just wasn't being used to filter the two
     real-data sections. The fix threads a `content_focus_url` hand-off
     through to `core.keywords.for_page()`, so both sections now show only
     that page's own Search Console queries, with its striking-distance
     terms called out as recommended. Navigating to Content directly (no
     hand-off) keeps the old site-wide behavior.

  2. The sidebar's site selector had no `key=`, so it always fell back to
     the first site in the list on every rerun — including a browser tab
     reload, which starts a brand-new Streamlit session. Selecting ToolsHall
     and reloading silently reset to ToolsVenue. The fix persists the
     selection to `data/ui_state.json` (the same "session_state alone isn't
     enough, it's wiped by a reload" pattern Phase 15 used for live data),
     so a fresh session restores the site that was actually selected.

Run:  pytest -q            (needs `pip install -r requirements-dev.txt`)
"""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
sys.path.insert(0, str(ROOT))

from core import config, gsc  # noqa: E402
from ui import data as d  # noqa: E402

SITE = "https://toolsvenue.com"
PAGE_A = f"{SITE}/tool/change-image-background/"
PAGE_B = f"{SITE}/tool/resize-photo-online/"
LIVE_COVERAGE = [(PAGE_A, "Submitted and indexed"), (PAGE_B, "Submitted and indexed")]

QUERY_A = "remove background from image online"
QUERY_B = "resize photo online free"


def _search_analytics(_property, _start, _end, dimensions=None, row_limit=250):
    """Two indexed pages, each with its own striking-distance query."""
    if dimensions == ["page"]:
        return [
            {"page": PAGE_A, "clicks": 20, "impressions": 800, "ctr": 2.5, "position": 9.0},
            {"page": PAGE_B, "clicks": 15, "impressions": 700, "ctr": 2.1, "position": 10.0},
        ]
    if dimensions == ["page", "query"]:
        return [
            {"page": PAGE_A, "query": QUERY_A, "clicks": 20, "impressions": 800,
             "ctr": 2.5, "position": 9.0},
            {"page": PAGE_B, "query": QUERY_B, "clicks": 15, "impressions": 700,
             "ctr": 2.1, "position": 10.0},
        ]
    return [
        {"query": QUERY_A, "clicks": 20, "impressions": 800, "ctr": 2.5, "position": 9.0},
        {"query": QUERY_B, "clicks": 15, "impressions": 700, "ctr": 2.1, "position": 10.0},
    ]


def _run(page: str = "Overview") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    if page != "Overview":
        at.session_state["nav"] = page
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _refresh(at: AppTest) -> AppTest:
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


def _connected(monkeypatch) -> None:
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls",
                        lambda sitemap, limit=500: [u for u, _ in LIVE_COVERAGE])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(u, cov, "") for u, cov in LIVE_COVERAGE])
    monkeypatch.setattr(gsc, "search_analytics", _search_analytics)


# ── (a) Write article scopes Content's suggestions + keyword picker ────────
def test_write_article_scopes_suggestions_and_keywords_to_that_page(monkeypatch):
    """
    Click "Write article" on either page's row and the Content page that
    opens must show ONLY that page's own query as a suggestion and as a
    recommended keyword — never the other page's, even though both are
    real, live, striking-distance queries this site actually has.
    """
    for target_index in (0, 1):
        _connected(monkeypatch)
        at = _refresh(_run("Overview"))

        buttons = [b for b in at.button if b.label == "✍️ Write article" and not b.disabled]
        assert len(buttons) == 2, "expected one Write article button per indexed page"
        buttons[target_index].click().run()
        assert not at.exception, [str(e.value) for e in at.exception]
        assert at.session_state["nav"] == "Content"

        focus = at.session_state["content_focus_page"]
        assert focus in (PAGE_A, PAGE_B)
        own_query, other_query = (QUERY_A, QUERY_B) if focus == PAGE_A else (QUERY_B, QUERY_A)

        text = _text(at)
        assert focus in text, "the page should be named as what suggestions are scoped to"
        assert own_query in text, "the page's own striking-distance query should be suggested"
        assert other_query not in text, \
            "the OTHER page's query must never show up — that's the bug"
        assert "Recommended" in text, \
            "a striking-distance query must be labelled recommended, not just listed"


def test_navigating_to_content_directly_keeps_site_wide_suggestions(monkeypatch):
    """The other half of the rule: with no hand-off at all, both pages'
    queries are fair game — the old, unscoped behavior."""
    _connected(monkeypatch)
    at = _refresh(_run("Overview"))
    at.session_state["nav"] = "Content"
    at.run()
    assert not at.exception

    assert "content_focus_page" not in dict(at.session_state)
    text = _text(at)
    # Site-wide suggestions come from the DEEP band (position > 20), not
    # STRIKING (these two queries sit at position 9-10) — so directly assert
    # the page never claims to be scoped to either URL.
    assert "Scoped to" not in text
    assert PAGE_A not in text
    assert PAGE_B not in text


# ── (b) selected site survives a simulated reload ──────────────────────────
# `ui.data._UI_STATE_PATH` is already pointed at a throwaway per-test path by
# the autouse `_isolated_live_cache_dir` fixture in conftest.py, so nothing
# here ever touches the repo's real `data/ui_state.json`.
def test_selected_site_persists_across_a_simulated_reload():
    """
    Simulates: open the dashboard (defaults to the first site) -> pick
    ToolsHall in the sidebar -> close the tab and open a new one (a brand
    new AppTest session, the same isolation a real browser reload gives
    you) -> the sidebar must still show ToolsHall, not fall back to the
    first site in the list.
    """
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    site_select = at.selectbox(key="site_key")
    assert site_select.value == config.SITES[0].key  # ToolsVenue, the default

    other_key = "toolshall"
    assert other_key != config.SITES[0].key
    site_select.set_value(other_key).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.selectbox(key="site_key").value == other_key

    # A brand new AppTest.from_file() is a brand new session — nothing
    # carried over in session_state, exactly like a real tab reload.
    at2 = AppTest.from_file(APP, default_timeout=120)
    at2.run()
    assert not at2.exception, [str(e.value) for e in at2.exception]
    assert at2.selectbox(key="site_key").value == other_key, \
        "a reload must restore the site that was actually selected, not the first one"


def test_a_fresh_install_with_nothing_saved_defaults_to_the_first_site():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    assert at.selectbox(key="site_key").value == config.SITES[0].key


def test_save_selected_site_ignores_an_unknown_key():
    """Guards against a stale save (a site removed from .env) ever crashing
    the selectbox on reload — app.py falls back to the first real site."""
    d.save_selected_site("toolshall")
    assert d.last_selected_site() == "toolshall"

    d.save_selected_site("")
    assert d.last_selected_site() == "toolshall"  # unchanged, not cleared
