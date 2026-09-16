"""
Phase 15 — two bug fixes, both reported live.

  1. Sample data returned after a browser tab reload. `refresh_live()` cached
     its result only in `st.session_state`, so a fresh tab (a brand new
     Streamlit session) had nothing to read and fell back to the seed —
     even right after a successful refresh. Live coverage/performance/GA4
     are now also persisted to `data/live_cache/<site>.json`, and every
     reader hydrates from that file once per session before falling back to
     seed, so a reload shows the last real refresh instead of the sample.
     Sample only shows for a site that has genuinely never been refreshed —
     not this session, not an earlier one.

  2. "Go back and enter a topic first" on the Content page even with a topic
     typed in. Streamlit clears a widget's `session_state` entry once that
     widget stops being instantiated on a render, which happens to every one
     of step 1's inputs (`content_topic` included) the instant the wizard
     moves to step 2 — so reading `st.session_state["content_topic"]` from
     step 2 worked on the very next render only by luck (the value hadn't
     been swept yet) and returned "" on any later one, which is exactly what
     "the box is full but it says no topic" looks like. Step 1 now mirrors
     its fields into a plain, non-widget key (`content_fields`) every time
     it renders, and step 2 reads from there instead.

Both are driven through Streamlit's AppTest; bug 1 also gets a direct
`ui.data` test since "close the tab and open a new one" is best simulated by
clearing `st.session_state` outright rather than faking a browser.
"""

import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
sys.path.insert(0, str(ROOT))

from agents import content as content_agent  # noqa: E402
from core import config, gsc  # noqa: E402
from core.classifier import HEALTHY  # noqa: E402
from ui import data as d  # noqa: E402

SITE_KEY = "toolsvenue"
SITE_PROP = "https://toolsvenue.com"
URL = f"{SITE_PROP}/json-formatter/"


def _no_search_analytics(_property, _start, _end, dimensions=None, row_limit=250):
    return []


