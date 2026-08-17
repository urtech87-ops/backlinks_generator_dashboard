"""
Backlinks — the main target, in two lanes.

  Lane A (Phase 3)  auto-publish to platforms you OWN, logged to a tracker
  Lane B (Phase 4)  guest outreach: prospect, score, draft, track — you approve
                    every send, and the host publishes

The guardrails are stated on the page, not just in code, because they're the
difference between links that help and a link-spam penalty.

Lane A walks top to bottom: pick the page that deserves a link → pick the
platforms you own → generate a draft per platform → read it → publish. Nothing
publishes without that last click, and every attempt lands in the tracker.
"""

import pandas as pd
import streamlit as st

from agents import backlink as bl
from core import config, tracker
from core.classifier import HEALTHY, CRAWL_BUDGET
from publishers import PLATFORMS, blogger
from publishers.base import Article
from ui import components as c
from ui import data as d

DRAFTS = "bl_drafts"            # session state: the generated drafts
RESULTS = "bl_results"          # session state: the last publish outcomes


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

    if linkable == 0 and crawl == 0:
        st.warning("No pages worth linking to yet. Clear the red and orange buckets on "
                   "the Fix Plan first — that's what makes links pay off.", icon="🔧")
        c.nav_button("Open the Fix Plan", "Analysis", key="bl_to_fix")

    st.divider()

    lane_a, lane_b = st.tabs(["🅰️ Auto-publish (platforms you own)",
                              "🅱️ Guest outreach (you approve)"])

    with lane_a:
        _lane_a(ctx, df)
    with lane_b:
        _lane_b()


