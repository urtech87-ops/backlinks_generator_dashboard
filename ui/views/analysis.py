"""
Analysis — the four views the Analysis agent feeds.

  Fix Plan     every problem page sorted into what actually needs doing
  Indexing     how much of the site Google has accepted
  Performance  clicks / impressions / position (live Search Console only)
  Audience     who actually turns up (live GA4 only)
"""

import pandas as pd
import streamlit as st

from agents import analysis as ag
from core import config, ga4, gsc, seed
from core.classifier import (
    BUCKET_ORDER, PLUMBING, CONTENT, CRAWL_BUDGET, HEALTHY, OTHER,
)
from ui import components as c
from ui import data as d

BUCKET_COLOR = {
    PLUMBING: "#e5484d",       # red — broken, fix first
    CONTENT: "#f76b15",        # orange — rewrite
    CRAWL_BUDGET: "#f5d90a",   # yellow — links/internal
    OTHER: "#8b8d98",          # grey — usually leave alone
    HEALTHY: "#30a46c",        # green — done, link-eligible
}
EVERYTHING = "Everything that needs doing"

BUCKET_ONELINER = {
    PLUMBING: "Broken URL — Google can't index it. Fix the redirect/404. No backlink helps.",
    CONTENT: "Crawled and rejected on quality. Rewrite required.",
    CRAWL_BUDGET: "Not crawled yet. Internal links + sitemap. The only place backlinks help.",
    OTHER: "Intentional or informational. Usually no action.",
    HEALTHY: "Indexed. Eligible for the backlink / outreach stage.",
}


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Analysis · {site.label}",
        "What Google thinks of your pages, and what to do about it — worst first.",
    )

    df, source = d.coverage_frame(site)
    c.data_source_note(source)
    st.caption("**Fix Plan** = what's broken and how to mend it · **Indexing** = how much "
               "of the site Google has accepted · **Performance** = what you earn in "
               "search · **Audience** = who actually turns up.")
    c.jargon_note("Indexed", "Crawl budget", "Impressions", "Average position")

    tab_fix, tab_index, tab_perf, tab_aud = st.tabs(
        ["🔧 Fix Plan", "📄 Indexing", "📈 Performance", "👥 Audience"]
    )

    with tab_fix:
        _fix_plan(site, df)
    with tab_index:
        _indexing(df, source)
    with tab_perf:
        _performance(ctx, df)
    with tab_aud:
        _audience(ctx)


