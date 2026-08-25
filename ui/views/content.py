"""
Content — the writing side, in two paths that share one standard.

  · the QUALITY path is the skills in `.claude/skills/`. You run it in Claude
    Code and it researches deeply, one piece at a time.
  · the VOLUME path is this page (Phase 5): a topic goes in, the agent searches
    the web, writes an SEO/AEO/GEO article with your CONTENT_MODEL, makes the
    images (or their briefs), and files it as a WordPress **draft**.

Both obey the same rules, and this page shows them being obeyed: every draft is
checked against the writer skill's non-negotiables before you publish, and every
cited source is traced back to research this run actually found. Nothing here
goes live — WordPress is always a draft.
"""

import streamlit as st

from agents import content as agent
from core import config, images as image_api, keywords as kw, search
from ui import components as c
from ui import data as d

RUN = "content_run"          # session state: the current topic → draft → images run
CHECK_LABEL = {"ok": "pass", "warn": "check", "bad": "fix this"}
KEYWORD_BRIEF = "content_kw_brief"   # session state: the last keyword brief


SKILLS = [
    ("content-agent-orchestrator", "Runs the whole pipeline end to end for one topic."),
    ("keyword-researcher", "Real keywords from Search Console first, free expansion second."),
    ("website-brand-scraper", "Learns your voice and the internal pages to link to."),
    ("competitor-site-scraper", "Finds the gap competitors cover thinly or miss."),
    ("blog-writer-seo-aeo-geo", "Writes the article to rank *and* be quotable by AI engines."),
    ("blog-image-generator", "Featured + supporting images, or image briefs if no image API."),
    ("wordpress-publisher", "Creates the WordPress draft. Always a draft."),
]


def render(ctx) -> None:
    site = ctx.site
    c.page_header(
        f"Content · {site.label}",
        "Turn a topic into a WordPress draft that's actually worth indexing.",
    )

    st.info("**Quality over volume.** Thin AI pages are what got these pages rejected in "
            "the first place — the Fix Plan's orange bucket is the receipt. Every path "
            "here ends in a **draft** you review, never a live post.", icon="⚠️")

    st.caption("The path is always the same: say what the article is about → the agent "
               "researches it → you read and edit the draft → it's filed as a WordPress "
               "**draft** for you to publish yourself.")
    c.jargon_note("Impressions", "Striking distance", "Indexed")

    coverage_df, _ = d.coverage_frame(site)
    _readiness(site)
    st.divider()

    _writer(ctx, coverage_df)

    st.divider()
    _saved_runs()

    st.divider()
    _quality_path()


