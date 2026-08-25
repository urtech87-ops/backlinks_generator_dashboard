"""
Overview — the conductor, and the page you land on (Phase 7, reworked in Phase 8).

Phase 7 made this page decide what the other pages do. Phase 8 makes it the
spine of the whole tool, in the order you actually work:

  1 · Connect your data          the three-step strip at the top says where you are
  2 · Indexing health            the number that gates everything else
  3 · What's ranking right now   your pages ranked on real impressions/clicks/position,
                                 and the searches you sit 5th-20th for
  4 · What to do next            the ordered to-do list, unchanged from Phase 7

Every row in section 3 carries the same three one-click actions, each of which
fills in the agent that does the job and takes you there:

  🔗 Build backlinks → Backlinks, with this page preselected as the target
  ✍️ Write article   → Content, with topic, keyword and direction filled in
  🔧 Fix             → Analysis, with the Fix Plan filtered to this page's problem

An action that would be wasted is disabled with the reason printed next to it —
a backlink to a page Google can't reach earns nothing, and the dashboard says so
rather than letting you spend an afternoon on it.

Nothing here writes or publishes anything by itself. It reads, ranks, and hands
the work to the page that does it — with you pressing the button.
"""

import streamlit as st

import publishers
from agents import analysis
from core import config, keywords as kw
from publishers import PLATFORMS
from ui import components as c
from ui import data as d

REPORT = "ov_report"          # session state: the last analysis run for this site
BRIEFING = "ov_briefing"      # session state: the optional written summary


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Overview · {site.label}",
        "Where this site stands, which pages are actually earning something, and the "
        "button that acts on each one.",
    )

    coverage_df, coverage_source = d.coverage_frame(site)
    # The run happens before anything is drawn, so a fresh report is what the
    # sections below show — not the previous one with a rerun's delay.
    report = _report(ctx, coverage_df, coverage_source)

    _onboarding(ctx, report)
    st.divider()

    report = _run_controls(ctx, coverage_df, coverage_source, report)
    st.divider()

    _health(report, coverage_source)
    st.divider()

    _whats_ranking(ctx, report, coverage_source)
    st.divider()

    _todo(ctx, report)
    st.divider()

    _system_status(ctx)


# ── The three-step strip ───────────────────────────────────────────────────
def _onboarding(ctx, report) -> None:
    """
    The whole tool in three steps, always on screen. Which one you're on is
    read from the actual state — credentials on disk, figures in the report,
    platforms configured — never from a stored "tutorial progress" flag.
    """
    connected = ctx.creds
    ranking = bool(report.performance) or bool(report.pages)
    can_act = bool(publishers.ready_keys(ctx.site)) or config.is_set("OPENROUTER_API_KEY")

    if not connected:
        states = (c.NOW, c.LATER, c.LATER)
    elif not ranking:
        states = (c.DONE, c.NOW, c.LATER)
    else:
        states = (c.DONE, c.DONE, c.NOW if can_act else c.LATER)

    c.onboarding_strip([
        {
            "title": "Connect your data",
            "detail": ("Search Console and GA4, through one Google service-account file. "
                       "Until then every number here is sample data."
                       if not connected else
                       "Search Console is connected. Press **Refresh live data** in the "
                       "sidebar to re-check which pages Google has indexed."),
            "state": states[0],
            "button": "🔌 Connect Search Console + GA4" if not connected else "⚙️ Settings",
            "page": "Settings",
            "help": "Opens Settings, where you point the dashboard at your key file.",
        },
        {
            "title": "Review what's ranking",
            "detail": ("Your pages ranked by the impressions and clicks they actually "
                       "earn, plus the searches you sit 5th-20th for. It's the section "
                       "just below this one."
                       if ranking else
                       "Press **Run the analysis** below and this fills in with the "
                       "pages and searches you already earn something from."),
            "state": states[1],
        },
        {
            "title": "Generate backlinks + content",
            "detail": ("Every row below has the buttons: build backlinks to a page, or "
                       "write the article that strengthens it."
                       if can_act else
                       "Add an OpenRouter key and one platform you own, and the buttons "
                       "on each row below start working."),
            "state": states[2],
            "button": "🔗 Backlinks" if can_act else "⚙️ Add a key",
            "page": "Backlinks" if can_act else "Settings",
            "help": ("Auto-publish to platforms you own, plus human-approved guest "
                     "outreach." if can_act else "Opens Settings."),
        },
    ])


