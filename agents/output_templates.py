"""
Per-site OUTPUT TEMPLATES for the Content agent (Phase 16).

Neither real site takes markdown: ToolsVenue's tool pages and ToolsHall's
blog posts are both hand-styled, inline-styled HTML, and they aren't styled
the *same* way as each other. Until now `agents.content.write()` handed back
plain markdown regardless of which site it was for, so every draft needed
reformatting by hand before it could be pasted into either site's editor.

`render()` is the one entry point: given a finished `agents.content.Draft`
and the format it should come out in (`core.config.output_format(site)`
decides that per site, and the Content page lets a run override it for just
that article), it returns paste-ready HTML matching that site's structure —
or, for `core.config.FORMAT_MARKDOWN`, the draft's markdown unchanged, kept
as an explicit fallback (the user may still want raw text).

Both HTML templates are built from the same structured data
`agents.content.write()` already returns — the body's own `## ` sections,
plus the FAQ and internal links in `draft.meta` — so nothing here reparses
or reinterprets what the model wrote; it only repaints it:

  ToolsVenue (`FORMAT_TOOLSVENUE`) — the tool-page pattern: `<section>`
  blocks, a coloured-rule `<h2>`, a quick-reference `<table>` when the
  model wrote a numbered how-to, FAQ as `<details>` blocks, and a
  related-tools `<aside>` sidebar.
  ToolsHall (`FORMAT_TOOLSHALL`) — the blog-post pattern: an intro
  paragraph, plain `## H2` sections styled as blog headings, FAQ as
  `<details>`, a related-tools list, and a closing CTA box linking to the
  most relevant related page (or the homepage).

Both are a best-effort match to the patterns described for each site, not a
pixel-for-pixel copy of a real page. If you paste in one of ToolsVenue's or
ToolsHall's actual page's HTML, `render_toolsvenue()` / `render_toolshall()`
below are the one place to tighten the markup to match it exactly.
"""

import re

from publishers.base import md_to_html

from core.config import FORMAT_MARKDOWN, FORMAT_TOOLSHALL, FORMAT_TOOLSVENUE, OUTPUT_FORMATS

FORMATS = OUTPUT_FORMATS   # re-exported so callers only need this module