# ── The writer ─────────────────────────────────────────────────────────────
def _writer(ctx, coverage_df) -> None:
    site = ctx.site

    c.section("1 · What should this article be about?",
              "Write the topic the way a person would search for it — that's what the "
              "research step goes looking for.")

    # Filled in by the Overview, the Opportunity Finder or the keyword engine.
    # Popped before the boxes are drawn, so it shows once and doesn't stick.
    handed_over = st.session_state.pop("content_source", "")
    if handed_over:
        st.success(f"Filled in from {handed_over}. Edit anything below before you run it.",
                   icon="💡")

    topic = st.text_input(
        "Topic", key="content_topic",
        placeholder="e.g. How do you compress a JPEG without visible quality loss?",
        help="One article, one question. A topic phrased as a real question tends to "
             "produce a piece answer engines can quote.",
    )

    cols = st.columns(2)
    keyword = cols[0].text_input(
        "Primary keyword (optional)", key="content_keyword",
        placeholder="e.g. compress jpeg without losing quality",
        help="Leave blank and the agent picks the phrase it thinks people search for. "
             "Or fill it from your own Search Console data with the keyword engine "
             "below.",
    )
    notes = cols[1].text_input(
        "Anything the writer should know (optional)", key="content_notes",
        placeholder="e.g. aimed at photographers, mention batch processing",
        help="Free text passed to the model — an angle, an audience, a use-case.",
    )

    _keyword_helper(ctx, topic)

    options = agent.internal_link_options(coverage_df, site)
    if options:
        picked = st.multiselect(
            "Pages this article should link to", options=[o["url"] for o in options],
            default=[o["url"] for o in options[:4]],
            format_func=lambda u: next((o["page"] for o in options if o["url"] == u), u),
            key="content_internal",
            help="Only indexed pages are offered. Linking a new article to a page Google "
                 "has already rejected spreads the problem instead of fixing it.",
        )
        internal = [o for o in options if o["url"] in picked]
    else:
        internal = []
        st.caption("No indexed pages to link to yet, so the article will link to your "
                   "homepage only. Clear the Fix Plan and they'll appear here.")

    st.write("")
    c.section("2 · Research it, then write it",
              f"Research runs through your search provider "
              f"(`{search.PROVIDERS[search.provider()]}`); the article is written by "
              f"`{config.get('CONTENT_MODEL', 'no model set')}`.")

    if not config.is_set("OPENROUTER_API_KEY"):
        st.warning("No OpenRouter key saved, so nothing can be written yet.", icon="🔑")
        c.nav_button("Add an OpenRouter key", "Settings", key="content_key")
        return

    if st.button("🔎 Research and write the draft", type="primary", key="content_write",
                 disabled=not topic.strip()):
        _run(site, topic, keyword, notes, internal)

    run = st.session_state.get(RUN) or {}
    if not run.get("draft") or run.get("site") != site.key:
        st.caption("Nothing drafted yet. Enter a topic above and press the button.")
        return

    if run.get("topic") != topic.strip() and topic.strip():
        st.info(f"The draft below is for “{run['topic']}”, not the topic now in the box. "
                "Press the button again to write the new one.")

    _research_summary(run["research"])
    _review(site, run)


def _keyword_helper(ctx, topic: str) -> None:
    """
    The keyword engine (Phase 6) feeding the writer: real Search Console terms
    first, free autocomplete second. Optional — switched off, this is one line
    saying so, and the writer picks its own phrase as it always did.
    """
    if not kw.enabled():
        st.caption("The keyword engine is switched off, so the writer will choose the "
                   "phrase itself. Turn it on in Settings → Content tools to target a "
                   "keyword you already get impressions for.")
        return

    with st.expander("🔑 Pick the keyword from real data instead of guessing"):
        st.caption(kw.status())
        if st.button("Build a keyword brief for this topic", key="content_kw_build",
                     disabled=not topic.strip()):
            with st.spinner("Matching your Search Console queries, then expanding…"):
                st.session_state[KEYWORD_BRIEF] = {
                    "site": ctx.site.key,
                    "brief": kw.brief(topic, ctx.site, ctx.start, ctx.end),
                }

        state = st.session_state.get(KEYWORD_BRIEF) or {}
        brief = state["brief"] if state.get("site") == ctx.site.key else None
        if not brief:
            st.caption("Nothing built yet. The full picture — striking-distance terms, "
                       "the secondary cluster, the questions — lives on the "
                       "Opportunities page.")
            c.nav_button("Open the keyword engine", "Opportunities",
                         key="content_kw_nav")
            return

        if not brief.ok:
            st.warning(brief.detail, icon="⚠️")
        if brief.notes:
            st.caption(brief.notes)

        for i, candidate in enumerate(brief.cluster[:8]):
            cols = st.columns([4, 2, 1])
            label = "unvalidated" if candidate.unvalidated else candidate.band
            cols[0].markdown(f"**{candidate.keyword}**")
            cols[0].caption(candidate.reason)
            with cols[1]:
                c.show_badge("warn" if candidate.unvalidated else "ok", label)
            cols[2].button("Use", key=f"content_kw_use_{i}",
                           on_click=lambda k=candidate.keyword:
                               st.session_state.update({"content_keyword": k}),
                           help="Puts this in the primary keyword box above.")

        if brief.questions:
            st.caption("Questions worth answering in the FAQ: "
                       + " · ".join(brief.questions[:6]))