def _run(page: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["nav"] = page
    at.run()
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
def isolated_cache_dir(monkeypatch, tmp_path):
    """Point the live-data disk cache at a throwaway directory, so these
    tests never read or write the repo's real `data/live_cache/`."""
    monkeypatch.setattr(d, "_CACHE_DIR", tmp_path / "live_cache")
    yield tmp_path / "live_cache"


# ── Bug 1: live data must survive a reload ──────────────────────────────────
def test_refresh_persists_to_disk_and_survives_a_cleared_session(
    isolated_cache_dir, monkeypatch,
):
    """
    Simulates: press Refresh live data (real data loads) -> close the tab and
    open a new one (a brand new session has nothing in session_state) ->
    the screen must still show the live coverage just refreshed, not seed.
    """
    site = config.SITES_BY_KEY[SITE_KEY]
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls", lambda sitemap, limit=500: [URL])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(URL, "Submitted and indexed", "")])
    monkeypatch.setattr(gsc, "search_analytics", _no_search_analytics)

    st.session_state.clear()
    rows, source = d.coverage_rows(site)
    assert source == "seed"          # never refreshed yet

    count, message = d.refresh_live(site)
    assert count == 1
    assert "Loaded live coverage" in message

    rows, source = d.coverage_rows(site)
    assert source == "live"
    assert rows == [(URL, "Submitted and indexed")]
    assert d.last_refreshed(site)    # a timestamp was recorded

    # The actual repro: a tab reload is a brand new session, with nothing
    # carried over in session_state at all.
    st.session_state.clear()

    rows, source = d.coverage_rows(site)
    assert source == "live", "a reload must not fall back to sample after a real refresh"
    assert rows == [(URL, "Submitted and indexed")]

    df, frame_source = d.coverage_frame(site)
    assert frame_source == "live"
    assert df.iloc[0]["Bucket"] == HEALTHY

    # And the timestamp survives the reload too, for the "last refreshed" banner.
    assert d.last_refreshed(site)


def test_a_site_never_refreshed_still_shows_sample_after_a_cleared_session(
    isolated_cache_dir, monkeypatch,
):
    """The other half of the rule: sample data may ONLY show for a site that
    has genuinely never been refreshed — clearing the session for a site
    with no disk cache at all must still show the sample, not crash or
    invent a live source."""
    site = config.SITES_BY_KEY["toolshall"]   # has no seed and no cache
    monkeypatch.setattr(config, "credentials_available", lambda: True)

    st.session_state.clear()
    rows, source = d.coverage_rows(site)
    assert source == "seed"
    assert d.last_refreshed(site) == ""


def test_overview_shows_live_banner_on_a_freshly_opened_session_after_refresh(
    isolated_cache_dir, monkeypatch,
):
    """End-to-end through the actual page: refresh in one AppTest "browser
    tab", then open a completely new AppTest (a fresh session, the way a
    real tab reload starts) and confirm Overview reads the persisted cache
    instead of announcing sample data."""
    monkeypatch.setattr(config, "credentials_available", lambda: True)
    monkeypatch.setattr(gsc, "discover_urls", lambda sitemap, limit=500: [URL])
    monkeypatch.setattr(gsc, "inspect_urls",
                        lambda prop, urls, progress=None:
                        [(URL, "Submitted and indexed", "")])
    monkeypatch.setattr(gsc, "search_analytics", _no_search_analytics)

    at = _run("Overview")
    button = next(b for b in at.sidebar.button if "Refresh" in b.label)
    button.click().run()
    assert not at.exception
    assert "Live data" in _text(at) or "🟢" in _text(at)

    # A new AppTest.from_file() is a brand new session_state — the same
    # isolation a browser tab reload gives you.
    at2 = _run("Overview")
    text2 = _text(at2)
    assert "SAMPLE data — never refreshed" not in text2
    assert "never refreshed" not in text2 or "Live data" in text2


# ── Bug 2: the Content topic must survive past step 1 ───────────────────────
def _stub_write_pipeline(monkeypatch):
    monkeypatch.setattr(config, "is_set", lambda key: key == "OPENROUTER_API_KEY")
    monkeypatch.setattr(
        content_agent, "research",
        lambda topic, site, **k: content_agent.Research(topic=topic, ok=True,
                                                         detail="stub research"))
    monkeypatch.setattr(content_agent, "page_facts", lambda url, **k: {})
    monkeypatch.setattr(
        content_agent, "write",
        lambda topic, site, *a, **k: content_agent.WriteResult(
            ok=True,
            draft=content_agent.Draft(topic=topic, title="Stub title",
                                      body_markdown="Stub body"),
        ))


def test_topic_survives_a_second_rerun_on_step_2():
    """
    The exact repro: type a topic, advance to step 2 — then anything at all
    that causes another rerun while still on step 2 (the reported case was
    simply clicking "Research and write the draft" itself) must not lose the
    topic. Before the fix, `content_topic` was already gone by this point.
    """
    at = _run("Content")
    at.text_input(key="content_topic").set_value("How do I compress a PDF?").run()
    next_button = next(b for b in at.button if b.label == "Research & write →")
    next_button.click().run()
    assert at.session_state["content_step"] == 2

    # A second rerun on step 2, with no step-1 widget re-instantiated.
    at.run()
    assert not at.exception

    text = _text(at)
    assert "Go back and enter a topic first" not in text
    assert "How do I compress a PDF?" in text


def test_research_and_write_button_uses_the_entered_topic(monkeypatch):
    """A filled topic must actually pass through to the write pipeline, not
    just render correctly — the button must proceed instead of erroring."""
    _stub_write_pipeline(monkeypatch)

    at = _run("Content")
    at.text_input(key="content_topic").set_value("How do I compress a PDF?").run()
    next_button = next(b for b in at.button if b.label == "Research & write →")
    next_button.click().run()
    assert at.session_state["content_step"] == 2

    # One more rerun before pressing the write button, matching the repro
    # exactly (this is the render where content_topic used to be gone).
    at.run()
    assert not at.exception

    write_button = next(b for b in at.button if "Research and write the draft" in b.label)
    write_button.click().run()
    assert not at.exception

    text = _text(at)
    assert "Go back and enter a topic first" not in text
    assert "No OpenRouter key saved" not in text

    run = at.session_state.get("content_run")
    assert run is not None, "the write pipeline never ran — the topic was lost"
    assert run["topic"] == "How do I compress a PDF?"
    assert run["draft"].title == "Stub title"