_FAQ_HEADING = re.compile(r"\bfaq\b|frequently asked", re.I)
_RELATED_HEADING = re.compile(r"related", re.I)
_QUICKREF_HEADING = re.compile(r"quick reference|how.?to|step.?by.?step|^steps?\b", re.I)
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_NUM_ITEM = re.compile(r"^\s*\d+[.)]\s+(.*\S)\s*$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

TV_H3_STYLE = "font-size:1.12em;font-weight:600;color:#111827;margin:20px 0 8px;"
TH_H3_STYLE = "font-size:1.2em;font-weight:700;color:#111;margin:1.4em 0 0.5em;"


# ── Shared parsing — read once, painted twice ───────────────────────────────
def _inline(text: str) -> str:
    """Markdown -> HTML for a short piece of text, unwrapped from its <p>."""
    html_text = md_to_html((text or "").strip()).strip()
    if html_text.startswith("<p>") and html_text.endswith("</p>"):
        html_text = html_text[3:-4]
    return html_text


def _html(md_text: str, h3_style: str) -> str:
    """A section's markdown -> HTML, with its H3s (question headings) styled."""
    return re.sub(r"<h3>", f'<h3 style="{h3_style}">', md_to_html(md_text or ""))


def _split_sections(body_markdown: str) -> list:
    """[(heading, section_markdown), ...] — "" heading is the lead-in intro."""
    heading, buf, sections = "", [], []
    for line in (body_markdown or "").strip("\n").split("\n"):
        m = _H2.match(line)
        if m:
            sections.append((heading, "\n".join(buf).strip()))
            heading, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    sections.append((heading, "\n".join(buf).strip()))
    return [(h, s) for h, s in sections if h or s]


def _quick_reference(md_text: str):
    """(leading_prose_markdown, [step, ...]) — items is [] with no real numbered list."""
    prose, items, in_list = [], [], False
    for line in md_text.split("\n"):
        m = _NUM_ITEM.match(line)
        if m:
            in_list = True
            items.append(m.group(1).strip())
        elif not in_list:
            prose.append(line)
    return "\n".join(prose).strip(), items


def _related_links(draft) -> list:
    """
    [{anchor, url}, ...] — the model's own structured `internal_links` first;
    a plain markdown-link scrape of the "related" section as a fallback for a
    reply that skipped the structured field but still wrote the links.
    """
    links = [l for l in (draft.meta.get("internal_links") or []) if l.get("url")]
    if links:
        return links
    for heading, body in _split_sections(draft.body_markdown):
        if _RELATED_HEADING.search(heading or ""):
            return [{"anchor": a, "url": u} for a, u in _MD_LINK.findall(body)]
    return []


def _parts(draft):
    """Everything both templates need: intro, ordinary sections (FAQ/related
    pulled out — those get bespoke markup below), the FAQ list, the links."""
    sections = _split_sections(draft.body_markdown)
    intro = next((s for h, s in sections if not h), "")
    body_sections = [(h, s) for h, s in sections
                     if h and not _FAQ_HEADING.search(h) and not _RELATED_HEADING.search(h)]
    faq = [f for f in (draft.meta.get("faq") or []) if f.get("q")]
    return intro, body_sections, faq, _related_links(draft)


def _quickref_table_or_html(heading: str, body: str, h3_style: str,
                            row_style: str, header_style: str) -> str:
    if _QUICKREF_HEADING.search(heading):
        prose, items = _quick_reference(body)
        if len(items) >= 3:
            rows = "".join(
                f'<tr><td style="{row_style}font-weight:600;">{i}</td>'
                f'<td style="{row_style}">{_inline(step)}</td></tr>'
                for i, step in enumerate(items, 1))
            table = (f'<table style="width:100%;border-collapse:collapse;margin:16px 0;'
                     f'font-size:0.97em;"><thead><tr>'
                     f'<th style="{header_style}">Step</th>'
                     f'<th style="{header_style}">What to do</th>'
                     f'</tr></thead><tbody>{rows}</tbody></table>')
            return (_html(prose, h3_style) if prose else "") + table
    return _html(body, h3_style)


# ── ToolsVenue — the tool-page pattern ──────────────────────────────────────
def render_toolsvenue(draft) -> str:
    intro, body_sections, faq, related = _parts(draft)
    h2 = ('style="font-size:1.4em;font-weight:700;color:#111827;'
          'border-left:4px solid #2563eb;padding:2px 0 2px 14px;margin:0 0 16px;"')
    section = 'style="margin:0 0 32px;"'
    row_style = "padding:10px 14px;border-bottom:1px solid #e5e7eb;vertical-align:top;"
    header_style = ("text-align:left;padding:10px 14px;border-bottom:2px solid #1f2937;"
                    "color:#1f2937;")

    html = ['<div class="tv-article" style="max-width:820px;margin:0 auto;'
            'font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
            'line-height:1.7;color:#1f2430;">']

    if intro:
        html.append(f'<section {section}><p style="font-size:1.12em;margin:0;">'
                    f'{_inline(intro)}</p></section>')

    for heading, body in body_sections:
        content = _quickref_table_or_html(heading, body, TV_H3_STYLE, row_style, header_style)
        html.append(f'<section {section}><h2 {h2}>{_inline(heading)}</h2>{content}</section>')

    if faq:
        items = "".join(
            '<details style="margin:0 0 12px;border:1px solid #e5e7eb;'
            'border-radius:8px;padding:14px 18px;">'
            f'<summary style="font-weight:600;cursor:pointer;">{_inline(f["q"])}</summary>'
            f'<p style="margin:10px 0 0;color:#374151;">{_inline(f.get("a", ""))}</p>'
            '</details>' for f in faq)
        html.append(f'<section {section}><h2 {h2}>Frequently asked questions</h2>{items}'
                    '</section>')

    if related:
        items = "".join(
            f'<li style="margin-bottom:8px;"><a href="{l["url"]}" '
            'style="color:#2563eb;text-decoration:none;font-weight:600;">'
            f'{l.get("anchor") or l["url"]}</a></li>' for l in related)
        html.append('<aside style="background:#f8fafc;border:1px solid #e5e7eb;'
                    'border-radius:12px;padding:22px 26px;">'
                    '<h3 style="margin:0 0 12px;font-size:1.1em;color:#111827;">'
                    f'Related tools</h3><ul style="margin:0;padding-left:20px;">{items}</ul>'
                    '</aside>')

    html.append('</div>')
    return "\n".join(html)


# ── ToolsHall — the blog-post pattern ───────────────────────────────────────
def render_toolshall(draft, homepage: str = "", site_label: str = "the site") -> str:
    intro, body_sections, faq, related = _parts(draft)
    h2 = f'style="font-size:1.55em;font-weight:700;color:#111;margin:2em 0 0.6em;"'
    row_style = "padding:9px 12px;border-bottom:1px solid #e5e7eb;vertical-align:top;"
    header_style = ("text-align:left;padding:9px 12px;border-bottom:2px solid #111;")

    html = ['<div class="th-article" style="max-width:760px;margin:0 auto;'
            "font-family:Georgia,'Times New Roman',serif;line-height:1.75;color:#222;\">"]

    if intro:
        html.append(f'<p style="font-size:1.08em;">{_inline(intro)}</p>')

    for heading, body in body_sections:
        content = _quickref_table_or_html(heading, body, TH_H3_STYLE, row_style, header_style)
        html.append(f'<h2 {h2}>{_inline(heading)}</h2>{content}')

    if faq:
        html.append(f'<h2 {h2}>Frequently asked questions</h2>')
        html.append("".join(
            '<details style="margin:0 0 10px;padding:6px 0;">'
            f'<summary style="font-weight:600;cursor:pointer;">{_inline(f["q"])}</summary>'
            f'<p style="margin:8px 0 0;">{_inline(f.get("a", ""))}</p></details>'
            for f in faq))

    if related:
        html.append(f'<h2 {h2}>Related tools</h2>')
        html.append('<ul style="padding-left:22px;">' + "".join(
            f'<li style="margin-bottom:6px;"><a href="{l["url"]}" '
            f'style="color:#1d4ed8;">{l.get("anchor") or l["url"]}</a></li>'
            for l in related) + '</ul>')

    cta_url = (related[0]["url"] if related else homepage) or "#"
    html.append(
        '<div style="background:#111827;color:#fff;border-radius:10px;'
        'padding:26px 30px;margin:2.5em 0 1em;text-align:center;">'
        '<p style="margin:0 0 14px;font-size:1.1em;">Ready to put this into practice?</p>'
        f'<a href="{cta_url}" style="display:inline-block;background:#fff;color:#111827;'
        f'font-weight:700;padding:10px 24px;border-radius:6px;text-decoration:none;">'
        f'Try {site_label} →</a></div>')

    html.append('</div>')
    return "\n".join(html)


# ── Entry point ──────────────────────────────────────────────────────────────
def render(draft, fmt: str, homepage: str = "", site_label: str = "the site") -> str:
    """
    The one entry point. `fmt` is one of `FORMATS` (normally
    `core.config.output_format(site)`, or a one-off override the Content page
    offers per run). Unknown or `FORMAT_MARKDOWN` -> the draft's own markdown,
    unchanged, so a plain-text fallback is always available.
    """
    if fmt == FORMAT_TOOLSVENUE:
        return render_toolsvenue(draft)
    if fmt == FORMAT_TOOLSHALL:
        return render_toolshall(draft, homepage, site_label)
    return draft.body_markdown