# ── 1 · Run the analysis ───────────────────────────────────────────────────
def _stored(ctx, coverage_source: str):
    """The stored run for exactly this site, date range and data source."""
    stored = st.session_state.get(REPORT) or {}
    if (stored.get("site") == ctx.site.key
            and stored.get("range") == f"{ctx.start} → {ctx.end}"
            and stored.get("coverage_source") == coverage_source):
        return stored["report"]
    return None


def _remember(ctx, coverage_source: str, report) -> None:
    st.session_state[REPORT] = {
        "site": ctx.site.key, "range": f"{ctx.start} → {ctx.end}",
        "coverage_source": coverage_source, "report": report,
    }


def _report(ctx, coverage_df, coverage_source: str):
    """
    The report on screen. A stored run wins. Otherwise: with credentials the
    page fetches its own figures once and keeps them, so landing here already
    shows what's ranking instead of an empty panel asking you to press a button;
    without credentials it builds from coverage alone and makes no network call
    at all.
    """
    stored = _stored(ctx, coverage_source)
    if stored is not None:
        return stored

    if not ctx.creds:
        return analysis.run(ctx.site, coverage_df, ctx.start, ctx.end, live=False,
                            coverage_source=coverage_source)

    with st.spinner("Reading Search Console for this date range…"):
        report = analysis.run(ctx.site, coverage_df, ctx.start, ctx.end, live=True,
                              coverage_source=coverage_source)
    _remember(ctx, coverage_source, report)
    return report


def _run_controls(ctx, coverage_df, coverage_source: str, report):
    c.section("1 · Your data",
              "Reads your coverage, your Search Console performance and the queries "
              "you already rank for, then sorts every page into what it needs. Nothing "
              "is written or published by this button.")

    cols = st.columns([2, 2, 3])
    with cols[0]:
        if st.button("🔄 Re-run the analysis", type="primary", key="ov_run",
                     width="stretch",
                     help="Fetches your Search Console figures again for the sidebar's "
                          "date range. Takes a few seconds. Without Google credentials "
                          "it still runs — on your coverage snapshot, and it says so."):
            bar = st.progress(0.0, text="Starting…")
            fresh = analysis.run(
                ctx.site, coverage_df, ctx.start, ctx.end, live=True,
                coverage_source=coverage_source,
                progress=lambda fraction, message: bar.progress(fraction, text=message),
            )
            bar.empty()
            _remember(ctx, coverage_source, fresh)
            st.session_state.pop(BRIEFING, None)
            report = fresh
    with cols[1]:
        c.show_badge(*_source_badge(report))
    with cols[2]:
        st.caption(report.detail or "Nothing to triage yet.")

    if report.generated_at:
        st.caption(f"Last run {report.generated_at.replace('T', ' ')} · "
                   f"{report.range or 'no date range'}")

    for note in report.notes:
        st.info(note, icon="ℹ️")

    _briefing(ctx, report)
    return report


def _source_badge(report) -> tuple:
    if report.source == "live":
        return "ok", "🟢 ranked on live Search Console figures"
    return "warn", "🟡 coverage only — no performance figures"


