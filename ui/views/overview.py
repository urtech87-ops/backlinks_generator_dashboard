"""
Overview — the front page. Where this site stands, and the next thing to do.

Deliberately read-only for now: it summarises what the Analysis agent already
knows and points at the page that acts on it. Phase 7 turns it into the
conductor that launches the content and backlink runs from here.
"""

import streamlit as st

from core import config
from core.classifier import PLUMBING, CONTENT, CRAWL_BUDGET, HEALTHY
from ui import components as c
from ui import data as d


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Overview · {site.label}",
        "The state of the site in one screen, and the next thing worth doing.",
    )

    df, source = d.coverage_frame(site)
    summary = d.health_summary(df)
    counts = summary["counts"]

    # ── Indexing health ────────────────────────────────────────────────────
    c.section("Indexing health",
              "Backlinks to a page Google hasn't indexed do nothing. This is the "
              "number that gates everything else.")
    c.metric_row([
        ("Pages tracked", summary["total"]),
        ("Indexed", summary["healthy"], "Eligible for backlinks and outreach."),
        ("Need attention", summary["problems"], "Not indexed for one of the reasons below."),
        ("Share indexed", f"{summary['pct']}%"),
    ])
    if summary["total"]:
        st.progress(summary["healthy"] / summary["total"])
    c.data_source_note(source)

    st.divider()

    # ── What to do next ────────────────────────────────────────────────────
    c.section("What to do next",
              "In order. Each step unlocks the one under it — fixing plumbing is "
              "worth more than any link you could build today.")

    actions = _next_actions(counts, summary)
    if not actions:
        st.success("Nothing urgent in the indexing data. Time to publish and build links.")
    for i, (icon, title, detail, page, cta) in enumerate(actions, 1):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{i}. {icon} {title}**")
                st.caption(detail)
            with right:
                c.nav_button(cta, page, key=f"ov_action_{i}")

    st.divider()

    # ── System status ──────────────────────────────────────────────────────
    c.section("System status", "What's connected, and what's still waiting on a key.")
    for row in _system_status(ctx):
        cols = st.columns([2, 1, 4])
        cols[0].markdown(f"**{row['name']}**")
        with cols[1]:
            c.show_badge(row["state"], row["label"])
        cols[2].caption(row["detail"])

    if not ctx.creds:
        st.write("")
        c.empty_state(
            "Running on seed data",
            "Everything on this page is your real 16 August Search Console snapshot, "
            "so the Fix Plan is useful today. Connect the Google APIs to see whether "
            "your fixes have landed since.",
            steps=[
                "Open **Settings → Google Search Console + Analytics**.",
                "Point it at your service-account JSON file.",
                "Run **Test connections** — it checks each API separately and tells "
                "you exactly which step failed.",
            ],
            icon="🟡",
        )


def _next_actions(counts: dict, summary: dict) -> list:
    """Turn the bucket counts into a short, ordered to-do list."""
    actions = []
    if counts.get(PLUMBING):
        actions.append((
            "🔴", f"Fix {counts[PLUMBING]} broken URLs",
            "Redirect errors and 404s. Google can't reach these at all, so no amount "
            "of content or links will help until they resolve. Cheapest win on the list.",
            "Analysis", "Fix Plan",
        ))
    if counts.get(CONTENT):
        actions.append((
            "🟠", f"Rewrite {counts[CONTENT]} rejected pages",
            "Google crawled these and declined to index them on quality. They need real "
            "use-cases, a worked example and an FAQ — not more links.",
            "Content", "Write",
        ))
    if counts.get(CRAWL_BUDGET):
        actions.append((
            "🟡", f"Get {counts[CRAWL_BUDGET]} pages crawled",
            "Discovered but never crawled. Internal links from strong pages, plus a "
            "couple of genuine backlinks. This is the one bucket where link-building "
            "actually moves the needle.",
            "Backlinks", "Backlinks",
        ))
    if counts.get(HEALTHY):
        actions.append((
            "🟢", f"Build links to {counts[HEALTHY]} healthy pages",
            "These are indexed, so links to them compound. Auto-publish to platforms "
            "you own; pitch guest posts by hand.",
            "Backlinks", "Backlinks",
        ))
    return actions


def _system_status(ctx) -> list:
    """One line per moving part, with a plain-language explanation."""
    rows = []

    if ctx.creds:
        email = config.service_account_email()
        rows.append({"name": "Search Console + GA4", "state": "ok", "label": "connected",
                     "detail": f"Service account found{f' ({email})' if email else ''}. "
                               "Use Settings → Test connections to confirm access."})
    else:
        rows.append({"name": "Search Console + GA4", "state": "warn", "label": "seed mode",
                     "detail": "No service-account file yet, so indexing views use the "
                               "16 Aug snapshot and the live-only views stay empty."})

    if config.is_set("OPENROUTER_API_KEY"):
        rows.append({"name": "AI models", "state": "ok", "label": "key saved",
                     "detail": "Analysis: {} · Backlinks: {} · Content: {}".format(
                         config.get("ANALYSIS_MODEL", "not set"),
                         config.get("BACKLINK_MODEL", "not set"),
                         config.get("CONTENT_MODEL", "not set"))})
    else:
        rows.append({"name": "AI models", "state": "warn", "label": "no key",
                     "detail": "Add an OpenRouter key in Settings to let the agents "
                               "draft anything."})

    wp = config.wp_credentials(ctx.site)
    if wp["username"] and wp["app_password"]:
        rows.append({"name": "WordPress drafts", "state": "ok", "label": "ready",
                     "detail": f"Drafts will be created on {wp['url']} as {wp['username']}. "
                               "Always as a draft — never published live."})
    else:
        rows.append({"name": "WordPress drafts", "state": "warn", "label": "not set up",
                     "detail": f"Add a WordPress username + application password for "
                               f"{ctx.site.label} in Settings to publish drafts."})

    owned = [n for n, k in (("dev.to", "DEVTO_API_KEY"), ("Blogger", "BLOGGER_BLOG_ID"))
             if config.is_set(k)]
    rows.append({
        "name": "Owned platforms",
        "state": "ok" if owned else "idle",
        "label": ", ".join(owned) if owned else "none yet",
        "detail": "Where the backlink agent may auto-publish. Only platforms you own — "
                  "guest posts always wait for your approval.",
    })
    return rows