def _run(site, topic: str, keyword: str, notes: str, internal: list) -> None:
    """Research → write, with a progress bar and no exceptions escaping."""
    progress = st.progress(0.15, text="Searching the web for what's already been written…")
    research = agent.research(topic, site)

    progress.progress(0.45, text="Reading your site so the piece sounds like you…")
    brand = agent.page_facts(site.homepage)

    progress.progress(0.6, text="Writing the article — this is the slow part…")
    result = agent.write(topic, site, research, internal, keyword, notes, brand)
    progress.empty()

    if not result.ok:
        st.error(result.detail, icon="⚠️")
        return

    st.session_state[RUN] = {
        "site": site.key, "topic": topic.strip(), "research": research,
        "draft": result.draft, "images": [], "result": None, "folder": "",
    }


def _research_summary(research) -> None:
    if research.ok:
        st.success(research.detail, icon="🔎")
    else:
        st.warning(f"Research came back empty — {research.detail} The article was written "
                   "**qualitatively**: it may not state a single statistic, and any figure "
                   "in it is unvalidated. Fix the search provider in Settings and rerun for "
                   "a stronger piece.", icon="🔎")
    if research.sources:
        with st.expander(f"The {len(research.sources)} sources the research found"):
            for s in research.sources:
                st.markdown(f"- [{s['title'] or s['url']}]({s['url']})")
                if s["snippet"]:
                    st.caption(s["snippet"])


# ── Review, images, publish ────────────────────────────────────────────────
def _review(site, run: dict) -> None:
    draft = run["draft"]

    st.divider()
    c.section("3 · Read it before anyone else does",
              "These checks are the writer skill's rules, applied to what the model "
              "actually produced. Edit anything — what's in these boxes is what gets "
              "filed as the draft.")

    rows = agent.check(draft, run["research"], site)
    c.status_rows([{**row, "label": CHECK_LABEL[row["state"]]} for row in rows],
                  widths=(2, 1, 5))

    st.write("")
    body_tab, meta_tab, faq_tab = st.tabs(["📄 Article", "🏷️ Meta + tags", "❓ FAQ + sources"])

    with body_tab:
        st.text_input("Title (H1)", value=draft.title, key="content_title")
        st.text_area("Article (markdown)", value=draft.body_markdown, height=520,
                     key="content_body",
                     help="Markdown. Headings, links and the FAQ section are all in here.")
        st.caption(draft.detail)

    with meta_tab:
        meta = draft.meta
        st.text_input("Meta title", value=meta.get("meta_title", ""), key="content_meta_title",
                      help="What Google shows as the blue link. 60 characters or fewer.")
        st.text_area("Meta description", value=meta.get("meta_description", ""), height=90,
                     key="content_meta_desc",
                     help="The grey line under it. 155 characters or fewer.")
        cols = st.columns(2)
        cols[0].text_input("Slug", value=meta.get("slug", ""), key="content_slug",
                           help="The URL ending. Three to five words — long stuffed slugs "
                                "are a low-quality signal on their own.")
        cols[1].text_input("Primary keyword", value=meta.get("primary_keyword", ""),
                           key="content_kw", help="Recorded in meta.json for your notes.")
        cols = st.columns(2)
        cols[0].text_input("Tags (comma-separated)", value=", ".join(meta.get("tags", [])),
                           key="content_tags")
        cols[1].text_input("Categories (comma-separated)",
                           value=", ".join(meta.get("categories", [])),
                           key="content_cats",
                           help="Created in WordPress if they don't exist yet.")
        st.caption(f"Schema to add on review: {', '.join(meta.get('schema', [])) or '—'} "
                   "(JSON-LD, via your SEO plugin or a block).")

    with faq_tab:
        faq = draft.meta.get("faq") or []
        if faq:
            for item in faq:
                st.markdown(f"**{item.get('q', '')}**")
                st.caption(item.get("a", ""))
        else:
            st.caption("No FAQ came back — that's a miss. Rewrite, or add one by hand in "
                       "the article body.")
        st.markdown("**Sources cited**")
        sources = draft.meta.get("sources") or []
        if sources:
            for s in sources:
                st.markdown(f"- [{s.get('claim', s['url'])}]({s['url']})")
        else:
            st.caption("No sources cited. A sourced figure is the single biggest lift for "
                       "being quoted by AI engines — worth a rerun once research works.")

    _images(run)
    _publish(site, run, rows)