def _briefing(ctx, report) -> None:
    """
    The optional written summary. It's the one place the cheap ANALYSIS_MODEL is
    used, it only ever sees the measured numbers above, and the ordered list
    below stays the authority whether or not you run it.
    """
    with st.expander("📝 Read it back to me in plain English (optional)"):
        model = config.get("ANALYSIS_MODEL", "")
        if not (config.is_set("OPENROUTER_API_KEY") and model):
            st.caption("This writes a short status note over the numbers above using "
                       "your Analysis model — the cheap one. It needs an OpenRouter key "
                       "and an Analysis model in Settings. Everything else on this page "
                       "works without it.")
            c.nav_button("Open Settings", "Settings", key="ov_briefing_settings")
            return

        st.caption(f"Written by `{model}` from the measured numbers on this page only — "
                   "it is told not to invent a statistic, and the list below is the "
                   "authority either way.")
        if st.button("Write the status note", key="ov_briefing_btn"):
            with st.spinner("Reading the numbers…"):
                result = analysis.briefing(report, ctx.site)
            st.session_state[BRIEFING] = {"site": ctx.site.key, "result": result}

        stored = st.session_state.get(BRIEFING) or {}
        if stored.get("site") != ctx.site.key:
            return
        result = stored["result"]
        if result["ok"]:
            st.write(result["text"])
            st.caption(result["detail"])
        else:
            st.warning(result["detail"], icon="⚠️")


# ── 2 · Indexing health ────────────────────────────────────────────────────
def _health(report, coverage_source: str) -> None:
    c.section("2 · Indexing health",
              "Backlinks to a page Google hasn't indexed do nothing. This is the "
              "number that gates everything else on this page.")

    h = report.health
    if not h.get("total"):
        c.empty_state(
            "No coverage data for this site yet",
            "This screen ranks your pages by what each one needs. It needs a list of "
            "your pages and what Google thinks of them to do that.",
            steps=[
                "Add your Google service-account file on the **Settings** page.",
                "Check the sitemap URL for this site is right.",
                "Press **Refresh live data** in the sidebar.",
            ],
            icon="🏠",
        )
        return

    c.metric_row([
        ("Pages tracked", h["total"], "Every page in your sitemap that we have a "
                                      "verdict for."),
        ("Indexed", h["healthy"], "Google has accepted these. Only these can earn "
                                  "traffic, and only these are worth linking to."),
        ("Need attention", h["problems"], "Not indexed — broken, refused on quality, "
                                          "or never crawled."),
        ("Share indexed", f"{h['pct']}%", "The single number to move. Under about 70% "
                                          "means indexing, not links, is your problem."),
    ])
    st.progress(h["healthy"] / h["total"])
    c.data_source_note(coverage_source)
    c.jargon_note("Indexed", "Crawl budget", "Backlink")


# ── 3 · What's ranking right now ───────────────────────────────────────────
def _whats_ranking(ctx, report, coverage_source: str) -> None:
    c.section("3 · What's ranking right now",
              "Your pages, best first, and the searches you're closest on. Each row "
              "carries the three things you can do about it — no hunting for the right "
              "page afterwards.")

    _performance_totals(ctx, report)
    st.write("")
    _winners(ctx, report, coverage_source)
    st.write("")
    _striking(ctx, report)
    c.jargon_note("Impressions", "Clicks", "Average position", "Striking distance")


def _performance_totals(ctx, report) -> None:
    p = report.performance
    if not p:
        return
    c.metric_row([
        ("Clicks", f"{p['clicks']:,}", "Visits Google sent you in this date range."),
        ("Impressions", f"{p['impressions']:,}", "Times you appeared in results. "
                                                 "Appearing isn't being clicked."),
        ("Pages earning impressions", p["pages"], "How many of your pages Google showed "
                                                  "to anyone at all."),
        ("Average position", p["avg_position"] or "—", "1 is the top of page one. Past "
                                                       "about 10 is page two."),
        ("Searches you appear for", p["queries"], "Distinct queries with impressions. "
                                                  "Needs the keyword engine on."),
    ])


def _winners(ctx, report, coverage_source: str) -> None:
    """The ranked page list — the centrepiece, with three actions per row."""
    st.markdown("**🏆 Your pages, ranked**")

    if not report.pages:
        c.empty_state(
            "Nothing to rank yet",
            "This is the list of your pages ordered by the impressions and clicks they "
            "actually earn, with a button on each row to build links to it or write the "
            "article that strengthens it. It needs either coverage data or Search "
            "Console performance to fill in.",
            steps=[
                "Add your Google service-account file on the **Settings** page.",
                "Press **Refresh live data** in the sidebar to load your pages.",
                "Press **Re-run the analysis** above to rank them on real figures.",
            ],
            icon="🏆",
        )
        return

    if report.source == "live":
        st.caption(f"Ranked on real Search Console impressions for {report.range}. "
                   "The top of this list is where a link or a rewrite pays back fastest.")
    else:
        st.caption("⚠️ No Search Console performance figures for this range, so these are "
                   "your link-eligible pages in coverage order — **not** a performance "
                   "ranking. Connect Search Console and the same list re-sorts on real "
                   "impressions."
                   + (" The pages themselves come from the sample snapshot."
                      if coverage_source == "seed" else ""))

    for i, stat in enumerate(report.pages):
        _page_row(stat, i)


