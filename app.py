"""
SEO Command Center
==================
Run:  streamlit run app.py

Opens on the Fix Plan — every not-indexed page sorted into what actually needs
doing, in priority order. Then live Indexing, Performance (GSC) and Audience (GA4).

Works day one on the seed of your real Search Console state. Once you connect the
GSC + GA4 APIs (see README), hit "Refresh live data" and it uses live numbers.
"""

import datetime as dt

import pandas as pd
import streamlit as st

from core import config, gsc, ga4, seed
from core.classifier import (
    recommend, BUCKET_ORDER, BUCKET_PRIORITY,
    PLUMBING, CONTENT, CRAWL_BUDGET, HEALTHY, OTHER,
)

st.set_page_config(page_title="SEO Command Center", page_icon="🧭", layout="wide")

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


# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("🧭 SEO Command Center")

site_key = st.sidebar.selectbox(
    "Site", [s.key for s in config.SITES],
    format_func=lambda k: config.SITES_BY_KEY[k].label,
)
site = config.SITES_BY_KEY[site_key]

today = dt.date.today()
default_start = today - dt.timedelta(days=28)
date_range = st.sidebar.date_input("Date range (GSC + GA4)", (default_start, today))
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
else:
    start_d, end_d = default_start, today
start, end = start_d.isoformat(), end_d.isoformat()

live_on = config.credentials_available()
st.sidebar.markdown(
    f"**Live data:** {'🟢 credentials found' if live_on else '🟡 seed mode (no creds yet)'}"
)

refresh = st.sidebar.button("🔄 Refresh live data", disabled=not live_on,
                            help="Runs the URL Inspection API over your sitemap. Cached 6h.")
st.sidebar.caption("Seed = your real GSC state from 16 Aug. Live = current, once APIs are connected.")


# ── Data loading (cached) ──────────────────────────────────────────────────
@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_coverage_live(site_key: str, gsc_property: str, sitemap_url: str, homepage: str):
    urls = gsc.discover_urls(sitemap_url)
    if not urls:
        return []
    bar = st.progress(0.0, text="Inspecting URLs via Search Console…")
    def prog(done, total):
        bar.progress(done / total, text=f"Inspecting URLs… {done}/{total}")
    rows = gsc.inspect_urls(gsc_property, urls, progress=prog)
    bar.empty()
    return rows


def get_coverage_rows():
    """Live rows if available + refreshed, else the seed."""
    if live_on and refresh:
        rows = load_coverage_live(site.key, site.gsc_property, site.sitemap_url, site.homepage)
        if rows:
            st.session_state[f"cov_{site.key}"] = rows
    cached = st.session_state.get(f"cov_{site.key}")
    if cached:
        return cached, "live"
    return seed.seed_rows(site.key, site.homepage), "seed"


coverage_rows, source = get_coverage_rows()

# Classify everything up front.
verdicts = [recommend(url, cov) for url, cov in coverage_rows]
df = pd.DataFrame([{
    "URL": v.url, "Coverage": v.coverage, "Bucket": v.bucket,
    "Priority": v.priority, "Action": v.action,
    "Flags": ", ".join(v.flags), "_p": v.url.replace(site.homepage.rstrip("/"), "") or "/",
} for v in verdicts])


# ── Header ─────────────────────────────────────────────────────────────────
st.title(site.label)
badge = "🟢 live" if source == "live" else "🟡 seed (your 16 Aug snapshot)"
st.caption(f"Data source for indexing: {badge}  ·  GSC property `{site.gsc_property}`")

tab_fix, tab_index, tab_perf, tab_aud = st.tabs(
    ["🔧 Fix Plan", "📄 Indexing", "📈 Performance", "👥 Audience"]
)


# ── TAB 1 — FIX PLAN ───────────────────────────────────────────────────────
with tab_fix:
    if df.empty:
        st.info("No coverage data yet for this site. Connect the GSC API and hit "
                "**Refresh live data**, or add a seed in `seo/seed.py`.")
    else:
        counts = df["Bucket"].value_counts().to_dict()
        healthy_n = counts.get(HEALTHY, 0)
        problem_n = len(df) - healthy_n

        c = st.columns(5)
        for col, b in zip(c, BUCKET_ORDER):
            col.metric(b, counts.get(b, 0))
        st.caption(f"{problem_n} pages need attention · {healthy_n} healthy · "
                   f"work top-to-bottom: red → orange → yellow.")

        st.divider()

        # Show buckets in priority order, most urgent first.
        for b in BUCKET_ORDER:
            sub = df[df["Bucket"] == b]
            if sub.empty:
                continue
            dot = BUCKET_COLOR[b]
            st.markdown(
                f"<h3><span style='color:{dot}'>●</span> {b} "
                f"<span style='font-size:0.6em;color:#8b8d98'>({len(sub)})</span></h3>",
                unsafe_allow_html=True,
            )
            st.caption(BUCKET_ONELINER[b])
            show = sub.sort_values("URL")[["_p", "Coverage", "Flags", "Action"]]
            show = show.rename(columns={"_p": "Page"})
            st.dataframe(show, use_container_width=True, hide_index=True)

        # Duplicate-slug watch (toolsvenue only, from seed analysis)
        dups = seed.SUSPECTED_DUPLICATES if site.key == "toolsvenue" else []
        if dups:
            st.divider()
            st.subheader("⚠️ Suspected duplicate tool URLs")
            st.caption("Same tool at two URLs — a clean slug and an old keyword-stuffed one. "
                       "They cannibalise each other. Keep one, 301 the other.")
            st.table(pd.DataFrame(dups, columns=["Keep (clean)", "301-redirect away (stuffed)"]))

        st.divider()
        st.download_button(
            "⬇️ Export full fix plan (CSV)",
            df.drop(columns=["_p"]).to_csv(index=False).encode(),
            file_name=f"{site.key}_fix_plan_{today}.csv",
            mime="text/csv",
        )