# ── Fix Plan ───────────────────────────────────────────────────────────────
def _fix_plan(site: config.Site, df: pd.DataFrame) -> None:
    if df.empty:
        c.empty_state(
            "No coverage data for this site yet",
            "The Fix Plan lists every page Google has refused to index and sorts it "
            "into what actually needs doing — broken URLs first, thin content next, "
            "un-crawled pages last.",
            steps=[
                "Add your Google service-account file on the **Settings** page.",
                "Check the sitemap URL for this site is right.",
                "Press **Refresh live data** in the sidebar.",
            ],
            icon="🔧",
        )
        return

    summary = d.health_summary(df)
    c.metric_row([(bucket, summary["counts"].get(bucket, 0), BUCKET_ONELINER[bucket])
                  for bucket in BUCKET_ORDER])
    st.caption(f"{summary['problems']} pages need attention · {summary['healthy']} healthy · "
               "work top-to-bottom: red → orange → yellow.")

    # The Overview page hands a bucket (and sometimes one page) over to here.
    focus = st.session_state.pop("analysis_focus", "")
    st.write("")
    choice = st.selectbox(
        "Show", options=[EVERYTHING] + BUCKET_ORDER, key="analysis_bucket",
        help="Filter the plan to one kind of problem. The Overview page sets this "
             "when you open a step from there.",
    )
    if choice != EVERYTHING:
        st.caption(BUCKET_ONELINER[choice])

    if focus:
        row = df[df["URL"] == focus]
        if row.empty:
            st.info(f"`{focus}` was sent over from the Overview, but it isn't in this "
                    "site's coverage data any more. Press **Refresh live data** in the "
                    "sidebar.")
        else:
            row = row.iloc[0]
            with st.container(border=True):
                st.markdown(f"**Sent over from the Overview — {row['Page']}**")
                st.caption(row["URL"])
                st.caption(f"Search Console says: **{row['Coverage']}**"
                           + (f" · flags: {row['Flags']}" if row["Flags"] else ""))
                st.write(row["Action"])
                st.caption("This one is fixed on your site — a redirect, a template link "
                           "or a deletion. The dashboard can't do it for you, which is "
                           "why there's no button here.")

    st.divider()

    shown = BUCKET_ORDER if choice == EVERYTHING else [choice]
    for bucket in shown:
        sub = df[df["Bucket"] == bucket]
        if sub.empty:
            continue
        dot = BUCKET_COLOR[bucket]
        st.markdown(
            f"<h4><span style='color:{dot}'>●</span> {bucket} "
            f"<span style='font-size:0.7em;color:#8b8d98'>({len(sub)})</span></h4>",
            unsafe_allow_html=True,
        )
        st.caption(BUCKET_ONELINER[bucket])
        st.dataframe(
            sub.sort_values("Page")[["Page", "Coverage", "Flags", "Action"]].rename(
                columns={"Coverage": "What Google says",
                         "Flags": "Warning signs",
                         "Action": "What to do about it"}),
            width="stretch", hide_index=True,
            column_config={
                "Page": st.column_config.TextColumn(
                    "Page", help="The path on your site, with the domain trimmed off."),
                "What Google says": st.column_config.TextColumn(
                    "What Google says",
                    help="The exact coverage state Search Console reports for this URL."),
            },
        )
        _bucket_actions(bucket)

    dups = seed.SUSPECTED_DUPLICATES if site.key == "toolsvenue" else []
    if dups:
        st.divider()
        c.section("⚠️ Suspected duplicate tool URLs",
                  "Same tool at two URLs — a clean slug and an old keyword-stuffed one. "
                  "They cannibalise each other. Keep one, 301 the other.")
        st.table(pd.DataFrame(dups, columns=["Keep (clean)", "301-redirect away (stuffed)"]))

    st.divider()
    st.download_button(
        "⬇️ Export full fix plan (CSV)",
        df.drop(columns=["Page"]).to_csv(index=False).encode(),
        file_name=f"{site.key}_fix_plan.csv",
        mime="text/csv",
        help="Every page with its coverage state, bucket and recommended action.",
    )


def _bucket_actions(bucket: str) -> None:
    """
    The two buckets that are acted on elsewhere in the dashboard get the button
    that does it, so the plan is never a dead end.
    """
    if bucket == CONTENT:
        cols = st.columns([2, 4])
        with cols[0]:
            c.nav_button("✍️ Rewrite these", "Content", key=f"an_act_{bucket}",
                         help="Opens the Content page. Pick the page to rewrite from "
                              "the Overview if you want it filled in for you.")
        cols[1].caption("A rewrite is the only thing that changes a quality verdict — "
                        "no link overrides it.")
    elif bucket == CRAWL_BUDGET:
        cols = st.columns([2, 4])
        with cols[0]:
            c.nav_button("🔗 Get these linked", "Backlinks", key=f"an_act_{bucket}",
                         help="Opens the Backlinks page, where these pages are the "
                              "rescue targets.")
        cols[1].caption("Internal links first, then one or two genuine backlinks. This "
                        "is the one bucket where link-building changes indexing.")