def _page_row(stat, index: int) -> None:
    """One page: what it is, what it earns, and the three buttons."""
    with st.container(border=True):
        info, badge = st.columns([6, 2])
        with info:
            st.markdown(f"**{stat.page or '/'}**")
            st.caption(stat.url)
            st.caption(stat.metrics_line)
            if stat.keyword:
                st.caption(f"🎯 Closest search: “{stat.keyword}” — position "
                           f"{stat.keyword_position} on "
                           f"{stat.keyword_impressions:,} impressions.")
        with badge:
            c.show_badge(stat.status_state, stat.status_label)
            st.caption(stat.coverage)

        link_col, write_col, fix_col = st.columns(3)
        with link_col:
            st.button("🔗 Build backlinks", key=f"ov_link_{index}", width="stretch",
                      type="primary" if stat.can_link else "secondary",
                      disabled=not stat.can_link,
                      on_click=_to_backlinks, args=(stat.url,),
                      help=stat.link_note)
        with write_col:
            st.button("✍️ Write article", key=f"ov_write_{index}", width="stretch",
                      disabled=not stat.topic,
                      on_click=_to_content_page, args=(stat,),
                      help=(stat.write_note if stat.topic else
                            "This URL isn't an article — it's an archive, feed or "
                            "category page. It needs clearing out, not writing."))
        with fix_col:
            st.button("🔧 Fix", key=f"ov_fix_{index}", width="stretch",
                      disabled=not stat.needs_fix,
                      on_click=_to_fix_plan, args=(stat.bucket, stat.url),
                      help=("Opens the Fix Plan filtered to this problem, with this page "
                            "called out." if stat.needs_fix else
                            "Nothing to fix — Google has no complaint about this URL."))

        if not stat.can_link:
            st.caption(f"⚠️ {stat.link_note}")


def _striking(ctx, report) -> None:
    """The searches you're one push away from page one on."""
    st.markdown("**🎯 Searches you're one push from page one on**")

    if not kw.enabled():
        st.caption("The keyword engine is switched off, so this list is empty. Turn it "
                   "on in **Settings → Content tools** — it reads the queries you "
                   "already rank for in Search Console and needs no extra key.")
        c.nav_button("Turn the keyword engine on", "Settings", key="ov_kw_settings")
        return

    striking = report.of_kind(analysis.STRENGTHEN)
    if not striking:
        if not ctx.creds:
            st.caption("Needs live Search Console query data — there's no sample for "
                       "this, because invented search figures would be worse than none.")
            return
        st.caption("No searches in the 5th-20th band with real impressions for this "
                   "range yet. That usually means indexing comes first — work the list "
                   "below, then come back.")
        return

    st.caption("Each of these is a search where a page of yours already ranks 5th-20th "
               "on real impressions. Strengthening the page that nearly ranks is the "
               "cheapest traffic you own.")

    for i, rec in enumerate(striking[:analysis.MAX_PER_KIND]):
        with st.container(border=True):
            info, action = st.columns([5, 2])
            with info:
                st.markdown(f"**🎯 {rec.keyword}**")
                st.caption(rec.why)
                st.caption(rec.url or "No page of yours ranks for this yet — it would "
                                      "be a new article.")
            with action:
                st.button("✍️ Write for this", key=f"ov_strike_write_{i}",
                          width="stretch", type="primary",
                          on_click=_to_content, args=(rec,),
                          help="Fills the Content page in with this search as the "
                               "primary keyword.")
                if rec.url:
                    st.button("🔗 Build backlinks", key=f"ov_strike_link_{i}",
                              width="stretch",
                              on_click=_to_backlinks, args=(rec.url,),
                              help="Preselects the page that already ranks as the "
                                   "backlink target.")


