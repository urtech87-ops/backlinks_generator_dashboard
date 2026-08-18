"""
Opportunities — what to write next, and which words to write it for.

Two tabs, because they answer two different questions:

  💡 **Opportunity Finder** — scans your competitors, your own coverage and your
     Search Console queries, and returns a ranked list of things worth writing,
     each with the evidence behind it. Every card hands straight off: "Write
     this" fills in the Content page, "Target with links" preselects the page on
     the Backlinks page.

  🔑 **Keywords** — the optional keyword engine. Search Console first (the
     queries you already rank for, striking-distance terms flagged), free Google
     autocomplete second, a paid API only if you plug one in. It can be switched
     off entirely in Settings, and everything here says so plainly when it is.

The honest rule this page keeps: no invented search volumes. A keyword or a
topic with nothing measuring it is labelled **unvalidated**, every time.
"""

import pandas as pd
import streamlit as st

from agents import opportunity as opp
from core import keywords as kw, search
from ui import components as c
from ui import data as d

SCAN = "opp_scan"            # session state: the last competitor/coverage scan
KEYWORDS = "opp_keywords"    # session state: the loaded Search Console queries
BRIEF = "opp_brief"          # session state: the last keyword brief


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Opportunities · {site.label}",
        "What to write next, argued from your competitors, your own coverage and "
        "your real Search Console queries.",
    )

    tab_finder, tab_keywords = st.tabs(["💡 Opportunity Finder", "🔑 Keywords"])
    with tab_finder:
        _finder(ctx)
    with tab_keywords:
        _keywords(ctx)


# ══ Opportunity Finder ═════════════════════════════════════════════════════
def _finder(ctx) -> None:
    site = ctx.site
    coverage_df, source = d.coverage_frame(site)

    st.info("**This is the fallback for “I don't know what to write.”** It never copies a "
            "competitor — it records the topics and questions they cover, compares them "
            "with yours, and points at the openings.", icon="🧭")

    _readiness(ctx)
    st.divider()

    c.section("1 · What are we comparing against?",
              "Name the competitors if you know them. If you don't, give the niche and "
              "the finder takes the top independent sites ranking for it.")

    saved = opp.configured_competitors(site)
    cols = st.columns(2)
    niche = cols[0].text_input(
        "Your niche, in the words people search",
        key="opp_niche",
        placeholder="e.g. free online developer tools",
        help="Used to find competitors when you haven't named any, and to pick which of "
             "their pages are worth reading.",
    )
    competitor_text = cols[1].text_input(
        "Competitor sites (optional, comma-separated)",
        value=", ".join(saved), key="opp_competitors",
        placeholder="example.com, another-site.com",
        help="Save these permanently in Settings → Sites so you don't retype them.",
    )
    competitors = [x.strip() for x in competitor_text.replace(",", " ").split() if x.strip()]

    cols = st.columns([1, 1, 2])
    max_competitors = cols[0].number_input(
        "Sites to scan", min_value=1, max_value=5, value=min(3, max(len(competitors), 3)),
        key="opp_max", help="Capped low on purpose. This is analysis, not scraping.",
    )
    read_pages = cols[1].checkbox(
        "Read a few of their pages", value=False, key="opp_read",
        help="Slower, and politer than it sounds — robots.txt is honoured, at most four "
             "pages per site, with a pause between each. It's what finds the questions "
             "they answer.",
    )
    use_keywords = cols[2].checkbox(
        "Use my Search Console queries", value=kw.enabled(), key="opp_use_kw",
        disabled=not kw.enabled(),
        help="Adds striking-distance opportunities and puts real impression numbers "
             "behind the gaps. Needs the keyword engine on." if kw.enabled() else
             "The keyword engine is switched off in Settings.",
    )

    if st.button("🔭 Scan for opportunities", type="primary", key="opp_scan_btn"):
        bar = st.progress(0.0, text="Starting…")
        result = opp.scan(
            site, coverage_df, niche=niche, competitors=competitors,
            start=ctx.start, end=ctx.end, use_keywords=use_keywords,
            read_pages=read_pages, max_competitors=int(max_competitors),
            progress=lambda fraction, message: bar.progress(min(fraction, 1.0),
                                                            text=message),
        )
        bar.empty()
        st.session_state[SCAN] = {"site": site.key, "result": result, "niche": niche}
        if result.keywords:
            st.session_state[KEYWORDS] = {"site": site.key, "keywords": result.keywords,
                                          "range": f"{ctx.start} → {ctx.end}"}

    state = st.session_state.get(SCAN) or {}
    if state.get("site") != site.key or not state.get("result"):
        st.caption("Nothing scanned yet. You can run it with no competitors at all — it "
                   "will still read your own coverage and your Search Console queries.")
        return

    st.divider()
    _results(ctx, state["result"], source)