# ── Indexing ───────────────────────────────────────────────────────────────
def _indexing(df: pd.DataFrame, source: str) -> None:
    if df.empty:
        st.info("No coverage data yet — see the Fix Plan tab for how to switch it on.")
        return

    summary = d.health_summary(df)
    c.metric_row([
        ("Indexed (healthy)", f"{summary['healthy']} / {summary['total']}",
         "Pages Google has accepted. Only these are worth linking to."),
        ("Needs attention", summary["problems"], "Everything not yet indexed."),
        ("Share indexed", f"{summary['pct']}%"),
    ])
    st.progress(summary["healthy"] / summary["total"] if summary["total"] else 0)

    c.section("Coverage breakdown",
              "The exact verdicts Search Console reports, counted up. A tall bar on "
              "anything other than “Submitted and indexed” is where your traffic is "
              "going missing.")
    cov = (df["Coverage"].value_counts().rename_axis("Coverage state")
           .reset_index(name="Pages"))
    st.bar_chart(cov.set_index("Coverage state"))

    c.section("Every page and what Google decided about it",
              "Sorted by problem type, so pages with the same cause sit together — they "
              "usually share one fix.")
    st.dataframe(
        df[["Page", "Coverage", "Bucket", "Flags"]].sort_values(["Bucket", "Page"]).rename(
            columns={"Coverage": "What Google says", "Bucket": "Problem type",
                     "Flags": "Warning signs"}),
        width="stretch", hide_index=True,
    )
    if source == "seed":
        st.info("This is the sample 16 Aug snapshot, not today's figures. Connect Search "
                "Console and press **Refresh live data** in the sidebar to see whether "
                "your fixes have flipped pages to indexed.", icon="🟡")


# ── Performance (GSC Search Analytics) ─────────────────────────────────────
def _performance(ctx, coverage_df: pd.DataFrame) -> None:
    if not ctx.creds:
        c.empty_state(
            "Performance needs the live Search Console API",
            "This view shows which pages and queries actually earn clicks and "
            "impressions — the numbers that pick your winner pages for the backlink "
            "agent. There's no seed for it, because made-up performance data would be "
            "worse than none.",
            steps=[
                "Add the Google service-account file on the **Settings** page.",
                "Grant its email access in Search Console → Settings → Users.",
                "Run **Test connections** on the Settings page.",
            ],
            icon="📈",
        )
        return

    pages = gsc.search_analytics(ctx.site.gsc_property, ctx.start, ctx.end, ["page"])
    queries = gsc.search_analytics(ctx.site.gsc_property, ctx.start, ctx.end, ["query"])

    if not pages and not queries:
        st.warning("No performance rows came back for this date range. Either the site "
                   "genuinely has no impressions yet, or the service account isn't on "
                   "this Search Console property — run **Test connections** in Settings.")
        return

    if pages:
        pdf = pd.DataFrame(pages)
        c.metric_row([
            ("Total clicks", int(pdf["clicks"].sum()),
             "Visits Google sent you in this date range."),
            ("Total impressions", int(pdf["impressions"].sum()),
             "Times one of your pages appeared in results — appearing isn't being clicked."),
            ("Pages earning impressions", len(pdf),
             "How many of your pages Google showed to anyone at all."),
        ])
        c.section("Which pages earn the most",
                  "Sorted by impressions. Lots of impressions at a weak average position "
                  "is the best-value row on this table — the demand is already there, "
                  "the page just isn't high enough yet. Every row also gets a verdict: "
                  "the one thing that page needs next.")
        st.dataframe(
            _perf_frame(_with_verdicts(coverage_df, pdf)), width="stretch", hide_index=True,
            column_config={
                "Verdict": st.column_config.TextColumn(
                    "Verdict", help="What this page needs next — see the legend below."),
                "Why": st.column_config.TextColumn(
                    "Why", help="The one-line reason behind the verdict."),
            },
        )
        c.legend("❓ What each verdict means", ag.VERDICT_LEGEND)
        cols = st.columns([2, 4])
        with cols[0]:
            c.nav_button("🏠 Act on these", "Overview", key="an_perf_overview",
                         type="primary",
                         help="The Overview shows this same ranking with a Build "
                              "backlinks / Write article / Fix button on every row.")
        cols[1].caption("This tab is the raw report. The buttons that act on it live on "
                        "the Overview, so one page owns the actions.")
    if queries:
        c.section("Which searches you appear for",
                  "What people actually typed to see you. Real first-party data — no "
                  "estimated volumes anywhere in this dashboard.")
        st.dataframe(_perf_frame(pd.DataFrame(queries)), width="stretch", hide_index=True)
        cols = st.columns([2, 4])
        with cols[0]:
            c.nav_button("🔑 Find the striking-distance ones", "Opportunities",
                         key="an_perf_kw",
                         help="The Keywords tab flags the searches you sit 5th-20th for "
                              "and hands them to the writer.")
        cols[1].caption("A search you rank 5th-20th for, on real impressions, is the "
                        "cheapest traffic you own.")