# ── 4 · What to do next ────────────────────────────────────────────────────
def _todo(ctx, report) -> None:
    c.section("4 · What to do next",
              "In order. Each step unlocks the one under it — fixing plumbing is worth "
              "more than any link you could build today. Open a step to act on the "
              "actual pages behind it.")

    if not report.steps:
        st.caption("Nothing to order yet — run the analysis above.")
        return

    if len(report.steps) == 1:
        st.success("Nothing urgent in the indexing data. Time to publish and build links.")

    for i, step in enumerate(report.steps, 1):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{i}. {step.icon} {step.title}**")
                st.caption(step.detail)
            with right:
                c.nav_button(step.cta, step.page, key=f"ov_step_{i}",
                             help=f"Opens the {step.page} page.")

            behind = report.for_step(step)
            picks = behind[:analysis.MAX_PER_KIND]
            if not picks:
                continue
            total = len(behind)
            label = (f"Show the {len(picks)} pages to start with"
                     if total <= analysis.MAX_PER_KIND
                     else f"Show the top {len(picks)} of {total} pages")
            with st.expander(label):
                for j, rec in enumerate(picks):
                    _recommendation(rec, key=f"ov_rec_{i}_{j}")


def _recommendation(rec, key: str) -> None:
    """One page, why it's here, and the button that acts on it."""
    with st.container(border=True):
        head, action = st.columns([4, 1])
        with head:
            st.markdown(f"**{rec.icon} {rec.page or rec.keyword or rec.url}**")
            st.caption(rec.url or "No page of yours ranks for this yet — a new article.")
            st.caption(rec.why)
            for line in rec.evidence:
                st.caption(f"· {line}")
            st.caption(rec.metrics_line)
        with action:
            st.button(rec.cta, key=key, type="primary", width="stretch",
                      on_click=_hand_off, args=(rec,),
                      help=f"Takes you to the {rec.target_page} page with this "
                           "page already filled in.")
            if rec.kind == analysis.STRENGTHEN and rec.url:
                st.button("🔗 Links", key=f"{key}_link", width="stretch",
                          on_click=_to_backlinks, args=(rec.url,),
                          help="Preselects this page on the Backlinks page instead.")


# ── Hand-offs — the same session-state keys the Opportunities cards use ────
def _hand_off(rec) -> None:
    if rec.kind in (analysis.FIX, analysis.PRUNE):
        _to_fix_plan(rec.bucket, rec.url)
    elif rec.kind in (analysis.REWRITE, analysis.STRENGTHEN):
        _to_content(rec)
    else:
        _to_backlinks(rec.url)


def _to_fix_plan(bucket: str, url: str) -> None:
    """Open the Fix Plan filtered to this bucket, with the page called out."""
    st.session_state.update({"analysis_bucket": bucket, "analysis_focus": url,
                             "nav": "Analysis"})


def _to_content(rec) -> None:
    """Fill the writer's boxes and jump there — the Opportunities hand-off keys."""
    st.session_state.update({
        "content_topic": rec.topic or rec.keyword,
        "content_keyword": rec.keyword,
        "content_notes": rec.notes,
        "content_source": f"the Overview — {rec.kind.lower()}",
        "nav": "Content",
    })


def _to_content_page(stat) -> None:
    """
    The winners table's writer hand-off. Same keys as every other hand-off, so
    the Content page doesn't care which screen sent the work over.
    """
    st.session_state.update({
        "content_topic": stat.topic,
        "content_keyword": stat.keyword,
        "content_notes": stat.write_note,
        "content_source": f"the Overview — {stat.page or stat.url}",
        "nav": "Content",
    })


def _to_backlinks(url: str) -> None:
    """Preselect this page as the Backlinks target and jump there."""
    st.session_state.update({"bl_focus_url": url, "bl_focus_from": "the Overview",
                             "nav": "Backlinks"})


