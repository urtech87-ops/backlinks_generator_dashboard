"""
Content — the writing side.

Two paths exist by design:
  · the QUALITY path is already built, as the skills in `.claude/skills/`. You
    run it in Claude Code and it produces a researched, sourced article.
  · the FAST path (topic → draft, in the dashboard, via OpenRouter) is Phase 5.

This page is honest about that split rather than showing buttons that do
nothing.
"""

import streamlit as st

from core import config
from ui import components as c


SKILLS = [
    ("content-agent-orchestrator", "Runs the whole pipeline end to end for one topic."),
    ("keyword-researcher", "Real keywords from Search Console first, free expansion second."),
    ("website-brand-scraper", "Learns your voice and the internal pages to link to."),
    ("competitor-site-scraper", "Finds the gap competitors cover thinly or miss."),
    ("blog-writer-seo-aeo-geo", "Writes the article to rank *and* be quotable by AI engines."),
    ("blog-image-generator", "Featured + supporting images, or image briefs if no image API."),
    ("wordpress-publisher", "Creates the WordPress draft. Always a draft."),
]


def render(ctx) -> None:
    c.page_header(
        f"Content · {ctx.site.label}",
        "Turn a topic into a WordPress draft that's actually worth indexing.",
    )

    st.info("**Quality over volume.** Thin AI pages are what got these pages rejected "
            "in the first place — the Fix Plan's orange bucket is the receipt. Every "
            "path here ends in a **draft** you review, never a live post.", icon="⚠️")

    c.section("Available today — the quality path",
              "These skills already work. Run them from Claude Code in this folder; "
              "they read the same .env you set up on the Settings page.")
    with st.container(border=True):
        st.markdown("Ask Claude Code: **“run the content agent on <your topic>”**")
        st.caption("The orchestrator calls the rest in order and finishes with a "
                   "WordPress draft.")
        for name, what in SKILLS:
            st.markdown(f"- `{name}` — {what}")

    st.divider()

    c.coming_soon(
        "In-dashboard drafting",
        "Phase 5",
        "A fast path that stays inside this dashboard: type a topic, the Content agent "
        "researches it, writes an SEO/AEO/GEO article with your CONTENT_MODEL, adds an "
        "image (or an image brief), and files it as a WordPress draft.",
        [
            "Topic box, plus one-click hand-off from a Fix Plan page that needs rewriting.",
            "Research → outline → article, with real sources and no invented statistics.",
            "Meta title, description, slug, tags, FAQ and schema alongside the body.",
            "The draft lands in WordPress for you to read before anything goes live.",
        ],
        icon="✍️",
    )

    st.divider()
    c.section("Readiness for this site", "What the content path still needs from you.")
    for row in _readiness(ctx.site):
        cols = st.columns([2, 1, 4])
        cols[0].markdown(f"**{row['name']}**")
        with cols[1]:
            c.show_badge(row["state"], row["label"])
        cols[2].caption(row["detail"])
    c.nav_button("Open Settings", "Settings", key="content_settings")


def _readiness(site: config.Site) -> list:
    rows = []
    wp = config.wp_credentials(site)
    ready = bool(wp["username"] and wp["app_password"])
    rows.append({
        "name": "WordPress drafts", "state": "ok" if ready else "warn",
        "label": "ready" if ready else "needs a password",
        "detail": (f"Drafts go to {wp['url']} as {wp['username']}."
                   if ready else
                   f"Add a username + application password for {site.label} in Settings."),
    })

    has_model = config.is_set("CONTENT_MODEL") and config.is_set("OPENROUTER_API_KEY")
    rows.append({
        "name": "Writing model", "state": "ok" if has_model else "warn",
        "label": "ready" if has_model else "not set",
        "detail": (f"Using {config.get('CONTENT_MODEL')} — use your strongest model here."
                   if has_model else
                   "Set an OpenRouter key and a Content model in Settings."),
    })

    provider = config.get("IMAGE_API_PROVIDER", "dummy").lower()
    live_images = provider not in ("", "dummy") and config.is_set("IMAGE_API_KEY")
    rows.append({
        "name": "Images", "state": "ok" if live_images else "idle",
        "label": provider or "dummy",
        "detail": (f"Images will be generated with {provider}."
                   if live_images else
                   "No image API yet — the agent writes a detailed image brief instead, "
                   "so drafting never blocks."),
    })
    return rows
