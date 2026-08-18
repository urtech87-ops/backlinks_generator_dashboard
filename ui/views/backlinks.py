"""
Backlinks — the main target, in two lanes.

  Lane A (Phase 3)  auto-publish to platforms you OWN, logged to a tracker
  Lane B (Phase 4)  guest outreach: prospect, score, draft, track — you approve
                    every send, and the host publishes. Nothing on this page can
                    post to a site you don't own; the only outbound action in
                    Lane B is one email, sent by one click, after you've read it.

The guardrails are stated on the page, not just in code, because they're the
difference between links that help and a link-spam penalty.

Lane A walks top to bottom: pick the page that deserves a link → pick the
platforms you own → generate a draft per platform → read it → publish. Nothing
publishes without that last click, and every attempt lands in the tracker.
"""

import pandas as pd
import streamlit as st

from agents import backlink as bl
from agents import outreach as out
from core import config, mailer, search, tracker
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
        _lane_b(ctx, df)


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

    stats = tracker.summary(site.key, lane=tracker.LANE_OWNED)
    c.metric_row([
        ("Posts published", stats["live"], "Live on a platform you own."),
        ("Waiting as drafts", stats["drafts"], "Created, but not live until you click."),
        ("Failed attempts", stats["failed"], "Logged so they don't quietly disappear."),
        ("Pages linked to", stats["pages"], "Distinct target pages that now have links."),
    ])

    df = tracker.load(site.key, lane=tracker.LANE_OWNED)
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


# ── Lane B: human-gated guest outreach ─────────────────────────────────────
# The whole lane is a funnel with a person standing in it. The agent searches,
# scores and writes; every state change below happens because you clicked
# something, and the only thing that ever leaves this machine is one email you
# have read first.

PROSPECTS = "gb_prospects"       # session state: the last prospect search
PITCH = "gb_pitch"               # session state: the drafted pitch
GUEST_ARTICLE = "gb_article"     # session state: the drafted guest article
SENT = "gb_sent"                 # session state: the outcome of the last send

_STAGE_STATE = {"prospected": "idle", "pitched": "warn", "accepted": "ok",
                "live": "ok", "declined": "bad"}

_VERDICT_ICON = {out.WORTH: "🟢", out.MAYBE: "🟡", out.SKIP: "🔴"}


def _lane_b(ctx, coverage_df: pd.DataFrame) -> None:
    site = ctx.site

    st.info("**How this stays safe.** The agent prospects, scores and drafts. "
            "*You* press send, and the host decides whether to publish. Nothing is "
            "ever auto-posted to someone else's site, and there are no scaled, "
            "keyword-stuffed campaigns — that's exactly what Google penalises.",
            icon="🛡️")

    _outreach_readiness()
    st.divider()

    target = _lane_b_target(ctx, coverage_df)
    if target is None:
        return

    st.divider()
    _prospect_step(site, target)

    st.divider()
    prospect = _draft_step(site, target)

    st.divider()
    _approval_step(site, target, prospect)

    st.divider()
    _board_step(site)


def _stage_map(site, target) -> dict:
    """{host domain: current stage} for one target page — the board read once."""
    board = tracker.guest_board(site.key)
    if board.empty:
        return {}
    rows = board[board["target_url"] == target.url]
    return dict(zip(rows["domain"], rows["stage"]))


def _outreach_readiness() -> None:
    """What's switched on, and what each missing piece actually costs you."""
    c.section("What's ready", "Outreach works with none of this set up — you just do "
                              "more of it by hand.")
    rows = [
        ("Prospect search", not search.missing(),
         f"Searching with {search.PROVIDERS[search.provider()]}."
         if not search.missing()
         else "Add a search API key in Settings, or switch the provider to DuckDuckGo. "
              "You can still add sites by hand."),
        ("Writer model", config.is_set("OPENROUTER_API_KEY"),
         f"Pitches and drafts written by `{config.get('BACKLINK_MODEL', 'not set')}`."
         if config.is_set("OPENROUTER_API_KEY")
         else "No OpenRouter key, so nothing can be drafted yet."),
        ("Email sending", mailer.configured(),
         f"Approved pitches can send from {mailer.from_address()}."
         if mailer.configured()
         else "Optional. Without it you copy the pitch and send it yourself — which is "
              "what most people should do anyway."),
    ]
    for label, ok, blurb in rows:
        cols = st.columns([2, 1, 4])
        cols[0].markdown(f"**{label}**")
        with cols[1]:
            c.show_badge("ok" if ok else "idle", "ready" if ok else "not set")
        cols[2].caption(blurb)
    c.nav_button("Open Settings", "Settings", key="gb_settings")


