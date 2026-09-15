"""
Phase 12 — the task wizards, driven through Streamlit's own AppTest.

Phase 12 turned the dense Backlinks and Content pages into step-by-step
wizards: one step on screen at a time, a "Step X of N" progress strip, and
Next/Back buttons that only let you move forward once the current step has
actually produced something. These tests exist to prove that shape survived
the rewrite — that a step really does gate on its own state, that Back
really goes back, and that nothing here lets you skip past a guardrail
(no OpenRouter key, no platform configured) by clicking Next anyway.

No credentials are used anywhere in this file — every wizard here is driven
on the sample snapshot, which is exactly the environment a fresh install of
this dashboard starts in.

Run:  pytest -q            (needs `pip install -r requirements-dev.txt`)
"""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
sys.path.insert(0, str(ROOT))


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
    return " ".join(str(p) for p in parts)


def _labels(at: AppTest) -> list:
    return [b.label for b in at.button]


def _state(at: AppTest, key: str, default=None):
    """session_state has no .get(), and an unset key legitimately doesn't exist."""
    try:
        return at.session_state[key]
    except Exception:
        return default


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


# ── Lane A: build an auto-publish backlink ─────────────────────────────────
def test_lane_a_starts_on_step_1_of_4():
    at = _run("Backlinks")
    assert "Step 1 of 4" in _text(at)
    assert "Pick the page you want links to" in _text(at)
    # Nothing past step 1 is drawn yet.
    assert "Choose where to publish" not in _text(at)


def test_lane_a_next_and_back_move_one_step():
    at = _run("Backlinks")
    _click(at, "Choose platforms →")
    assert at.session_state["bl_step_a"] == 2
    assert "Step 2 of 4" in _text(at)
    assert "Choose where to publish" in _text(at)

    _click(at, "← Back")
    assert at.session_state["bl_step_a"] == 1
    assert "Step 1 of 4" in _text(at)


def test_lane_a_step_2_blocks_without_a_platform_configured():
    """No dev.to/Blogger/WordPress keys in this environment — step 2 has to say so
    and must not offer a way past it."""
    at = _run("Backlinks")
    _click(at, "Choose platforms →")
    assert "None of your platforms are set up yet" in _text(at)
    assert "Generate the draft →" not in _labels(at)


def test_lane_a_step_3_blocks_without_an_openrouter_key():
    at = _run("Backlinks")
    at.session_state["bl_step_a"] = 3
    at.run()
    assert "No OpenRouter key saved" in _text(at)
    assert "Review & publish →" not in _labels(at)


# ── Lane B: the 5-stage guest outreach wizard ──────────────────────────────
def test_lane_b_has_five_named_stages():
    at = _run("Backlinks")
    text = _text(at)
    for stage in ("Pick target page", "Find prospects", "Choose a site",
                 "Review pitch + article", "Send & track"):
        assert stage in text, f"missing stage: {stage}"


def test_lane_b_step_1_picks_the_target_and_advances():
    at = _run("Backlinks")
    lane_b_next = [b for b in at.button if b.label == "Find prospects →"]
    assert lane_b_next, "Lane B's step-1 Next button should be on screen"
    lane_b_next[0].click().run()
    assert at.session_state["bl_step_b"] == 2
    assert _state(at, "gb_target_url")


def test_lane_b_cannot_reach_step_3_without_ever_picking_a_target():
    """
    Jumping the step counter directly, before step 1 has ever run (so there's
    no selectbox default backing a choice), must bounce back to a warning —
    never crash and never show step 3's controls.
    """
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["nav"] = "Backlinks"
    at.session_state["bl_step_b"] = 3
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert _state(at, "gb_target_url") is None
    assert "Choose which site to pitch" not in _text(at)
    assert "pick the page this outreach should link to first" in _text(at)


def test_lane_b_step_5_names_the_human_approval_point():
    at = _run("Backlinks")
    _click(at, "Find prospects →")
    at.session_state["bl_step_b"] = 5
    at.run()
    assert "the only step a human has to do" in _text(at)


# ── Content: the "improve a page" / write-an-article wizard ───────────────
def test_content_wizard_starts_on_step_1_of_5():
    at = _run("Content")
    assert "Step 1 of 5" in _text(at)
    assert "What should this article be about?" in _text(at)


def test_content_step_1_next_is_disabled_without_a_topic():
    at = _run("Content")
    next_buttons = [b for b in at.button if b.label == "Research & write →"]
    assert next_buttons and next_buttons[0].disabled


def test_content_step_1_advances_once_a_topic_is_entered():
    at = _run("Content")
    at.text_input(key="content_topic").set_value("How do I compress a PDF?").run()
    next_button = next(b for b in at.button if b.label == "Research & write →")
    assert not next_button.disabled
    next_button.click().run()
    assert at.session_state["content_step"] == 2
    assert "Step 2 of 5" in _text(at)


def test_content_step_2_blocks_without_an_openrouter_key():
    at = _run("Content")
    at.text_input(key="content_topic").set_value("How do I compress a PDF?").run()
    _click(at, "Research & write →")
    assert "No OpenRouter key saved" in _text(at)
    assert "Review & edit →" not in _labels(at)


def test_content_step_3_bounces_back_without_a_draft():
    at = _run("Content")
    at.session_state["content_step"] = 3
    at.run()
    assert not at.exception
    assert "Nothing drafted yet" in _text(at)
    assert "Read it before anyone else does" not in _text(at)


# ── Every page still renders with no wizard state at all ───────────────────
def test_backlinks_and_content_render_cold():
    for page in ("Backlinks", "Content"):
        _run(page)