# ── Lane A ─────────────────────────────────────────────────────────────────
def _lane_a(ctx, coverage_df: pd.DataFrame) -> None:
    site = ctx.site

    st.info("**Why this is safe.** Everything here publishes to accounts *you* own — "
            "your dev.to, your Blogger, your WordPress. Posts on your own site are "
            "always created as drafts, and nothing is ever posted to someone else's "
            "site in this lane.", icon="🛡️")

    _platform_readiness(site)
    st.divider()

    # ── Step 1: the page that deserves a link ──────────────────────────────
    c.section("1 · Pick the page you want links to",
              "Ranked by where a link does the most good. Broken and quality-rejected "
              "pages are left out on purpose — a link to those is wasted.")

    targets, rank_source = bl.rank_targets(site, coverage_df, ctx.start, ctx.end)
    if not targets:
        c.empty_state(
            "No link-eligible pages yet",
            "A page only earns a link once Google has either indexed it, or at least "
            "discovered it. Right now none of this site's pages are in that state, so "
            "the Fix Plan is where the next win is.",
            steps=[
                "Work the **Fix Plan** top-down: broken URLs, then rewrites.",
                "Press **Refresh live data** in the sidebar to re-check coverage.",
                "Come back here once pages start showing as indexed.",
            ],
            icon="🔗",
        )
        return

    if rank_source == "live":
        st.caption("Ranked on live Search Console impressions and average position for "
                   "the sidebar's date range.")
    else:
        st.caption("⚠️ No Search Console performance data for this range, so this is the "
                   "eligible list rather than a performance ranking — the ordering is "
                   "unvalidated.")

    choice = st.selectbox(
        "Target page", options=list(range(len(targets))),
        format_func=lambda i: f"{_opportunity_icon(targets[i])} {targets[i].page}"
                              f"{_metric_suffix(targets[i])}",
        key="bl_target_pick",
        help="The page the article will link to. One link, placed where it's relevant.",
    )
    target = targets[choice]

    with st.container(border=True):
        st.markdown(f"**{target.url}**")
        st.caption(target.reason)
        if target.has_metrics:
            c.metric_row([
                ("Clicks", target.clicks),
                ("Impressions", f"{target.impressions:,}"),
                ("Avg position", target.position or "—"),
                ("Opportunity score", target.score),
            ])

    with st.expander(f"See all {len(targets)} eligible pages"):
        st.dataframe(
            pd.DataFrame([{
                "Page": t.page, "Opportunity": t.opportunity, "Bucket": t.bucket,
                "Clicks": t.clicks, "Impressions": t.impressions,
                "Avg position": t.position or "", "Score": t.score, "Why": t.reason,
            } for t in targets],),
            width="stretch", hide_index=True,
        )

    st.divider()

    # ── Step 2: where to publish ───────────────────────────────────────────
    c.section("2 · Choose where to publish",
              "Only platforms you own, and only the ones whose keys are saved.")

    available = [k for k, p in PLATFORMS.items() if not p.missing(site)]
    if not available:
        st.warning("None of your platforms are set up yet. Add a dev.to API key, your "
                   "Blogger details, or a WordPress application password in Settings.",
                   icon="🔑")
        c.nav_button("Open Settings", "Settings", key="bl_settings_step2")
        return

    chosen = st.multiselect(
        "Publish to", options=available,
        default=available[:1],
        format_func=lambda k: PLATFORMS[k].label,
        key="bl_platforms",
        help="One article is written per platform, tailored to that audience — the same "
             "text posted twice is duplicate content and helps nobody.",
    )

    notes = st.text_input(
        "Anything the writer should know (optional)",
        key="bl_notes", placeholder="e.g. focus on the CSV export use-case",
        help="Free text passed to the model — an angle, a use-case, an audience detail.",
    )

    st.divider()

    # ── Step 3: draft ──────────────────────────────────────────────────────
    c.section("3 · Generate the draft",
              f"Written by your backlink model (`{config.get('BACKLINK_MODEL', 'not set')}`). "
              "You read it before anything is published.")

    if not config.is_set("OPENROUTER_API_KEY"):
        st.warning("No OpenRouter key saved, so nothing can be drafted yet.", icon="🔑")
        c.nav_button("Add an OpenRouter key", "Settings", key="bl_settings_key")
        return

    if st.button("✍️ Write the articles", type="primary", key="bl_generate",
                 disabled=not chosen):
        items, problems = {}, []
        progress = st.progress(0.0, text="Reading the target page…")
        for i, key in enumerate(chosen, 1):
            progress.progress((i - 0.5) / len(chosen),
                              text=f"Writing for {PLATFORMS[key].label}…")
            result = bl.draft_article(site, target, key, notes)
            if result.ok:
                items[key] = {
                    "title": result.article.title,
                    "body": result.article.body_markdown,
                    "tags": ", ".join(result.article.tags),
                    "summary": result.article.summary,
                    "detail": result.detail,
                }
            else:
                problems.append(f"**{PLATFORMS[key].label}** — {result.detail}")
            progress.progress(i / len(chosen))
        progress.empty()

        st.session_state[DRAFTS] = {"target_url": target.url, "site": site.key,
                                    "items": items}
        st.session_state.pop(RESULTS, None)
        for problem in problems:
            st.error(problem)

    drafts = st.session_state.get(DRAFTS) or {}
    if not drafts.get("items") or drafts.get("site") != site.key:
        st.caption("Nothing drafted yet. Pick your platforms above and press the button.")
        _tracker_section(site)
        return

    if drafts["target_url"] != target.url:
        st.info(f"These drafts link to `{drafts['target_url']}`, not the page selected "
                "above. Press **Write the articles** again to draft for the new target.")

    _review_and_publish(site, drafts)
    _tracker_section(site)


def _opportunity_icon(target) -> str:
    return "🟢" if target.opportunity == bl.COMPOUND else "🟡"


def _metric_suffix(target) -> str:
    if not target.has_metrics:
        return f"  ·  {target.opportunity.lower()}"
    return (f"  ·  {target.impressions:,} impressions"
            f"{f', position {target.position}' if target.position else ''}")