# ── TAB 2 — INDEXING ───────────────────────────────────────────────────────
with tab_index:
    if df.empty:
        st.info("No coverage data yet.")
    else:
        healthy_n = int((df["Bucket"] == HEALTHY).sum())
        total = len(df)
        st.metric("Indexed (healthy)", f"{healthy_n} / {total}")
        st.progress(healthy_n / total if total else 0)

        st.subheader("Coverage breakdown")
        cov = (df["Coverage"].value_counts().rename_axis("Coverage state")
               .reset_index(name="Pages"))
        st.bar_chart(cov.set_index("Coverage state"))

        st.subheader("Every page + live coverage")
        st.dataframe(
            df[["_p", "Coverage", "Bucket", "Flags"]].rename(columns={"_p": "Page"})
              .sort_values(["Bucket", "Page"]),
            use_container_width=True, hide_index=True,
        )
        if source == "seed":
            st.info("Showing your 16 Aug snapshot. Connect the GSC API + **Refresh live data** "
                    "to see whether your validation fixes have flipped pages to indexed.")


# ── TAB 3 — PERFORMANCE (GSC Search Analytics) ─────────────────────────────
with tab_perf:
    if not live_on:
        st.info("Performance needs the live Search Console API. Follow the README, then "
                "**Refresh live data**. (This report has no seed — it's live-only.)")
    else:
        pages = gsc.search_analytics(site.gsc_property, start, end, ["page"])
        queries = gsc.search_analytics(site.gsc_property, start, end, ["query"])
        if not pages and not queries:
            st.warning("No performance rows returned. Either the property has no clicks/impressions "
                       "in this range yet, or the service account isn't added to this GSC property.")
        else:
            if pages:
                pdf = pd.DataFrame(pages)
                tot = st.columns(2)
                tot[0].metric("Total clicks", int(pdf["clicks"].sum()))
                tot[1].metric("Total impressions", int(pdf["impressions"].sum()))
                st.subheader("Top pages")
                st.dataframe(pdf.sort_values("impressions", ascending=False),
                             use_container_width=True, hide_index=True)
            if queries:
                st.subheader("Top queries")
                st.dataframe(pd.DataFrame(queries).sort_values("impressions", ascending=False),
                             use_container_width=True, hide_index=True)


# ── TAB 4 — AUDIENCE (GA4) ─────────────────────────────────────────────────
with tab_aud:
    if not live_on or not site.ga4_property_id:
        st.info("Audience needs the GA4 Data API and a property id for this site. "
                "Add it in `seo/config.py` (or the .env), grant the service account "
                "Viewer access in GA4, then reload. (Live-only, no seed.)")
    else:
        s = ga4.summary(site.ga4_property_id, start, end)
        if not s:
            st.warning("No GA4 rows. Check the property id and that the service account has "
                       "Viewer access to this GA4 property.")
        else:
            cols = st.columns(5)
            cols[0].metric("Active users", f"{s['activeUsers']:,}")
            cols[1].metric("Sessions", f"{s['sessions']:,}")
            cols[2].metric("Page views", f"{s['pageViews']:,}")
            cols[3].metric("Avg session (s)", s["avgDuration"])
            cols[4].metric("Engagement", f"{s['engagementRate']}%")

            left, right = st.columns(2)
            with left:
                st.subheader("Traffic by channel")
                ch = ga4.channels(site.ga4_property_id, start, end)
                if ch:
                    st.dataframe(pd.DataFrame(ch), use_container_width=True, hide_index=True)
            with right:
                st.subheader("Top countries")
                co = ga4.countries(site.ga4_property_id, start, end)
                if co:
                    st.dataframe(pd.DataFrame(co), use_container_width=True, hide_index=True)

            st.subheader("Top landing pages")
            tp = ga4.top_pages(site.ga4_property_id, start, end)
            if tp:
                st.dataframe(pd.DataFrame(tp), use_container_width=True, hide_index=True)