def _results(ctx, result, coverage_source: str) -> None:
    c.section("2 · What came back", result.detail)

    for note in result.notes:
        st.warning(note, icon="ℹ️")

    if not result.opportunities:
        c.empty_state(
            "No opportunities surfaced yet",
            "The finder needs something to compare: a competitor domain, a niche phrase "
            "it can search, or your own coverage data.",
            steps=[
                "Add a competitor domain above (or in **Settings → Sites**).",
                "Check the search provider works — **Settings → Prospecting → Test search**.",
                "Connect Search Console so your own queries can be read.",
            ],
            icon="💡",
        )
        return

    counts = {}
    for item in result.opportunities:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    c.metric_row([(f"{opp.KIND_ICON[kind]} {kind}", counts.get(kind, 0), opp.KIND_BLURB[kind])
                  for kind in (opp.STRIKING, opp.GAP, opp.ORPHAN, opp.REWRITE)])

    if coverage_source == "seed":
        st.caption("Your side of the comparison is the 16 Aug seed snapshot — refresh live "
                   "data in the sidebar once Search Console is connected.")

    kinds = st.multiselect(
        "Show", options=[k for k in (opp.STRIKING, opp.GAP, opp.ORPHAN, opp.REWRITE)
                         if counts.get(k)],
        default=[k for k in (opp.STRIKING, opp.GAP, opp.ORPHAN, opp.REWRITE)
                 if counts.get(k)],
        key="opp_kinds", help="Filter the list by the kind of opportunity.",
    )

    shown = [o for o in result.opportunities if o.kind in kinds]
    for i, item in enumerate(shown):
        _card(ctx, item, i)

    if result.maps:
        with st.expander(f"What the {len(result.maps)} competitors actually cover"):
            for cmap in result.maps:
                st.markdown(f"**{cmap.domain}** — {cmap.detail or 'nothing readable.'}")
                if cmap.pages:
                    st.caption("Topics found: "
                               + ", ".join(p.topic for p in cmap.pages[:25])
                               + ("…" if len(cmap.pages) > 25 else ""))
                if cmap.questions:
                    st.caption("Questions they answer: " + " · ".join(cmap.questions[:8]))

    st.download_button(
        "⬇️ Export the opportunities (CSV)",
        _frame(result.opportunities).to_csv(index=False).encode(),
        file_name=f"{ctx.site.key}_opportunities.csv", mime="text/csv",
        key="opp_export",
        help="Topic, kind, demand, evidence and the suggested angle for each one.",
    )