# ── Step 1: the page the guest post should link to ─────────────────────────
def _lane_b_target(ctx, coverage_df: pd.DataFrame):
    """Same ranking Lane A uses — a guest post to a broken page is wasted too."""
    site = ctx.site
    c.section("1 · Pick the page the guest post should link to",
              "The same ranking Lane A uses. A hard-won guest link pointing at a page "
              "Google won't index is the most expensive way to earn nothing.")

    targets, rank_source = bl.rank_targets(site, coverage_df, ctx.start, ctx.end)
    if not targets:
        c.empty_state(
            "No link-eligible pages yet",
            "Outreach costs you real time and someone else's goodwill, so it only makes "
            "sense once the page you're pointing at is one Google has accepted.",
            steps=[
                "Work the **Fix Plan** top-down: broken URLs, then rewrites.",
                "Press **Refresh live data** in the sidebar to re-check coverage.",
                "Come back when pages start showing as indexed.",
            ],
            icon="🅱️",
        )
        return None

    if rank_source != "live":
        st.caption("⚠️ No Search Console performance data for this range, so this is the "
                   "eligible list rather than a performance ranking — unvalidated.")

    choice = st.selectbox(
        "Target page", options=list(range(len(targets))),
        format_func=lambda i: f"{_opportunity_icon(targets[i])} {targets[i].page}"
                              f"{_metric_suffix(targets[i])}",
        key="gb_target_pick",
        help="Every pitch and draft below is written around this page.",
    )
    target = targets[choice]
    with st.container(border=True):
        st.markdown(f"**{target.url}**")
        st.caption(target.reason)
    return target


# ── Step 2: find and score prospects ───────────────────────────────────────
def _default_niche(site, target) -> str:
    """A starting point for the niche box, from the page you picked."""
    words = target.page.strip("/").replace("-", " ").replace("_", " ").replace("/", " ")
    return f"{words} {site.label}".strip() if words else site.label


def _prospect_step(site, target) -> None:
    c.section("2 · Find sites that accept guest posts",
              "Searches the phrases sites use when they *want* contributors, then reads "
              "each page and scores it. Reading only — nothing is contacted here.")

    niche = st.text_input(
        "Your niche, in plain words", value=_default_niche(site, target), key="gb_niche",
        help="What the article would be about — the words a matching site would use "
             "about itself. e.g. 'developer productivity tools'.",
    )

    cols = st.columns(2)
    limit = cols[0].slider("How many prospects to keep", 5, 25, 12, key="gb_limit",
                           help="Quality beats volume. Ten good sites you actually "
                                "email beat a hundred you don't.")
    read_pages = cols[1].checkbox(
        "Read each site's page before scoring", value=True, key="gb_read",
        help="Slower, but it's what finds the editorial guidelines, the contact "
             "address and the sites that quietly sell links.")

    with st.expander("What exactly gets searched"):
        for query in out.queries_for(niche):
            st.markdown(f"- `{query}`")
        extra = st.text_area(
            "Add your own searches, one per line (optional)", key="gb_extra", height=90,
            placeholder='"guest author" home automation',
            help="Any search you'd type yourself. Same treatment: read, scored, never "
                 "contacted.")

    if search.missing():
        st.warning(f"{search.PROVIDERS[search.provider()]} needs a key before it can "
                   "search. Add one in Settings → Prospecting, switch the provider to "
                   "DuckDuckGo, or add sites by hand below.", icon="🔑")

    if st.button("🔎 Find prospects", type="primary", key="gb_find",
                 disabled=not niche.strip() or bool(search.missing())):
        bar = st.progress(0.0, text="Searching…")
        result = out.find_prospects(
            niche, limit=limit, extra_queries=extra.splitlines(),
            read_pages=read_pages,
            progress=lambda fraction, text: bar.progress(min(fraction, 1.0), text=text),
        )
        bar.empty()
        st.session_state[PROSPECTS] = {
            "site": site.key, "niche": niche, "items": result["prospects"],
            "detail": result["detail"], "failures": result["failures"],
            "ok": result["ok"],
        }
        st.session_state.pop(PITCH, None)
        st.session_state.pop(GUEST_ARTICLE, None)

    with st.expander("Or add a site you already know about"):
        st.caption("An editor someone recommended, or a site search missed. It gets "
                   "read and scored exactly the same way.")
        manual = st.text_input("Site or guidelines URL", key="gb_manual",
                               placeholder="https://example.com/write-for-us")
        if st.button("Score this site", key="gb_manual_add", disabled=not manual.strip()):
            with st.spinner(f"Reading {manual}…"):
                prospect = out.prospect_from_url(manual, niche)
            state = st.session_state.get(PROSPECTS) or {
                "site": site.key, "niche": niche, "items": [], "detail": "",
                "failures": [], "ok": True}
            state["items"] = ([p for p in state["items"]
                               if p.domain != prospect.domain] + [prospect])
            state["site"] = site.key
            st.session_state[PROSPECTS] = state
            st.success(f"Scored {prospect.domain}: {prospect.score}/100 — "
                       f"{prospect.verdict}.")

    _prospect_results(site, target)