def _images(run: dict) -> None:
    st.divider()
    c.section("4 · Images", image_api.status())

    if st.button("🖼️ Make the images", key="content_images"):
        edited = _edited_draft(run)
        with st.spinner("Generating…" if image_api.live() else "Writing image briefs…"):
            run["images"] = agent.make_images(edited, agent.run_folder(edited))
        st.session_state[RUN] = run

    for item in run.get("images") or []:
        with st.container(border=True):
            if item["brief"]:
                st.markdown(f"**Image brief** — `{item['path']}`")
                st.caption(f"Alt text: {item['alt']}")
                with st.expander("The prompt to hand your image tool"):
                    st.code(item["prompt"], language="text")
            else:
                st.image(item["path"], caption=item["alt"], width="stretch")
                st.caption(("Featured image. " if item["featured"] else "") + item["detail"])

    if not run.get("images"):
        st.caption("No images yet. They're optional — the draft can be filed without them, "
                   "and with no image API you get briefs rather than a blocked run.")


def _publish(site, run: dict, rows: list) -> None:
    st.divider()
    c.section("5 · File it as a WordPress draft",
              "Always a draft. Nothing on this page can publish a live post.")

    wp = config.wp_credentials(site)
    if not (wp["username"] and wp["app_password"]):
        st.warning(f"No WordPress application password saved for {site.label}, so the "
                   "draft can't be filed yet. The run is still saved to `outputs/`.",
                   icon="🔑")
        c.nav_button("Add WordPress credentials", "Settings", key="content_wp_settings")

    problems = agent.blocking(rows)
    override = False
    if problems:
        st.error("Fix these before filing it: "
                 + "; ".join(p["name"] for p in problems)
                 + ". Edit the text above, or rerun the writer.", icon="🚫")
        override = st.checkbox("I've read the draft and want to file it anyway",
                               key="content_override",
                               help="Your call — the draft stays unpublished either way.")

    can_file = bool(wp["username"] and wp["app_password"]) and (not problems or override)

    cols = st.columns(2)
    if cols[0].button("📥 Create the WordPress draft", type="primary",
                      key="content_publish", disabled=not can_file):
        draft = _edited_draft(run)
        with st.spinner("Uploading images and creating the draft…"):
            result = agent.publish_draft(site, draft, run.get("images"))
        run["result"] = result
        run["folder"] = str(agent.save_run(site, draft, run["research"],
                                           run.get("images"), result.url if result.ok else ""))
        st.session_state[RUN] = run

    if cols[1].button("💾 Save to outputs/ only", key="content_save",
                      help="Writes article.md, meta.json, the research brief and the "
                           "images to a folder you can reuse or publish by hand."):
        draft = _edited_draft(run)
        run["folder"] = str(agent.save_run(site, draft, run["research"], run.get("images")))
        st.session_state[RUN] = run
        st.success(f"Saved to `{run['folder']}`.", icon="💾")

    result = run.get("result")
    if result:
        if result.ok:
            st.success(f"**{result.platform}** — {result.detail}", icon="✅")
            if result.url:
                st.markdown(f"[Open the draft in WordPress]({result.url})")
        else:
            st.error(f"**{result.platform}** — {result.detail}", icon="⚠️")
    if run.get("folder"):
        st.caption(f"Run saved to `{run['folder']}` — article.md, meta.json, the research "
                   "brief and any images.")