def _card(ctx, item, index: int) -> None:
    with st.container(border=True):
        head, badge = st.columns([5, 1])
        head.markdown(f"**{item.icon} {item.topic}**")
        head.caption(f"{item.kind} · {item.demand}")
        with badge:
            c.show_badge("warn" if item.unvalidated else "ok", f"score {item.score}")

        for reason in item.reasons:
            st.markdown(f"- {reason}")
        for warning in item.warnings:
            st.caption(f"⚠️ {warning}")
        if item.questions:
            st.caption("Questions to answer better: " + " · ".join(item.questions))
        if item.angle:
            st.caption(f"**Angle:** {item.angle}")

        cols = st.columns([1, 1, 2])
        cols[0].button(
            "✍️ Write this", key=f"opp_write_{index}", type="primary",
            on_click=_to_content, args=(item,),
            help="Fills in the Content page's topic, keyword and direction, then takes "
                 "you there.",
        )
        if item.target_page:
            cols[1].button(
                "🔗 Target with links", key=f"opp_link_{index}",
                on_click=_to_backlinks, args=(item.target_page,),
                help="Preselects this page on the Backlinks page, so the next article "
                     "you publish links to it.",
            )
            cols[2].caption(f"Existing page: {item.target_page}")
        else:
            cols[2].caption("No page of yours covers this yet — it's a new article.")


def _frame(items: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "Topic": o.topic, "Kind": o.kind, "Score": o.score, "Keyword": o.keyword,
        "Demand": o.demand, "Impressions": o.impressions,
        "Position": o.position or None,
        "Existing page": o.target_page, "Competitors": ", ".join(o.competitors),
        "Why": " ".join(o.reasons), "Angle": o.angle,
    } for o in items])


# ── Hand-offs to the other pages ───────────────────────────────────────────
def _to_content(item) -> None:
    """
    Fill the Content page's boxes and jump there. Runs as a button callback, so
    it happens before the next rerun draws those widgets.
    """
    direction = item.angle
    if item.target_page and item.kind in (opp.STRIKING, opp.REWRITE):
        direction += f" This is about an existing page: {item.target_page}."
    st.session_state.update({
        "content_topic": item.topic,
        "content_keyword": item.keyword,
        "content_notes": direction,
        "nav": "Content",
    })


def _to_backlinks(url: str) -> None:
    """Preselect this page as the Backlinks target and jump there."""
    st.session_state.update({"bl_focus_url": url, "nav": "Backlinks"})


def _to_content_keyword(keyword: str, topic: str = "") -> None:
    st.session_state.update({
        "content_keyword": keyword,
        "content_topic": topic or st.session_state.get("content_topic", "") or keyword,
        "nav": "Content",
    })


# ══ Keywords ═══════════════════════════════════════════════════════════════
def _keywords(ctx) -> None:
    site = ctx.site

    if not kw.enabled():
        c.empty_state(
            "The keyword engine is switched off",
            "That's a supported setting, not a broken one — the Opportunity Finder, the "
            "Content page and the Backlinks page all work without it. Turned on, it reads "
            "the queries you already rank for in Search Console, flags the ones sitting "
            "5th-20th, and expands them with free Google autocomplete. It needs no paid key.",
            steps=[
                "Open **Settings → Content tools**.",
                "Set **Keyword engine** to *On*.",
                "Come back here and press **Load my Search Console queries**.",
            ],
            icon="🔑",
        )
        c.nav_button("Open Settings", "Settings", key="kw_settings_off")
        return

    st.info(kw.status(), icon="🔑")

    c.section("1 · The queries you already rank for",
              f"Straight from Search Console for {ctx.start} → {ctx.end} — first-party, "
              "free, and the only numbers on this page that are actually measured.")

    if not ctx.creds:
        st.warning("No Google service-account file, so there are no Search Console "
                   "queries to read. Autocomplete below still works, but everything it "
                   "returns is unvalidated.", icon="🟡")
        c.nav_button("Connect Search Console", "Settings", key="kw_settings_creds")

    if st.button("📥 Load my Search Console queries", key="kw_load", disabled=not ctx.creds):
        with st.spinner("Reading Search Console…"):
            found = kw.gsc_keywords(site, ctx.start, ctx.end)
        st.session_state[KEYWORDS] = {"site": site.key, "keywords": found["keywords"],
                                      "range": f"{ctx.start} → {ctx.end}",
                                      "detail": found["detail"], "ok": found["ok"]}
        if not found["ok"]:
            st.warning(found["detail"], icon="⚠️")

    state = st.session_state.get(KEYWORDS) or {}
    loaded = state["keywords"] if state.get("site") == site.key else []

    if loaded:
        _query_tables(ctx, loaded)
    else:
        st.caption("Nothing loaded yet. The keyword brief below works without this — it "
                   "just has no measured demand to rank on.")

    st.divider()
    _brief_builder(ctx, loaded)


