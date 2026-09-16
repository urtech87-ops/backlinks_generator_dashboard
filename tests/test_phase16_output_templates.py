"""
Phase 16 — per-site OUTPUT TEMPLATES for the Content agent.

Neither real site takes markdown: ToolsVenue's tool pages and ToolsHall's
blog posts are each their own hand-styled HTML, and generated articles used
to come back as plain markdown regardless of which site they were for. This
phase adds `agents/output_templates.py` (the two HTML renderers + the
markdown fallback), a per-site default in `core.config.output_format()`
(overridable in Settings -> Sites, and per-article on the Content page's
review step), and wires the chosen format into what actually gets saved to
`outputs/<slug>/` and posted as the WordPress draft.

These tests cover, without any network or model call:
  - the per-site default resolves correctly and an explicit save overrides it
  - ToolsVenue's HTML has the tool-page pieces: `<section>` blocks, a
    quick-reference `<table>` built from a numbered how-to, FAQ as
    `<details>`, and a related-tools `<aside>`
  - ToolsHall's HTML has the blog pieces: `## `-derived `<h2>` sections, FAQ
    as `<details>`, a related-tools list and a closing CTA box
  - the markdown fallback is the draft's own markdown, byte for byte
  - `agents.content.to_article()` only sets `Article.body_html` for an HTML
    format, so a markdown-format site's `Article` (and every existing Lane
    A/B caller, which never sets it at all) is unaffected
  - the Content page's review step offers the picker, defaults to the
    site's own format, and the choice survives into the publish step the
    same way Phase 15 made the topic survive past step 1
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import content as content_agent          # noqa: E402
from agents import output_templates as ot            # noqa: E402
from core import config                               # noqa: E402

SAMPLE_BODY = """This is the answer-first intro paragraph. It stands on its own and
completely answers the question with no warm-up at all, which is the whole point.

## What it does

It compresses a JPEG without visibly hurting quality, by re-encoding it at a
carefully chosen quality level.

## Quick reference steps

1. Open the compressor
2. Upload your JPEG
3. Pick a quality level
4. Download the smaller file

## When it is useful

Useful before emailing a batch of photos, or uploading them to a site with a
strict file-size limit.

## Frequently asked questions

### Does this lose quality?
A little, but usually invisibly at the default setting.

### Is it free?
Yes.

## Related tools