def _with_verdicts(coverage_df: pd.DataFrame, pdf: pd.DataFrame) -> pd.DataFrame:
    """
    Attach "what this page needs next" to each performance row, using the
    same page_verdict() the Overview's winners list uses — one place decides,
    two screens display it.
    """
    indexed_urls = set()
    if coverage_df is not None and not coverage_df.empty:
        indexed_urls = set(coverage_df.loc[coverage_df["Bucket"] == HEALTHY, "URL"]
                           .str.rstrip("/"))

    def _row_verdict(row):
        v = ag.page_verdict(
            indexed=str(row["page"]).rstrip("/") in indexed_urls,
            position=float(row.get("position", 0) or 0),
            impressions=int(row.get("impressions", 0) or 0),
            ctr=float(row.get("ctr", 0) or 0),
            has_metrics=True,   # this row exists because GSC measured it
        )
        return pd.Series({"Verdict": f'{v["icon"]} {v["label"]}', "Why": v["reason"]})

    out = pdf.copy()
    out[["Verdict", "Why"]] = out.apply(_row_verdict, axis=1)
    return out


def _perf_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """The Search Console column names, said in plain language."""
    return frame.sort_values("impressions", ascending=False).rename(columns={
        "page": "Page", "query": "Search", "clicks": "Clicks",
        "impressions": "Impressions", "ctr": "Click rate %",
        "position": "Average position",
    })


# ── Audience (GA4) ─────────────────────────────────────────────────────────
def _audience(ctx) -> None:
    if not config.ga4_ready(ctx.site):
        c.empty_state(
            "Audience needs GA4",
            "This view shows how many real people arrive, where from, and what they "
            "land on. Live-only — there's no seed.",
            steps=[
                "Add the Google service-account file on the **Settings** page.",
                f"Set the GA4 property ID for {ctx.site.label} on the **Settings** page.",
                "In GA4 → Admin → Property access management, give the service-account "
                "email Viewer access.",
            ],
            icon="👥",
        )
        return

    s = ga4.summary(ctx.site.ga4_property_id, ctx.start, ctx.end)
    if not s:
        st.warning("No GA4 rows came back. Check the property ID and that the "
                   "service-account email has Viewer access — **Test connections** on "
                   "the Settings page will tell you which.")
        return

    c.metric_row([
        ("People", f"{s['activeUsers']:,}", "Distinct visitors in this date range."),
        ("Visits", f"{s['sessions']:,}", "One person can visit more than once."),
        ("Pages viewed", f"{s['pageViews']:,}", "Total page views across all visits."),
        ("Time per visit", f"{s['avgDuration']}s", "Average length of a visit. Seconds."),
        ("Engaged visits", f"{s['engagementRate']}%",
         "Share of visits where someone stayed, scrolled or clicked rather than "
         "bouncing straight off."),
    ])

    left, right = st.columns(2)
    with left:
        c.section("Where the visits come from",
                  "“Organic search” is the one this dashboard is trying to grow.")
        ch = ga4.channels(ctx.site.ga4_property_id, ctx.start, ctx.end)
        if ch:
            st.dataframe(pd.DataFrame(ch), width="stretch", hide_index=True)
        else:
            st.caption("No channel rows for this range yet.")
    with right:
        c.section("Which countries they're in",
                  "Useful for deciding what a piece should assume about its reader.")
        co = ga4.countries(ctx.site.ga4_property_id, ctx.start, ctx.end)
        if co:
            st.dataframe(pd.DataFrame(co), width="stretch", hide_index=True)
        else:
            st.caption("No country rows for this range yet.")

    c.section("The pages people arrive on",
              "The first page a visitor sees. These are the ones worth keeping indexed "
              "and worth linking to.")
    tp = ga4.top_pages(ctx.site.ga4_property_id, ctx.start, ctx.end)
    if tp:
        st.dataframe(pd.DataFrame(tp), width="stretch", hide_index=True)
    else:
        st.caption("No landing-page rows for this range yet.")