def _query_tables(ctx, loaded: list) -> None:
    striking = kw.striking_distance(loaded)
    winning = [k for k in loaded if k.band == kw.WINNING]
    deep = [k for k in loaded if k.band == kw.DEEP]

    c.metric_row([
        ("Queries", len(loaded), "Every query with impressions in this range."),
        ("🎯 Striking distance", len(striking),
         "Position 5-20 with real impressions — one push from page one."),
        ("🟢 Already winning", len(winning), "Position 1-4. Protect these."),
        ("🔭 Ranking deep", len(deep), "Demand, but a long way down. Content, not links."),
    ])

    if striking:
        st.markdown("**🎯 Striking distance — the fastest wins you own**")
        st.caption("Each of these has a page that already ranks. Strengthening it beats "
                   "starting a new article for the same term.")
        st.dataframe(_kw_frame(striking), width="stretch", hide_index=True)

        choice = st.selectbox(
            "Send one to the writer", options=list(range(len(striking))),
            format_func=lambda i: (f"{striking[i].keyword} — position "
                                   f"{striking[i].position}, "
                                   f"{striking[i].impressions:,} impressions"),
            key="kw_pick",
            help="Fills the Content page in with this keyword, or preselects its page "
                 "on the Backlinks page.",
        )
        picked = striking[choice]
        cols = st.columns([1, 1, 2])
        cols[0].button("✍️ Write for this keyword", key="kw_to_content", type="primary",
                       on_click=_to_content_keyword, args=(picked.keyword, picked.keyword))
        if picked.page:
            cols[1].button("🔗 Target with links", key="kw_to_backlinks",
                           on_click=_to_backlinks, args=(picked.page,))
            cols[2].caption(f"Ranking page: {picked.page}")
        else:
            cols[2].caption("Search Console didn't name the ranking page for this query.")
    else:
        st.caption("No striking-distance queries in this range. That's usually a sign "
                   "there aren't enough impressions yet — the Fix Plan comes first.")

    with st.expander(f"All {len(loaded)} queries"):
        st.dataframe(_kw_frame(loaded), width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Export the queries (CSV)",
            _kw_frame(loaded).to_csv(index=False).encode(),
            file_name=f"{ctx.site.key}_keywords.csv", mime="text/csv", key="kw_export")


def _kw_frame(items: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "Keyword": k.keyword, "Band": k.band, "Intent": k.intent,
        "Clicks": k.clicks, "Impressions": k.impressions,
        "Position": k.position or None, "Volume": k.volume_label,
        "Page": k.page, "Why": k.reason,
    } for k in items])