See our [PDF Compressor](https://toolsvenue.com/pdf-compressor/) and the
[Image Resizer](https://toolsvenue.com/image-resizer/).
"""


def _draft(meta=None) -> content_agent.Draft:
    return content_agent.Draft(
        topic="compress a jpeg",
        title="How Do You Compress a JPEG Without Losing Quality?",
        body_markdown=SAMPLE_BODY,
        meta=meta if meta is not None else {
            "faq": [{"q": "Does this lose quality?",
                    "a": "A little, but usually invisibly."},
                   {"q": "Is it free?", "a": "Yes."}],
            "internal_links": [{"anchor": "PDF Compressor",
                                "url": "https://toolsvenue.com/pdf-compressor/"}],
        },
    )


# ── Per-site default resolution ─────────────────────────────────────────────
def test_toolsvenue_and_toolshall_default_to_their_own_html_format():
    tv = config.SITES_BY_KEY["toolsvenue"]
    th = config.SITES_BY_KEY["toolshall"]
    assert config.output_format(tv) == config.FORMAT_TOOLSVENUE
    assert config.output_format(th) == config.FORMAT_TOOLSHALL


def test_a_site_with_no_named_template_falls_back_to_markdown():
    ta = config.SITES_BY_KEY["toolacademy"]
    assert config.output_format(ta) == config.FORMAT_MARKDOWN


def test_an_explicit_saved_format_overrides_the_site_default(monkeypatch):
    tv = config.SITES_BY_KEY["toolsvenue"]
    monkeypatch.setattr(tv, "output_format", config.FORMAT_MARKDOWN)
    assert config.output_format(tv) == config.FORMAT_MARKDOWN


def test_an_unrecognised_saved_value_is_treated_as_unset(monkeypatch):
    th = config.SITES_BY_KEY["toolshall"]
    monkeypatch.setattr(th, "output_format", "some-typo'd-value")
    assert config.output_format(th) == config.FORMAT_TOOLSHALL


# ── ToolsVenue HTML — the tool-page pattern ─────────────────────────────────
def test_toolsvenue_html_has_sections_a_table_faq_details_and_a_related_aside():
    html = ot.render_toolsvenue(_draft())

    assert html.count("<section") >= 4          # intro + 3 body sections + FAQ
    assert "<table" in html                      # the numbered how-to became a table
    assert html.count("<td") >= 8                 # 4 steps x 2 columns
    assert "<details" in html and "Does this lose quality?" in html
    assert "<aside" in html and "pdf-compressor" in html
    assert "Related tools" in html


def test_toolsvenue_html_falls_back_to_a_related_link_scrape_with_no_structured_field():
    """A model reply that skipped `internal_links` but still wrote the
    closing section's markdown links must still produce a sidebar."""
    draft = _draft(meta={"faq": [], "internal_links": []})
    html = ot.render_toolsvenue(draft)
    assert "<aside" in html
    assert "pdf-compressor" in html and "image-resizer" in html


def test_toolsvenue_html_skips_faq_and_related_blocks_when_there_is_nothing_to_show():
    draft = _draft(meta={"faq": [], "internal_links": []})
    draft.body_markdown = "Just an intro paragraph with no other sections at all.\n"
    html = ot.render_toolsvenue(draft)
    assert "<aside" not in html
    assert "Frequently asked questions" not in html


# ── ToolsHall HTML — the blog-post pattern ──────────────────────────────────
def test_toolshall_html_has_h2_sections_faq_related_list_and_a_cta_box():
    html = ot.render_toolshall(_draft(), homepage="https://toolshall.com/",
                               site_label="ToolsHall")

    assert html.count("<h2") >= 4                 # 3 body headings + FAQ heading
    assert "<details" in html and "Is it free?" in html
    assert "pdf-compressor" in html
    assert "Ready to put this into practice" in html
    assert 'href="https://toolsvenue.com/pdf-compressor/"' in html   # CTA targets a real related page


def test_toolshall_cta_falls_back_to_the_homepage_with_no_related_pages():
    draft = _draft(meta={"faq": [], "internal_links": []})
    draft.body_markdown = "Just an intro paragraph, nothing else.\n"
    html = ot.render_toolshall(draft, homepage="https://toolshall.com/",
                               site_label="ToolsHall")
    assert 'href="https://toolshall.com/"' in html


# ── Markdown fallback ────────────────────────────────────────────────────────
def test_markdown_format_returns_the_draft_unchanged():
    draft = _draft()
    assert ot.render(draft, config.FORMAT_MARKDOWN) == draft.body_markdown


def test_render_dispatches_on_format():
    draft = _draft()
    assert ot.render(draft, config.FORMAT_TOOLSVENUE) == ot.render_toolsvenue(draft)
    assert (ot.render(draft, config.FORMAT_TOOLSHALL, homepage="https://x.com/", site_label="X")
            == ot.render_toolshall(draft, homepage="https://x.com/", site_label="X"))


# ── agents.content integration ──────────────────────────────────────────────
def test_to_article_sets_body_html_only_for_an_html_format():
    draft = _draft()
    tv_article = content_agent.to_article(draft, config.SITES_BY_KEY["toolsvenue"])
    ta_article = content_agent.to_article(draft, config.SITES_BY_KEY["toolacademy"])
    no_site_article = content_agent.to_article(draft)

    assert tv_article.body_html and "<section" in tv_article.body_html
    assert ta_article.body_html == ""             # markdown site: nothing extra to post
    assert no_site_article.body_html == ""         # unchanged behaviour for existing callers


def test_save_run_writes_article_html_only_for_an_html_format(tmp_path, monkeypatch):
    monkeypatch.setattr(content_agent, "OUTPUT_ROOT", tmp_path)

    tv_draft = _draft()
    tv_folder = content_agent.save_run(config.SITES_BY_KEY["toolsvenue"], tv_draft)
    assert (tv_folder / "content" / "article.md").exists()
    assert (tv_folder / "content" / "article.html").exists()
    assert "<section" in (tv_folder / "content" / "article.html").read_text()

    ta_draft = _draft()
    ta_draft.title = "A Completely Different Article Title"     # a different slug/folder
    ta_folder = content_agent.save_run(config.SITES_BY_KEY["toolacademy"], ta_draft)
    assert ta_folder != tv_folder
    assert (ta_folder / "content" / "article.md").exists()
    assert not (ta_folder / "content" / "article.html").exists()


def test_save_run_fmt_override_beats_the_site_default(tmp_path, monkeypatch):
    monkeypatch.setattr(content_agent, "OUTPUT_ROOT", tmp_path)
    draft = _draft()
    folder = content_agent.save_run(config.SITES_BY_KEY["toolsvenue"], draft,
                                    fmt=config.FORMAT_MARKDOWN)
    assert not (folder / "content" / "article.html").exists()


# ── The Content page's review step ──────────────────────────────────────────
import streamlit as st                                # noqa: E402
from streamlit.testing.v1 import AppTest              # noqa: E402

APP = str(ROOT / "app.py")


def _run(page: str, site: str = "toolsvenue") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["nav"] = page
    at.session_state["site"] = site
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def _text(at: AppTest) -> str:
    parts = [el.value for el in at.markdown]
    parts += [el.value for el in at.caption]
    parts += [el.value for el in at.code]
    return " ".join(str(p) for p in parts)


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
            ok=True, draft=_draft()))


def _write_a_draft(at: AppTest) -> AppTest:
    at.text_input(key="content_topic").set_value("compress a jpeg").run()
    next_button = next(b for b in at.button if b.label == "Research & write →")
    at = next_button.click().run()
    write_button = next(b for b in at.button if "Research and write the draft" in b.label)
    at = write_button.click().run()
    next_button = next(b for b in at.button if b.label == "Review & edit →")
    at = next_button.click().run()
    assert at.session_state["content_step"] == 3
    return at


def test_review_step_defaults_the_format_picker_to_the_sites_own_template(monkeypatch):
    _stub_write_pipeline(monkeypatch)
    at = _run("Content", site="toolsvenue")
    at = _write_a_draft(at)

    picker = at.selectbox(key="content_fmt_pick")
    assert picker.value == config.FORMAT_TOOLSVENUE
    assert "<section" in _text(at)          # the paste-ready preview is real HTML


def test_review_step_can_switch_to_plain_markdown_and_it_survives_to_publish(monkeypatch):
    _stub_write_pipeline(monkeypatch)
    at = _run("Content", site="toolsvenue")
    at = _write_a_draft(at)

    at.selectbox(key="content_fmt_pick").set_value(config.FORMAT_MARKDOWN).run()
    assert at.session_state["content_run"]["output_format"] == config.FORMAT_MARKDOWN

    next_button = next(b for b in at.button if b.label == "Images →")
    at = next_button.click().run()
    next_button = next(b for b in at.button if b.label == "Publish →")
    at = next_button.click().run()
    assert at.session_state["content_step"] == 5

    assert "Plain markdown" in _text(at)