# ── 5 · System status ──────────────────────────────────────────────────────
def _system_status(ctx) -> None:
    c.section("5 · System status", "What's connected, and what's still waiting on a key.")
    c.status_rows(_system_rows(ctx))

    if not ctx.creds:
        st.write("")
        c.empty_state(
            "Running on sample data",
            "Everything on this page comes from a saved snapshot rather than from "
            "Google, so you can find your way around before connecting anything. "
            "Connect the Google APIs and the same screens fill in with what your sites "
            "are doing today.",
            steps=[
                "Open **Settings → Google APIs**.",
                "Point it at your service-account JSON file.",
                "Run **Test connections** — it checks each API separately and tells "
                "you exactly which step failed.",
                "Press **Refresh live data** in the sidebar, then **Re-run the "
                "analysis** here.",
            ],
            icon="🟡",
        )
        c.nav_button("Open Settings", "Settings", key="ov_settings", type="primary")


def _system_rows(ctx) -> list:
    """One line per moving part, with a plain-language explanation."""
    rows = []
    email = config.service_account_email()

    if ctx.creds:
        rows.append({"name": "Search Console", "state": "ok", "label": "connected",
                     "detail": f"Service account found{f' ({email})' if email else ''}. "
                               "Use Settings → Test connections to confirm it can "
                               "actually read this property."})
    else:
        rows.append({"name": "Search Console", "state": "warn", "label": "sample mode",
                     "detail": "No service-account file yet, so indexing figures come "
                               "from the sample snapshot and performance stays empty."})

    # GA4 is its own row on purpose: one file serves both APIs, but a site with
    # no GA4 property ID is not connected to GA4, whatever the file says.
    if config.ga4_ready(ctx.site):
        rows.append({"name": "Google Analytics (GA4)", "state": "ok", "label": "connected",
                     "detail": f"Property {ctx.site.ga4_property_id}. Visitor numbers "
                               "are on Analysis → Audience."})
    elif ctx.creds:
        rows.append({"name": "Google Analytics (GA4)", "state": "warn",
                     "label": "no property ID",
                     "detail": f"The key file is there, but {ctx.site.label} has no GA4 "
                               "property ID, so the Audience view stays empty. Add it in "
                               "Settings → Sites."})
    else:
        rows.append({"name": "Google Analytics (GA4)", "state": "warn", "label": "not set",
                     "detail": "Needs the same service-account file, plus a GA4 property "
                               "ID for this site."})

    if config.is_set("OPENROUTER_API_KEY"):
        rows.append({"name": "AI models", "state": "ok", "label": "ready",
                     "detail": "Analysis: {} · Backlinks: {} · Content: {}".format(
                         config.get("ANALYSIS_MODEL", "not set"),
                         config.get("BACKLINK_MODEL", "not set"),
                         config.get("CONTENT_MODEL", "not set"))})
    else:
        rows.append({"name": "AI models", "state": "warn", "label": "not set",
                     "detail": "Add an OpenRouter key in Settings to let the agents "
                               "draft anything."})

    wp = config.wp_credentials(ctx.site)
    if wp["username"] and wp["app_password"]:
        rows.append({"name": "WordPress drafts", "state": "ok", "label": "ready",
                     "detail": f"Drafts will be created on {wp['url']} as {wp['username']}. "
                               "Always as a draft — never published live."})
    else:
        rows.append({"name": "WordPress drafts", "state": "warn", "label": "not set",
                     "detail": f"Add a WordPress username + application password for "
                               f"{ctx.site.label} in Settings to publish drafts."})

    # One source of truth: the publisher registry, which is owned platforms only.
    owned = [PLATFORMS[k].label for k in publishers.ready_keys(ctx.site)]
    rows.append({
        "name": "Owned platforms",
        "state": "ok" if owned else "idle",
        "label": ", ".join(owned) if owned else "not set",
        "detail": "Where the backlink agent may auto-publish. Only platforms you own — "
                  "guest posts always wait for your approval.",
    })

    rows.append({
        "name": "Keyword engine", "state": "ok" if kw.enabled() else "idle",
        "label": "on" if kw.enabled() else "off",
        "detail": kw.status(),
    })
    return rows