def _prospect_results(site, target) -> None:
    """The scored list, the evidence behind each score, and the shortlist button."""
    state = st.session_state.get(PROSPECTS) or {}
    if state.get("site") != site.key or not state.get("items"):
        if state.get("failures"):
            for failure in state["failures"]:
                st.error(failure)
        st.caption("No prospects yet. Describe your niche and press **Find prospects**.")
        return

    prospects = state["items"]
    st.caption(state.get("detail", ""))
    for failure in state.get("failures", []):
        st.warning(f"One search didn't run: {failure}", icon="🔎")

    st.dataframe(
        pd.DataFrame([{
            "": _VERDICT_ICON.get(p.verdict, ""),
            "Site": p.domain,
            "Score": p.score,
            "Verdict": p.verdict,
            "Relevance": f"{p.relevance}/50",
            "Quality": f"{p.quality}/50",
            "Contact found": p.contact or "—",
            "Warnings": len(p.warnings),
        } for p in prospects]),
        width="stretch", hide_index=True,
    )
    st.caption("Scored only on what's on the page: your niche words, whether it has "
               "real editorial guidelines, whether it reads like a link seller. There "
               "is no domain-authority figure here because nothing in this dashboard "
               "can measure one — don't let a number stand in for reading the site.")

    stages = _stage_map(site, target)
    for prospect in prospects:
        stage = stages.get(prospect.domain, "")
        header = (f"{_VERDICT_ICON.get(prospect.verdict, '')} {prospect.domain} · "
                  f"{prospect.score}/100"
                  f"{f' · {tracker.STATUS_LABEL.get(stage, stage)}' if stage else ''}")
        with st.expander(header):
            st.markdown(f"[{prospect.url}]({prospect.url})")
            if prospect.title:
                st.caption(prospect.title)
            for warning in prospect.warnings:
                st.warning(warning, icon="⚠️")
            for reason in prospect.reasons:
                st.markdown(f"- {reason}")
            if prospect.contact:
                st.caption(f"Contact printed on the page: `{prospect.contact}`")
            else:
                st.caption("No email on the page — check for a contact form, or find "
                           "the editor yourself before pitching.")

    shortlist = st.multiselect(
        "Shortlist the ones worth your time",
        options=[p.domain for p in prospects],
        default=[p.domain for p in prospects if p.verdict == out.WORTH],
        key="gb_shortlist",
        help="Saved to the tracker as *prospected*. Nothing is contacted — this is "
             "just your list.",
    )
    if st.button("➕ Save shortlist to the tracker", key="gb_save_shortlist",
                 disabled=not shortlist):
        by_domain = {p.domain: p for p in prospects}
        for domain in shortlist:
            prospect = by_domain[domain]
            tracker.log_guest(
                site.key, target.url, domain, "prospected",
                detail=f"Score {prospect.score}/100 · {prospect.verdict} · {prospect.url}",
                contact=prospect.contact,
            )
        st.success(f"Saved {len(shortlist)} site(s) as prospected. Nothing has been "
                   "contacted.")