def _review_and_publish(site, drafts: dict) -> None:
    """Editable drafts, one tab per platform, then the publish step."""
    st.divider()
    c.section("4 · Read it, fix anything, then publish",
              "Edit freely — what's in these boxes is exactly what gets posted.")

    keys = list(drafts["items"])
    tabs = st.tabs([PLATFORMS[k].label for k in keys])
    for tab, key in zip(tabs, keys):
        item = drafts["items"][key]
        with tab:
            st.caption(item["detail"])
            st.text_input("Title", value=item["title"], key=f"bl_title_{key}")
            st.text_input("Tags (comma-separated)", value=item["tags"],
                          key=f"bl_tags_{key}",
                          help="dev.to accepts up to four, lowercase and alphanumeric.")
            st.text_area("Article", value=item["body"], height=420, key=f"bl_body_{key}",
                         help="Markdown. It should contain exactly one link to the "
                              "target page.")
            body = st.session_state.get(f"bl_body_{key}", item["body"])
            links = body.count(drafts["target_url"])
            if links == 1:
                st.success(f"Contains one link to {drafts['target_url']} — as intended.",
                           icon="🔗")
            elif links == 0:
                st.error(f"No link to {drafts['target_url']} in the text. Add one, or "
                         "regenerate — publishing this earns you nothing.", icon="🔗")
            else:
                st.warning(f"{links} links to the same page. One contextual link reads as "
                           "natural; several read as link-building.", icon="🔗")
            if PLATFORMS[key].always_draft:
                st.caption("🛡️ Posts to your own site are always created as drafts.")

    st.write("")
    as_draft = st.checkbox(
        "Save as an unpublished draft on every platform (recommended for a first run)",
        value=False, key="bl_as_draft",
        help="dev.to and Blogger will hold the post unpublished so you can look at it "
             "there first. Your own WordPress is always a draft either way.",
    )

    if st.button("🚀 Publish now", type="primary", key="bl_publish"):
        results = []
        for key in keys:
            article = Article(
                title=st.session_state.get(f"bl_title_{key}", drafts["items"][key]["title"]),
                body_markdown=st.session_state.get(f"bl_body_{key}",
                                                   drafts["items"][key]["body"]),
                tags=[t.strip() for t in
                      st.session_state.get(f"bl_tags_{key}", "").split(",") if t.strip()],
                summary=drafts["items"][key]["summary"],
                target_url=drafts["target_url"],
            )
            with st.spinner(f"Publishing to {PLATFORMS[key].label}…"):
                results.append(bl.publish(site, article, key, as_draft=as_draft))
        st.session_state[RESULTS] = results

    for result in st.session_state.get(RESULTS, []):
        if result.ok:
            link = f" · [open it]({result.url})" if result.url else ""
            st.success(f"**{result.platform}** — {result.detail}{link}", icon="✅")
        else:
            st.error(f"**{result.platform}** — {result.detail}", icon="⚠️")


def _platform_readiness(site) -> None:
    """One row per owned platform, naming the exact settings still missing."""
    c.section("Platform readiness", "Auto-publishing is only ever allowed on platforms "
                                    "you own.")
    for key, platform in PLATFORMS.items():
        gaps = platform.missing(site)
        cols = st.columns([2, 1, 4])
        cols[0].markdown(f"**{platform.label}**")
        with cols[1]:
            c.show_badge("ok" if not gaps else "idle",
                         "ready" if not gaps else "not set")
        cols[2].caption(platform.blurb if not gaps
                        else f"{platform.blurb} Still needed: {', '.join(gaps)}.")

    cols = st.columns([2, 4])
    with cols[0]:
        c.nav_button("Add platform keys", "Settings", key="bl_settings")
    with cols[1]:
        if st.button("🔌 Test Blogger connection", key="bl_test_blogger",
                     help="Exchanges your refresh token for an access token and reads "
                          "the blog — the step most likely to be misconfigured."):
            with st.spinner("Asking Google for an access token…"):
                result = blogger.check_auth()
            (st.success if result["ok"] else st.error)(result["detail"])


def _tracker_section(site) -> None:
    """Everything Lane A has ever published for this site."""
    st.divider()
    c.section("Tracker", "Every publish attempt, including the ones that failed — a link "
                         "you only *think* you built is worse than one you know about.")

    stats = tracker.summary(site.key)
    c.metric_row([
        ("Posts published", stats["live"], "Live on a platform you own."),
        ("Waiting as drafts", stats["drafts"], "Created, but not live until you click."),
        ("Failed attempts", stats["failed"], "Logged so they don't quietly disappear."),
        ("Pages linked to", stats["pages"], "Distinct target pages that now have links."),
    ])

    df = tracker.load(site.key)
    if df.empty:
        st.caption(f"Nothing logged yet. The tracker lives at `{tracker.PATH}`.")
        return

    view = df.copy()
    view["Status"] = view["status"].map(tracker.STATUS_LABEL).fillna(view["status"])
    st.dataframe(
        view[["logged_at", "platform", "Status", "title", "target_url", "post_url",
              "detail"]].rename(columns={
                  "logged_at": "When", "platform": "Platform", "title": "Post",
                  "target_url": "Links to", "post_url": "URL", "detail": "Outcome"}),
        width="stretch", hide_index=True,
    )
    st.download_button(
        "⬇️ Export tracker (CSV)", df.to_csv(index=False).encode(),
        file_name=f"{site.key}_backlinks.csv", mime="text/csv",
    )


# ── Lane B (Phase 4) ───────────────────────────────────────────────────────
def _lane_b() -> None:
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