def _brief_builder(ctx, loaded: list) -> None:
    c.section("2 · Build a keyword brief for one topic",
              "Search Console first, then free Google autocomplete, then a paid API only "
              "if you've plugged one in. Anything nothing measured is labelled unvalidated.")

    topic = st.text_input(
        "Topic or page you're writing about", key="kw_topic",
        placeholder="e.g. compress a JPEG without losing quality",
        help="The engine matches this against your real queries first, then expands it.",
    )
    use_auto = st.checkbox(
        "Expand with Google autocomplete", value=True, key="kw_auto",
        help="Free and needs no key. It shows how people phrase the search — but not how "
             "many, so those terms stay unvalidated.",
    )

    if st.button("🔑 Build the brief", key="kw_brief_btn", type="primary",
                 disabled=not topic.strip()):
        with st.spinner("Matching your queries, then expanding…"):
            result = kw.brief(topic, ctx.site, ctx.start, ctx.end,
                              use_autocomplete=use_auto,
                              gsc_keywords_cached=loaded or None)
        st.session_state[BRIEF] = {"site": ctx.site.key, "brief": result}

    state = st.session_state.get(BRIEF) or {}
    if state.get("site") != ctx.site.key or not state.get("brief"):
        return

    brief = state["brief"]
    if brief.topic != topic.strip() and topic.strip():
        st.info(f"The brief below is for “{brief.topic}”. Press the button again for the "
                "topic now in the box.")

    if not brief.ok:
        st.warning(brief.detail, icon="⚠️")
    if brief.notes:
        st.caption(brief.notes)

    primary = brief.primary
    if primary:
        with st.container(border=True):
            head, badge = st.columns([5, 1])
            head.markdown(f"**Primary keyword — {primary.keyword}**")
            head.caption(f"{primary.intent} intent · from {primary.source} · "
                         f"volume: {primary.volume_label}")
            with badge:
                c.show_badge("ok" if primary.validated else "warn",
                             primary.band if primary.validated else "unvalidated")
            st.caption(primary.reason)
            cols = st.columns([1, 1, 2])
            cols[0].button("✍️ Write with this keyword", key="kw_brief_content",
                           type="primary", on_click=_to_content_keyword,
                           args=(primary.keyword, brief.topic))
            if brief.target_page:
                cols[1].button("🔗 Target with links", key="kw_brief_backlinks",
                               on_click=_to_backlinks, args=(brief.target_page,))
                cols[2].caption(f"Strengthen the page that already ranks: "
                                f"{brief.target_page}")
            else:
                cols[2].caption("No page of yours ranks for this yet — write a new one.")

    if brief.secondary:
        st.markdown("**Secondary and long-tail cluster**")
        st.dataframe(_kw_frame(brief.secondary), width="stretch", hide_index=True)

    if brief.questions:
        st.markdown("**Real questions to answer (feeds the FAQ)**")
        for question in brief.questions:
            st.markdown(f"- {question}")

    if brief.sources_used:
        st.caption("Sources used: " + ", ".join(brief.sources_used) + ".")


# ── Readiness ──────────────────────────────────────────────────────────────
def _readiness(ctx) -> None:
    c.section("Readiness", "What this page can see right now.")
    rows = []

    gaps = search.missing()
    rows.append({
        "name": "Competitor scan", "state": "warn" if gaps else "ok",
        "label": "needs a key" if gaps else search.provider(),
        "detail": (f"{search.PROVIDERS[search.provider()]} — still missing: "
                   f"{', '.join(gaps)}." if gaps else
                   f"Competitors are found and mapped through "
                   f"{search.PROVIDERS[search.provider()]}, plus their own sitemap."),
    })

    rows.append({
        "name": "Keyword engine", "state": "ok" if kw.enabled() else "idle",
        "label": "on" if kw.enabled() else "off",
        "detail": kw.status(),
    })

    rows.append({
        "name": "Search Console queries", "state": "ok" if ctx.creds else "warn",
        "label": "connected" if ctx.creds else "seed mode",
        "detail": ("Your real queries are readable, so gaps can carry measured "
                   "impressions." if ctx.creds else
                   "No service-account file, so nothing here has measured demand behind "
                   "it — every topic is a lead, not a number."),
    })

    saved = opp.configured_competitors(ctx.site)
    rows.append({
        "name": "Saved competitors", "state": "ok" if saved else "idle",
        "label": f"{len(saved)} saved" if saved else "none yet",
        "detail": (", ".join(saved) if saved else
                   "None saved for this site. Add them in Settings → Sites, or type them "
                   "below for a one-off scan."),
    })

    for row in rows:
        cols = st.columns([2, 1, 4])
        cols[0].markdown(f"**{row['name']}**")
        with cols[1]:
            c.show_badge(row["state"], row["label"])
        cols[2].caption(row["detail"])