# ── Step 3: draft the pitch and the article ────────────────────────────────
def _known_prospects(site, target) -> dict:
    """
    Everything you could pitch for this page: what the last search found, plus
    anything already on the tracker (so a draft survives a page refresh).
    """
    state = st.session_state.get(PROSPECTS) or {}
    found = {p.domain: p for p in state.get("items", [])} \
        if state.get("site") == site.key else {}

    board = tracker.guest_board(site.key)
    if not board.empty:
        for _, row in board[board["target_url"] == target.url].iterrows():
            if row["domain"] not in found:
                # Tracked earlier, in another session: enough to draft from.
                found[row["domain"]] = out.Prospect(
                    domain=row["domain"], url=f"https://{row['domain']}",
                    contact=row["contact"], verdict=out.MAYBE,
                )
    return found


def _draft_step(site, target):
    c.section("3 · Draft the pitch and the article",
              f"Written by your backlink model (`{config.get('BACKLINK_MODEL', 'not set')}`) "
              "for this one site. You edit both before anything is sent.")

    known = _known_prospects(site, target)
    if not known:
        st.caption("Find or add a prospect first, then come back here.")
        return None

    domains = sorted(known)
    stages = _stage_map(site, target)
    stages = {d: stages.get(d, "") for d in domains}
    domain = st.selectbox(
        "Who are you pitching?", options=domains,
        format_func=lambda d: f"{d}"
                              f"{f' · {tracker.STATUS_LABEL.get(stages[d], stages[d])}' if stages[d] else ' · not tracked'}",
        key="gb_pitch_pick",
    )
    prospect = known[domain]

    if prospect.verdict == out.SKIP and prospect.warnings:
        st.error(f"This one scored {prospect.score}/100 and was marked **skip**: "
                 f"{prospect.warnings[0]} You can still draft for it, but read that "
                 "line again first.", icon="🚫")

    angle = st.text_input(
        "The angle, if the host already agreed one (optional)", key="gb_angle",
        placeholder="e.g. they asked for a walkthrough aimed at beginners",
        help="Leave blank when you're pitching cold — the pitch offers three ideas.")
    notes = st.text_input(
        "Anything the writer should know (optional)", key="gb_notes",
        placeholder="e.g. mention that I maintain the tool myself")

    # A missing key disables writing, but never hides a draft you already have —
    # you should still be able to read, edit and send what's on screen.
    can_draft = config.is_set("OPENROUTER_API_KEY")
    if not can_draft:
        st.warning("No OpenRouter key saved, so nothing new can be drafted.", icon="🔑")
        c.nav_button("Add an OpenRouter key", "Settings", key="gb_settings_key")

    cols = st.columns(2)
    if cols[0].button("✍️ Write the pitch", type="primary", key="gb_write_pitch",
                      disabled=not can_draft):
        with st.spinner(f"Writing a pitch for {domain}…"):
            pitch = out.draft_pitch(site, target, prospect, notes)
        if pitch.ok:
            st.session_state[PITCH] = {
                "site": site.key, "domain": domain, "target_url": target.url,
                "subject": pitch.subject, "body": pitch.body, "ideas": pitch.ideas,
                "detail": pitch.detail,
            }
            # Overwrite the edit boxes as well, or a rewrite would leave the old
            # text on screen — Streamlit keeps whatever is under a widget key.
            st.session_state[_key("subject", domain)] = pitch.subject
            st.session_state[_key("body", domain)] = pitch.body
            st.session_state.pop(SENT, None)
        else:
            st.error(pitch.detail)

    if cols[1].button("📝 Write the guest article", key="gb_write_article",
                      disabled=not can_draft,
                      help="The draft you'd offer them. It is never published from "
                           "here — if they say yes, they publish it."):
        with st.spinner(f"Writing a guest article for {domain}…"):
            draft = out.draft_guest_article(site, target, prospect, angle, notes)
        if draft.ok:
            st.session_state[GUEST_ARTICLE] = {
                "site": site.key, "domain": domain, "target_url": target.url,
                "title": draft.article.title, "body": draft.article.body_markdown,
                "detail": draft.detail,
            }
            st.session_state[_key("article_title", domain)] = draft.article.title
            st.session_state[_key("article_body", domain)] = draft.article.body_markdown
        else:
            st.error(draft.detail)

    _pitch_editor(site, target, domain)
    _article_editor(site, target, domain)
    return prospect


def _key(name: str, domain: str) -> str:
    """
    Widget keys are per-prospect on purpose: switching from one host to another
    must not leave the previous site's pitch sitting in the box.
    """
    return f"gb_{name}_{domain}"