def _edited_draft(run: dict):
    """Rebuild the draft from the boxes, so edits are what gets filed."""
    draft = run["draft"]
    meta = dict(draft.meta)
    meta.update({
        "title": st.session_state.get("content_title", draft.title),
        "meta_title": st.session_state.get("content_meta_title", meta.get("meta_title", "")),
        "meta_description": st.session_state.get("content_meta_desc",
                                                 meta.get("meta_description", "")),
        "slug": agent.slugify(st.session_state.get("content_slug", meta.get("slug", "")),
                              words=8),
        "primary_keyword": st.session_state.get("content_kw", meta.get("primary_keyword", "")),
        "tags": [t.strip() for t in st.session_state.get(
            "content_tags", ", ".join(meta.get("tags", []))).split(",") if t.strip()],
        "categories": [t.strip() for t in st.session_state.get(
            "content_cats", ", ".join(meta.get("categories", []))).split(",") if t.strip()],
    })
    return agent.Draft(
        topic=draft.topic,
        title=meta["title"],
        body_markdown=st.session_state.get("content_body", draft.body_markdown),
        meta=meta,
        image_specs=draft.image_specs,
        detail=draft.detail,
    )


# ── Everything else on the page ────────────────────────────────────────────
def _saved_runs() -> None:
    runs = agent.recent_runs()
    c.section("Recent runs", "Every article this page has written, on disk. The folder is "
                             "the record — the draft in WordPress is just a copy.")
    if not runs:
        st.caption("Nothing written yet. Your first run appears here.")
        return
    for run in runs:
        cols = st.columns([3, 1, 2])
        cols[0].markdown(f"**{run.get('title', run.get('topic', 'Untitled'))}**")
        cols[0].caption(f"`{run.get('folder', '')}` · {run.get('sources', 0)} sources")
        cols[1].caption(run.get("created_at", "").replace("T", " "))
        if run.get("wordpress_draft_url"):
            cols[2].markdown(f"[Open the WordPress draft]({run['wordpress_draft_url']})")
        else:
            cols[2].caption("Saved, not filed to WordPress.")


def _quality_path() -> None:
    c.section("The quality path — when a piece really has to rank",
              "Same rules, more depth: these skills research competitors, learn your "
              "voice and do keyword work before writing. Run them from Claude Code in "
              "this folder; they read the same .env the Settings page writes.")
    with st.expander("The seven content skills"):
        st.markdown("Ask Claude Code: **“run the content agent on <your topic>”**")
        for name, what in SKILLS:
            st.markdown(f"- `{name}` — {what}")


def _readiness(site: config.Site) -> None:
    c.section("Readiness for this site", "What the content path has, and what it's missing.")
    c.status_rows(_readiness_rows(site))
    c.nav_button("Open Settings", "Settings", key="content_settings")


def _readiness_rows(site: config.Site) -> list:
    rows = []
    wp = config.wp_credentials(site)
    ready = bool(wp["username"] and wp["app_password"])
    rows.append({
        "name": "WordPress drafts", "state": "ok" if ready else "warn",
        "label": "ready" if ready else "needs a password",
        "detail": (f"Drafts go to {wp['url']} as {wp['username']}, always as a draft."
                   if ready else
                   f"Add a username + application password for {site.label} in Settings."),
    })

    has_model = config.is_set("CONTENT_MODEL") and config.is_set("OPENROUTER_API_KEY")
    rows.append({
        "name": "Writing model", "state": "ok" if has_model else "warn",
        "label": "ready" if has_model else "not set",
        "detail": (f"Using {config.get('CONTENT_MODEL')} — use your strongest model here."
                   if has_model else
                   "Set an OpenRouter key and a Content model in Settings."),
    })

    gaps = search.missing()
    rows.append({
        "name": "Web research", "state": "warn" if gaps else "ok",
        "label": "needs a key" if gaps else search.provider(),
        "detail": (f"{search.PROVIDERS[search.provider()]} — still missing: "
                   f"{', '.join(gaps)}." if gaps else
                   f"Research runs through {search.PROVIDERS[search.provider()]}. Without "
                   "it the agent still writes, but with no statistics at all."),
    })

    rows.append({
        "name": "Images", "state": "ok" if image_api.live() else "idle",
        "label": image_api.provider(),
        "detail": image_api.status(),
    })

    rows.append({
        "name": "Keyword engine", "state": "ok" if kw.enabled() else "idle",
        "label": "on" if kw.enabled() else "off",
        "detail": kw.status(),
    })
    return rows
