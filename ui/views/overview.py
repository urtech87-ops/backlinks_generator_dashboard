"""
Overview — the conductor (Phase 7).

This is the page you start on, and the one that decides what the other pages
do. It runs the Analysis agent over your coverage and your Search Console
figures, shows the indexing health that gates everything else, and turns that
into an ordered to-do list where every line opens onto the actual pages it's
talking about — each with the button that carries the job out:

  🔴 fix        → Analysis, with the Fix Plan already filtered to that bucket
  🟠 rewrite    → Content, with the topic and direction filled in
  🟢 link       → Backlinks, with the target page preselected
  🎯 strengthen → Content, with the striking-distance keyword filled in

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
        "The state of the site in one screen, the next thing worth doing, and the "
        "button that does it.",
    )

    coverage_df, coverage_source = d.coverage_frame(site)
    # The run happens before anything is drawn, so a fresh report is what the
    # sections below show — not the previous one with a rerun's delay.
    report = _report(ctx, coverage_df, coverage_source)
    report = _run_controls(ctx, coverage_df, coverage_source, report)
    st.divider()

    _health(report, coverage_source)
    st.divider()

    _performance(ctx, report)
    st.divider()

    _todo(ctx, report)
    st.divider()

    _system_status(ctx)


# ── 1 · Run the analysis ───────────────────────────────────────────────────
def _report(ctx, coverage_df, coverage_source: str):
    """
    The report on screen. A stored run wins; otherwise the page builds one from
    coverage alone, with no network calls, so it always has something honest to
    show before you press anything.
    """
    stored = st.session_state.get(REPORT) or {}
    if (stored.get("site") == ctx.site.key
            and stored.get("range") == f"{ctx.start} → {ctx.end}"
            and stored.get("coverage_source") == coverage_source):
        return stored["report"]
    return analysis.run(ctx.site, coverage_df, ctx.start, ctx.end, live=False,
                        coverage_source=coverage_source)


def _run_controls(ctx, coverage_df, coverage_source: str, report):
    c.section("1 · Run the analysis",
              "Reads your coverage, your Search Console performance and the queries "
              "you already rank for, then sorts every page into what it actually "
              "needs. Nothing is written or published by this button.")

    cols = st.columns([2, 2, 3])
    with cols[0]:
        if st.button("▶️ Run the analysis", type="primary", key="ov_run",
                     help="Takes a few seconds. Without Google credentials it still "
                          "runs — on your coverage snapshot, and it says so."):
            bar = st.progress(0.0, text="Starting…")
            fresh = analysis.run(
                ctx.site, coverage_df, ctx.start, ctx.end, live=True,
                coverage_source=coverage_source,
                progress=lambda fraction, message: bar.progress(fraction, text=message),
            )
            bar.empty()
            st.session_state[REPORT] = {
                "site": ctx.site.key, "range": f"{ctx.start} → {ctx.end}",
                "coverage_source": coverage_source, "report": fresh,
            }
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
        return "ok", "ranked on live Search Console figures"
    return "warn", "coverage only — no performance figures"


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
              "number that gates everything else.")

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
        ("Pages tracked", h["total"]),
        ("Indexed", h["healthy"], "Eligible for backlinks and outreach."),
        ("Need attention", h["problems"], "Not indexed for one of the reasons below."),
        ("Share indexed", f"{h['pct']}%"),
    ])
    st.progress(h["healthy"] / h["total"])
    c.data_source_note(coverage_source)


# ── 3 · Performance ────────────────────────────────────────────────────────
def _performance(ctx, report) -> None:
    c.section("3 · What the site earned in this range",
              "Straight from Search Console for the sidebar's date range. Live-only — "
              "there's no seed for performance, because invented traffic figures would "
              "be worse than none.")

    p = report.performance
    if not p:
        if not ctx.creds:
            c.empty_state(
                "No performance figures yet",
                "Clicks, impressions and average position need the live Search Console "
                "API. Until it's connected, the ordering below is by what each page "
                "needs rather than by what it earns — which is still the right order to "
                "work in.",
                steps=[
                    "Add the Google service-account file on the **Settings** page.",
                    "Grant its email access in Search Console → Settings → Users.",
                    "Run **Test connections**, then press **Run the analysis** above.",
                ],
                icon="📈",
            )
        else:
            st.caption("Credentials are in place, but no performance rows came back for "
                       "this range — press **Run the analysis** above, or check "
                       "**Settings → Test connections**.")
        return

    c.metric_row([
        ("Clicks", f"{p['clicks']:,}"),
        ("Impressions", f"{p['impressions']:,}"),
        ("Pages with impressions", p["pages"]),
        ("Average position", p["avg_position"] or "—"),
        ("Queries", p["queries"], "Distinct searches you appeared for. Needs the "
                                  "keyword engine on."),
    ])
    c.nav_button("See the full performance report", "Analysis", key="ov_to_perf",
                 help="Top pages and top queries, on the Analysis page.")


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
            st.button(rec.cta, key=key, type="primary",
                      on_click=_hand_off, args=(rec,),
                      help=f"Takes you to the {rec.target_page} page with this "
                           "page already filled in.")
            if rec.kind == analysis.STRENGTHEN and rec.url:
                st.button("🔗 Links", key=f"{key}_link",
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
            "Running on seed data",
            "Everything on this page is your real 16 August Search Console snapshot, "
            "so the Fix Plan is useful today. Connect the Google APIs to see whether "
            "your fixes have landed since.",
            steps=[
                "Open **Settings → Google APIs**.",
                "Point it at your service-account JSON file.",
                "Run **Test connections** — it checks each API separately and tells "
                "you exactly which step failed.",
            ],
            icon="🟡",
        )
        c.nav_button("Open Settings", "Settings", key="ov_settings")


def _system_rows(ctx) -> list:
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