def _for_this(state_key: str, site, target, domain: str) -> dict:
    """The stored draft, but only if it belongs to this site/page/prospect."""
    stored = st.session_state.get(state_key) or {}
    matches = (stored.get("site") == site.key and stored.get("domain") == domain
               and stored.get("target_url") == target.url)
    return stored if matches else {}


def _pitch_editor(site, target, domain: str) -> None:
    stored = _for_this(PITCH, site, target, domain)
    if not stored:
        return
    subject_key, body_key = _key("subject", domain), _key("body", domain)
    st.session_state.setdefault(subject_key, stored["subject"])
    st.session_state.setdefault(body_key, stored["body"])

    st.markdown("**The pitch**")
    st.caption(stored["detail"])
    st.text_input("Subject", key=subject_key)
    st.text_area("Email", height=320, key=body_key,
                 help="Edit freely — what's in this box is exactly what would send.")
    if stored.get("ideas"):
        st.caption("Article ideas offered: " + " · ".join(stored["ideas"]))

    problems = out.pitch_checks(st.session_state[subject_key],
                                st.session_state[body_key])
    for problem in problems:
        st.warning(problem, icon="✉️")
    if not problems:
        st.success("Reads like a personal email — no mail-merge or link-request "
                   "wording in it.", icon="✉️")


def _article_editor(site, target, domain: str) -> None:
    stored = _for_this(GUEST_ARTICLE, site, target, domain)
    if not stored:
        return
    title_key, body_key = _key("article_title", domain), _key("article_body", domain)
    st.session_state.setdefault(title_key, stored["title"])
    st.session_state.setdefault(body_key, stored["body"])

    with st.expander(f"The guest article for {domain}", expanded=True):
        st.caption(stored["detail"])
        st.text_input("Article title", key=title_key)
        st.text_area("Article (markdown)", height=420, key=body_key)
        body = st.session_state[body_key]
        links = body.count(target.url)
        if links == 1:
            st.success(f"Contains one link to {target.url} — as intended.", icon="🔗")
        elif links == 0:
            st.error(f"No link to {target.url} in the text. Add one where it genuinely "
                     "helps the reader, or regenerate.", icon="🔗")
        else:
            st.warning(f"{links} links to the same page. One contextual link reads as "
                       "natural; several read as link-building, and an editor will "
                       "either cut them or bin the piece.", icon="🔗")
        st.download_button(
            "⬇️ Download the draft (markdown)",
            f"# {st.session_state[title_key]}\n\n{body}".encode(),
            file_name=f"guest-post-{domain}.md", mime="text/markdown",
            key=_key("article_dl", domain),
            help="Send this to the host once they've said yes. Nothing here posts it "
                 "for you.")


# ── Step 4: approve and send ───────────────────────────────────────────────
def _approval_step(site, target, prospect) -> None:
    c.section("4 · Approve and send",
              "The one outbound action in this lane. One pitch, one click, after "
              "you've read it.")
    if prospect is None:
        st.caption("Nothing to send yet.")
        return

    domain = prospect.domain
    stored = _for_this(PITCH, site, target, domain)
    if not stored:
        st.caption(f"Draft a pitch for {domain} first.")
        return

    subject = st.session_state.get(_key("subject", domain), stored["subject"])
    body = st.session_state.get(_key("body", domain), stored["body"])
    stage = _stage_map(site, target).get(domain, "")
    if stage in ("pitched", "accepted", "live"):
        st.info(f"You've already pitched {domain} for this page — it's at "
                f"*{tracker.STATUS_LABEL.get(stage, stage)}*. Pitching the same site "
                "twice for the same page is how you get blocked.", icon="📌")

    if mailer.configured():
        to = st.text_input("Send to", value=prospect.contact, key=_key("to", domain),
                           placeholder="editor@example.com",
                           help="The address on their guidelines page, if it had one. "
                                "Check it's a person, not a no-reply.")
        approved = st.checkbox(
            f"I have read this pitch and I approve sending it to {domain}.",
            key=_key("approve", domain),
            help="The send button stays disabled until this is ticked. That's "
                 "deliberate.")
        if st.button("✉️ Send this pitch", type="primary", key="gb_send",
                     disabled=not approved or not to.strip()):
            with st.spinner(f"Sending to {to}…"):
                result = mailer.send(to, subject, body)
            if result["ok"]:
                tracker.log_guest(site.key, target.url, domain, "pitched",
                                  title=subject, detail=result["detail"], contact=to)
            st.session_state[SENT] = result
        sent = st.session_state.get(SENT)
        if sent:
            (st.success if sent["ok"] else st.error)(sent["detail"])
    else:
        st.caption("No email set up — which is fine, and arguably better. Copy the "
                   "pitch and send it from your own mailbox, then mark it below.")
        st.code(f"Subject: {subject}\n\n{body}", language="text")
        if prospect.contact:
            st.caption(f"Their address, from the page: `{prospect.contact}`")

    st.write("")
    cols = st.columns([2, 3])
    if cols[0].button("📌 I sent it — mark as pitched", key="gb_mark_pitched"):
        tracker.log_guest(site.key, target.url, domain, "pitched", title=subject,
                          detail="Sent by hand",
                          contact=st.session_state.get(_key("to", domain),
                                                       prospect.contact))
        st.success(f"{domain} marked as pitched. It's on the board below.")
    cols[1].caption("Use this whichever way you sent it — the board is only as honest "
                    "as what you tell it.")


