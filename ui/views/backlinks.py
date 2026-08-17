"""
Backlinks — the main target, in two lanes.

  Lane A (Phase 3)  auto-publish to platforms you OWN, logged to a tracker
  Lane B (Phase 4)  guest outreach: prospect, score, draft, track — you approve
                    every send, and the host publishes

The guardrails are stated on the page, not just in code, because they're the
difference between links that help and a link-spam penalty.
"""

import streamlit as st

from core import config
from core.classifier import HEALTHY, CRAWL_BUDGET
from ui import components as c
from ui import data as d

OWNED_PLATFORMS = [
    ("dev.to", "DEVTO_API_KEY", "Publishes an article under your own dev.to account."),
    ("Blogger", "BLOGGER_BLOG_ID", "Posts to a Blogger blog you own."),
]


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Backlinks · {site.label}",
        "Links that actually count — earned on platforms you own, plus guest posts "
        "you approve one at a time.",
    )

    df, source = d.coverage_frame(site)
    summary = d.health_summary(df)
    counts = summary["counts"]
    linkable = counts.get(HEALTHY, 0)
    crawl = counts.get(CRAWL_BUDGET, 0)

    c.metric_row([
        ("Link-eligible pages", linkable,
         "Indexed pages. Links to these compound."),
        ("Pages links can rescue", crawl,
         "Discovered but never crawled — the one bucket where a backlink helps."),
        ("Not worth linking to yet", counts.get("Plumbing", 0) + counts.get("Content", 0),
         "Broken or quality-rejected. A link here is wasted."),
    ])
    c.data_source_note(source)

    if linkable == 0:
        st.warning("No indexed pages to link to yet. Clear the red and orange buckets on "
                   "the Fix Plan first — that's what makes links pay off.", icon="🔧")
        c.nav_button("Open the Fix Plan", "Analysis", key="bl_to_fix")

    st.divider()

    lane_a, lane_b = st.tabs(["🅰️ Auto-publish (platforms you own)",
                              "🅱️ Guest outreach (you approve)"])

    with lane_a:
        c.coming_soon(
            "Lane A — auto-publish to owned platforms",
            "Phase 3",
            "Ranks your winner pages from Search Console, drafts a genuinely useful "
            "article tailored to each platform, publishes it to accounts you own, and "
            "logs every link in a tracker so you can see what stuck.",
            [
                "Winner ranking from impressions and average position.",
                "Platform-tailored drafts written with your BACKLINK_MODEL.",
                "One-click publish per page, to dev.to / Blogger / your own WordPress.",
                "A tracker in `data/` recording every URL, platform, target page and date.",
            ],
            icon="🅰️",
        )
        c.section("Platform readiness", "Auto-publishing is only ever allowed on "
                                        "platforms you own.")
        for name, key, what in OWNED_PLATFORMS:
            cols = st.columns([2, 1, 4])
            cols[0].markdown(f"**{name}**")
            with cols[1]:
                ok = config.is_set(key)
                c.show_badge("ok" if ok else "idle", "connected" if ok else "not set")
            cols[2].caption(what)
        wp = config.wp_credentials(site)
        cols = st.columns([2, 1, 4])
        cols[0].markdown("**Your WordPress**")
        with cols[1]:
            ok = bool(wp["username"] and wp["app_password"])
            c.show_badge("ok" if ok else "idle", "connected" if ok else "not set")
        cols[2].caption("Posts to your own site — as a draft, like everything else.")
        c.nav_button("Add platform keys", "Settings", key="bl_settings")

    with lane_b:
        st.info("**How this stays safe.** The agent prospects, scores and drafts. "
                "*You* press send, and the host decides whether to publish. Nothing is "
                "ever auto-posted to someone else's site, and there are no scaled, "
                "keyword-stuffed campaigns — that's exactly what Google penalises.",
                icon="🛡️")
        c.coming_soon(
            "Lane B — human-gated guest outreach",
            "Phase 4",
            "Finds relevant sites that accept guest posts, scores them on real relevance "
            "and quality, drafts a tailored article and a personal pitch, and tracks each "
            "prospect from found → pitched → accepted → live.",
            [
                "Prospecting from search, scoped to your niche.",
                "A quality/relevance score per prospect, so you can ignore the junk.",
                "A tailored draft plus a pitch written for that specific site.",
                "An outreach tracker with an explicit approval step before anything sends.",
            ],
            icon="🅱️",
        )
