"""
Saved & Impact (Phase 17) — two small, related jobs:

  1 · Saved items    A browsable archive of every article/backlink draft the
                     Content and Backlinks pages generated and you pressed
                     Save on. Generation costs money, so nothing generated
                     should ever be lost between sessions — but nothing here
                     saves itself; every row exists because of a click.

  2 · Impact         Before/after for a page from the moment it entered
                     tracking — automatically, the instant an article or
                     backlink is generated for it, or by hand for work done
                     outside this tool. Honest by design: it shows raw
                     numbers and flags anything under two weeks as too early
                     to read, rather than ever claiming a link or an article
                     "worked".
"""

import datetime as dt

import pandas as pd
import streamlit as st

from core import config, impact, saved_items
from ui import components as c
from ui import data as d


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Saved & Impact · {site.label}",
        "Everything you've generated, kept safe — and whether the pages you've worked "
        "on are actually moving.",
    )
    c.jargon_note("Impressions", "Average position", "Striking distance")

    tab_saved, tab_impact = st.tabs(["💾 Saved items", "📈 Impact tracking"])
    with tab_saved:
        _saved_items_tab(site)
    with tab_impact:
        _impact_tab(ctx)


# ── Feature 1: saved items ──────────────────────────────────────────────────
def _saved_items_tab(site: config.Site) -> None:
    c.section(
        "Saved items",
        "Every article or backlink draft you pressed 💾 Save on, on the Content or "
        "Backlinks page — kept on disk whether or not you ever publish it. Saving is "
        "always manual; nothing here saves anything by itself.",
    )

    cols = st.columns(2)
    site_filter = cols[0].selectbox(
        "Site", options=["All sites"] + [s.key for s in config.SITES],
        format_func=lambda k: "All sites" if k == "All sites" else config.SITES_BY_KEY[k].label,
        key="si_site_filter",
    )
    type_filter = cols[1].selectbox(
        "Type", options=["All types", saved_items.TYPE_ARTICLE, saved_items.TYPE_BACKLINK],
        format_func=lambda t: "All types" if t == "All types" else saved_items.TYPE_LABEL[t],
        key="si_type_filter",
    )

    items = saved_items.list_items(
        site_key="" if site_filter == "All sites" else site_filter,
        item_type="" if type_filter == "All types" else type_filter,
    )
    if not items:
        c.empty_state(
            "Nothing saved yet",
            "Press the 💾 Save button under a generated article on the Content page, or "
            "under a generated draft on the Backlinks page, and it lands here.",
            icon="💾",
        )
        return

    st.caption(f"{len(items)} saved item(s).")
    st.dataframe(
        pd.DataFrame([{
            "Saved": it.get("saved_at", ""),
            "Site": config.SITES_BY_KEY[it["site"]].label
                    if it.get("site") in config.SITES_BY_KEY else it.get("site", ""),
            "Type": saved_items.TYPE_LABEL.get(it.get("type", ""), it.get("type", "")),
            "Title": it.get("title", ""),
            "Target / platform": it.get("target_url") or it.get("platform") or "",
            "Model": it.get("model", ""),
        } for it in items]),
        width="stretch", hide_index=True,
    )

    labels = [f"{it.get('saved_at', '')} · "
              f"{saved_items.TYPE_LABEL.get(it.get('type', ''), it.get('type', ''))} · "
              f"{it.get('title', 'Untitled')}" for it in items]
    index = st.selectbox(
        "Open an item to read or copy its full content",
        options=list(range(len(items))), format_func=lambda i: labels[i],
        key="si_open_pick",
    )
    _open_item(items[index])


def _open_item(row: dict) -> None:
    full = saved_items.load_item(row["path"])
    if not full:
        st.error("Couldn't reload this item from disk — the file may have been moved "
                  f"or deleted (`{row.get('path', '')}`).")
        return
    site_label = (config.SITES_BY_KEY[full["site"]].label
                  if full.get("site") in config.SITES_BY_KEY else full.get("site", ""))
    with st.container(border=True):
        st.markdown(f"**{full.get('title', 'Untitled')}**")
        bits = [saved_items.TYPE_LABEL.get(full.get("type", ""), full.get("type", "")),
                site_label, f"saved {full.get('saved_at', '')}"]
        if full.get("target_url"):
            bits.append(f"links to {full['target_url']}")
        if full.get("platform"):
            bits.append(f"for {full['platform']}")
        if full.get("model"):
            bits.append(full["model"])
        st.caption(" · ".join(b for b in bits if b))
        st.code(full.get("content", ""),
                language="html" if (full.get("format") or "").endswith("html") else "markdown")