# ── Step 5: the outreach board ─────────────────────────────────────────────
def _board_step(site) -> None:
    c.section("Outreach board",
              "Every prospect for this site and where it stands. Declines are kept on "
              "purpose — they stop you pitching the same editor twice.")

    stats = tracker.guest_summary(site.key)
    c.metric_row([
        ("Prospected", stats["prospected"], tracker.GUEST_STAGE_HELP["prospected"]),
        ("Pitched", stats["pitched"], tracker.GUEST_STAGE_HELP["pitched"]),
        ("Accepted", stats["accepted"], tracker.GUEST_STAGE_HELP["accepted"]),
        ("Live", stats["live"], tracker.GUEST_STAGE_HELP["live"]),
        ("Declined", stats["declined"], tracker.GUEST_STAGE_HELP["declined"]),
    ])

    board = tracker.guest_board(site.key)
    if board.empty:
        st.caption("Nothing tracked yet. Shortlisting a prospect above puts it here. "
                   f"The file is `{tracker.PATH}` — the same one Lane A writes to.")
        return

    view = board.copy()
    view["Stage"] = view["stage"].map(tracker.STATUS_LABEL).fillna(view["stage"])
    st.dataframe(
        view[["domain", "Stage", "target_url", "contact", "post_url", "updated",
              "detail"]].rename(columns={
                  "domain": "Site", "target_url": "Links to", "contact": "Contact",
                  "post_url": "Published at", "updated": "Last change",
                  "detail": "Note"}),
        width="stretch", hide_index=True,
    )

    st.markdown("**Move one on**")
    st.caption("Update a prospect when the host replies. Nothing moves on its own — "
               "the host's answer is the only thing that changes a stage.")
    labels = [f"{row['domain']} → {row['target_url']} "
              f"({tracker.STATUS_LABEL.get(row['stage'], row['stage'])})"
              for _, row in board.iterrows()]
    index = st.selectbox("Prospect", options=list(range(len(board))),
                         format_func=lambda i: labels[i], key="gb_board_pick")
    row = board.iloc[index]

    stage = st.radio("New stage", options=tracker.GUEST_STAGES,
                     index=tracker.GUEST_STAGES.index(row["stage"])
                     if row["stage"] in tracker.GUEST_STAGES else 0,
                     format_func=lambda s: tracker.STATUS_LABEL.get(s, s),
                     key="gb_board_stage", horizontal=True)
    st.caption(tracker.GUEST_STAGE_HELP.get(stage, ""))

    cols = st.columns([3, 2])
    note = cols[0].text_input("Note (optional)", key="gb_board_note",
                              placeholder="e.g. asked for 1,200 words by Friday")
    post_url = cols[1].text_input("Published URL", value=row["post_url"],
                                  key="gb_board_url",
                                  placeholder="https://host.com/the-post",
                                  help="Fill this in when it goes live, so you can find "
                                       "the link again.")
    if st.button("💾 Update this prospect", type="primary", key="gb_board_save"):
        tracker.log_guest(site.key, row["target_url"], row["domain"], stage,
                          title=row["title"], detail=note, contact=row["contact"],
                          post_url=post_url.strip())
        st.success(f"{row['domain']} → {tracker.STATUS_LABEL.get(stage, stage)}.")

    st.download_button(
        "⬇️ Export the outreach board (CSV)", board.to_csv(index=False).encode(),
        file_name=f"{site.key}_guest_outreach.csv", mime="text/csv",
        key="gb_board_export",
    )
