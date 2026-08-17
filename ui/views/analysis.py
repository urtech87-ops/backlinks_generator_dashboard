"""
Analysis — the four views the Analysis agent feeds.

  Fix Plan     every problem page sorted into what actually needs doing
  Indexing     how much of the site Google has accepted
  Performance  clicks / impressions / position (live Search Console only)
  Audience     who actually turns up (live GA4 only)
"""

import pandas as pd
import streamlit as st

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

    tab_fix, tab_index, tab_perf, tab_aud = st.tabs(
        ["🔧 Fix Plan", "📄 Indexing", "📈 Performance", "👥 Audience"]
    )

    with tab_fix:
        _fix_plan(site, df)
    with tab_index:
        _indexing(df, source)
    with tab_perf:
        _performance(ctx)
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
    cols = st.columns(5)
    for col, bucket in zip(cols, BUCKET_ORDER):
        col.metric(bucket, summary["counts"].get(bucket, 0))
    st.caption(f"{summary['problems']} pages need attention · {summary['healthy']} healthy · "
               "work top-to-bottom: red → orange → yellow.")

    st.divider()

    for bucket in BUCKET_ORDER:
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
            sub.sort_values("Page")[["Page", "Coverage", "Flags", "Action"]],
            width="stretch", hide_index=True,
        )

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

    c.section("Coverage breakdown", "The raw states Search Console reports, counted up.")
    cov = (df["Coverage"].value_counts().rename_axis("Coverage state")
           .reset_index(name="Pages"))
    st.bar_chart(cov.set_index("Coverage state"))

    c.section("Every page + its coverage state")
    st.dataframe(
        df[["Page", "Coverage", "Bucket", "Flags"]].sort_values(["Bucket", "Page"]),
        width="stretch", hide_index=True,
    )
    if source == "seed":
        st.info("This is your 16 Aug snapshot. Connect Search Console and press "
                "**Refresh live data** to see whether your fixes have flipped pages "
                "to indexed.")


# ── Performance (GSC Search Analytics) ─────────────────────────────────────
def _performance(ctx) -> None:
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
            ("Total clicks", int(pdf["clicks"].sum())),
            ("Total impressions", int(pdf["impressions"].sum())),
            ("Pages with impressions", len(pdf)),
        ])
        c.section("Top pages", "Sorted by impressions — high impressions with a weak "
                               "position is where a small push pays off most.")
        st.dataframe(pdf.sort_values("impressions", ascending=False),
                     width="stretch", hide_index=True)
    if queries:
        c.section("Top queries", "What people actually typed. Real keyword data, "
                                 "no guessing.")
        st.dataframe(pd.DataFrame(queries).sort_values("impressions", ascending=False),
                     width="stretch", hide_index=True)


# ── Audience (GA4) ─────────────────────────────────────────────────────────
def _audience(ctx) -> None:
    if not ctx.creds or not ctx.site.ga4_property_id:
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
        ("Active users", f"{s['activeUsers']:,}"),
        ("Sessions", f"{s['sessions']:,}"),
        ("Page views", f"{s['pageViews']:,}"),
        ("Avg session (s)", s["avgDuration"]),
        ("Engagement", f"{s['engagementRate']}%"),
    ])

    left, right = st.columns(2)
    with left:
        c.section("Traffic by channel", "Where the visits come from.")
        ch = ga4.channels(ctx.site.ga4_property_id, ctx.start, ctx.end)
        if ch:
            st.dataframe(pd.DataFrame(ch), width="stretch", hide_index=True)
    with right:
        c.section("Top countries")
        co = ga4.countries(ctx.site.ga4_property_id, ctx.start, ctx.end)
        if co:
            st.dataframe(pd.DataFrame(co), width="stretch", hide_index=True)

    c.section("Top landing pages", "The first page people see — worth keeping healthy.")
    tp = ga4.top_pages(ctx.site.ga4_property_id, ctx.start, ctx.end)
    if tp:
        st.dataframe(pd.DataFrame(tp), width="stretch", hide_index=True)