# ── Feature 2: impact tracking ──────────────────────────────────────────────
def _impact_tab(ctx) -> None:
    site = ctx.site
    c.section(
        "Impact tracking",
        "Before/after for pages you've actually worked on — the raw numbers, so you "
        "can judge for yourself. SEO movement takes weeks and is noisy; this never "
        "prints a confident \"it worked\".",
    )
    st.info(
        "**Honest limit.** A page is tracked only from the moment it's added here — "
        "there's no way to reconstruct a baseline for work done before tracking "
        "started. If you rewrote a page last month with no tracking, there's no "
        "\"before\" to compare it to.",
        icon="🩺",
    )

    _manual_track_form(site)
    st.write("")

    rows = impact.tracked_pages(site.key)
    if rows.empty:
        c.empty_state(
            "Nothing tracked yet",
            "A page is added here automatically the moment you generate an article or "
            "backlink for it, or by hand with the form above for work done outside "
            "this tool.",
            icon="📈",
        )
        return

    if not d.has_live_performance(site):
        st.caption("⚠️ No live performance data cached yet — press **Refresh live data** "
                   "in the sidebar to see the latest side of every comparison below.")

    metrics = d.performance_metrics(site)
    latest_date = d.last_refreshed(site)
    st.caption(f"{len(rows)} page(s) tracked.")
    for _, row in rows.iterrows():
        latest = metrics.get(str(row["url"]).rstrip("/"), {})
        cmp = impact.compare(site.key, row["url"], latest, latest_date)
        if cmp:
            _impact_row(cmp)


def _manual_track_form(site: config.Site) -> None:
    with st.expander("➕ I worked on this page (done outside this tool)"):
        st.caption("For a hand rewrite, a manual fix, anything you did yourself outside "
                   "this dashboard. Snapshots today's cached metrics as the starting point "
                   "— it does not call Search Console itself.")
        coverage_df, _ = d.coverage_frame(site)
        pages = (coverage_df["URL"].tolist()
                 if coverage_df is not None and not coverage_df.empty else [])
        if pages:
            picked = st.selectbox(
                "Pick one of your pages…", options=[""] + pages, key="im_page_pick",
                format_func=lambda u: "— or type the URL below —" if u == "" else u,
                help="Optional shortcut — fills the URL box below.",
            )
            if picked:
                st.session_state["im_url"] = picked

        url = st.text_input("Page URL", key="im_url",
                            placeholder="https://yoursite.com/the-page")
        if st.button("📌 Start tracking this page", key="im_track",
                     disabled=not url.strip()):
            _start_manual_tracking(site, url.strip())


def _start_manual_tracking(site: config.Site, url: str) -> None:
    if impact.is_tracked(site.key, url):
        st.info("Already tracked — overwriting the baseline would defeat the point of "
                "tracking, so the original snapshot is kept.")
        return
    baseline = d.performance_metrics(site).get(url.rstrip("/"), {})
    impact.start_tracking(
        site.key, url, impact.REASON_MANUAL, baseline,
        baseline_date=d.last_refreshed(site) or dt.date.today().isoformat(),
    )
    if not baseline:
        st.warning("Tracking started, but no live performance data is cached for this "
                   "page yet, so the baseline is 0 impressions / 0 clicks / no position "
                   "rather than a real measurement. Refresh live data soon so the "
                   "baseline actually means something.", icon="⚠️")
    else:
        st.success("Tracking started — today's cached numbers are the baseline.", icon="📌")


def _impact_row(cmp: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{cmp['url']}**")
        st.caption(f"{impact.REASON_LABEL.get(cmp['reason'], cmp['reason'])} · "
                   f"baseline {cmp['baseline_date']} · {cmp['days_elapsed']} day(s) ago")

        if not cmp["baseline_live"]:
            st.caption("⚠️ No live performance data was cached when tracking started, so "
                       "the baseline below is unmeasured (0), not a real reading.")

        if cmp["too_early"]:
            st.warning("**Too early to tell** — short-term changes can be noise. SEO "
                       "movement typically takes weeks; give it at least two weeks "
                       "before reading anything into this.", icon="⏳")

        baseline = cmp["baseline"]
        if not cmp["has_latest"]:
            st.caption("No live performance data cached for the latest side yet — press "
                       "**Refresh live data** in the sidebar to fill this in.")
            c.metric_row([
                ("Baseline impressions", f"{baseline['impressions']:,}"),
                ("Baseline clicks", f"{baseline['clicks']:,}"),
                ("Baseline position", baseline["position"] or "—"),
            ])
            return

        latest = cmp["latest"]
        change = cmp["change"]
        pos_delta = (change["position"]
                     if latest.get("position") and baseline["position"] else None)
        cols = st.columns(3)
        cols[0].metric("Impressions", f"{int(latest.get('impressions', 0)):,}",
                       delta=change["impressions"])
        cols[1].metric("Clicks", f"{int(latest.get('clicks', 0)):,}",
                       delta=change["clicks"])
        cols[2].metric("Average position", latest.get("position") or "—",
                       delta=pos_delta, delta_color="inverse")
        st.caption(
            f"Baseline ({cmp['baseline_date']}): {baseline['impressions']:,} impressions, "
            f"{baseline['clicks']:,} clicks, position {baseline['position'] or '—'}. "
            f"Latest ({cmp.get('latest_date') or '—'}): "
            f"{int(latest.get('impressions', 0)):,} impressions, "
            f"{int(latest.get('clicks', 0)):,} clicks, "
            f"position {latest.get('position') or '—'}."
        )
