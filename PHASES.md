# PHASES.md — the build roadmap

Do these in order. One phase per work session. Before each: read `PROGRESS.md`, then
the existing code you'll touch. After each: update `PROGRESS.md`.

Each phase lists: **Goal**, **Read first**, **Build**, **Done when** (acceptance).

---

## Phase 1 — Foundation & Analysis agent  ·  *mostly built*
**Goal:** Repo + config + Search Console/GA4 connectors + page classifier + the four
analysis views (Fix Plan, Indexing, Performance, Audience), working on seed now and
live once APIs connect.
**Read first:** `app.py`, all of `core/`.
**Build (remaining):**
- A basic **Settings** entry so sites + credential paths are set from the UI, not by
  hand-editing `.env` (full settings UI comes in Phase 2).
- Verify live GSC (URL Inspection + Search Analytics) and GA4 against a real property.
**Done when:** `streamlit run app.py` shows the Fix Plan populated from seed; with creds,
"Refresh live data" replaces seed with live coverage.

## Phase 2 — Clean UI shell & Settings
**Goal:** Turn the tabbed prototype into a neat, self-explanatory dashboard.
**Read first:** `app.py`, `core/config.py`, `.streamlit/config.toml`.
**Build:**
- Sidebar navigation mirroring the tree: **Overview · Analysis · Content · Backlinks · Settings**.
- Reusable UI helpers in `ui/` (section header, metric row, status badge, empty state).
- **Settings page** managing, with plain-language labels + helper text: sites (GSC property,
  sitemap, GA4 id), per-agent model pickers (Analysis / Content / Backlink), and all API
  keys (OpenRouter, image, keyword, WordPress app passwords, optional email/SMTP).
- Apply the theme in `.streamlit/config.toml`.
**Done when:** every feature is reachable from the sidebar and every option has a label +
helper; Settings reads/writes the `.env`-backed config; model-per-agent is selectable.

## Phase 3 — Backlink agent · Lane A (auto-publish)  ·  *user's main target*
**Goal:** Rank winner pages from GSC, draft platform-tailored articles, auto-publish to
platforms the user owns, log everything to a tracker.
**Read first:** `PROGRESS.md`, `core/gsc.py`, the user's existing `daily_backlink_job.py`
(port its dev.to / Blogger / WordPress publisher functions into `agents/backlink.py` +
a small `publishers/` module — reuse, don't reinvent).
**Build:** winner-ranking from Search Analytics (impressions/position); OpenRouter drafting
(`BACKLINK_MODEL`); publishers; a `data/`-backed tracker; a Backlinks UI tab with a
per-page "Auto-publish" action.
**Done when:** pick a winner page → generate → publish to a test platform → see it logged.

## Phase 4 — Backlink agent · Lane B (guest outreach)
**Goal:** The safe, human-gated guest-post pipeline.
**Read first:** `PROGRESS.md`, `agents/backlink.py`.
**Build:** prospecting (`"write for us" + niche` via search), quality/relevance scoring,
tailored guest-article + personalized pitch drafting, an outreach tracker
(prospected → pitched → accepted → live), optional email send (SMTP or API) behind an
explicit approval step.
**Done when:** for a target page you get a scored prospect list + drafts; the tracker moves
through stages; nothing sends without a human click; no auto-posting to third-party sites.

## Phase 5 — Content + SEO agent (volume path)
**Goal:** In-dashboard fast draft path (the quality path already exists as the skills).
**Read first:** `PROGRESS.md`, `.claude/skills/blog-writer-seo-aeo-geo/SKILL.md`,
`.claude/skills/wordpress-publisher/assets/publish.py`.
**Build:** topic → web research → SEO/AEO/GEO article via OpenRouter (`CONTENT_MODEL`) →
image via the image adapter → WordPress **draft**; a Content UI tab.
**Done when:** a topic produces a WordPress draft with meta + image (or image brief).

## Phase 6 — Opportunity Finder + optional Keyword engine
**Goal:** The point-2 fallback and the optional keyword branch.
**Read first:** `PROGRESS.md`, `.claude/skills/competitor-site-scraper/SKILL.md`,
`.claude/skills/keyword-researcher/SKILL.md`.
**Build:** competitor scan + content-gap finder; GSC-query keyword research (striking-distance
terms) with the pluggable keyword adapter; feed topics/keywords to Content and Backlink tabs.
Keep it toggleable (optional).
**Done when:** with no analytics you still get topic/keyword suggestions from competitors +
GSC; the keyword branch can be turned on/off.

## Phase 7 — Orchestration & polish
**Goal:** Dashboard-as-conductor ties the three agents into one flow; final polish.
**Read first:** `PROGRESS.md`, `app.py`, everything in `agents/` and `ui/`.
**Build:** an Overview page that runs analysis → shows recommendations → launches
backlink/content actions; consistency pass on UI; update `README.md`.
**Done when:** from Overview you can go data → recommendation → action end to end.

## Phase 8 — UX + completeness pass  ·  *the core journey, made obvious*
**Goal:** Make the tool's actual purpose — connect GA4 + Search Console → see which pages
and keywords are ranking → one click to build backlinks or write an article for *that*
page — visible and reachable without hunting. Audit first, then fix.
**Read first:** `PROGRESS.md`, `app.py`, all of `ui/`, `agents/analysis.py`.
**Build:**
- **Not-connected state:** a banner on every page saying the numbers are SAMPLE data,
  with a prominent "Connect Search Console + GA4" button that deep-links into Settings.
  Verify the seed really is replaced by live data on refresh.
- **Overview as the spine:** landing page, indexing health, a ranked list of the pages
  that actually earn impressions/clicks/position, striking-distance queries, and on
  every row the three one-click actions — Build backlinks · Write article · Fix — each
  pre-filling the agent that does the job.
- **A three-step onboarding strip:** 1 Connect data · 2 Review what's ranking ·
  3 Generate backlinks + content, tracking real state rather than a tutorial flag.
- **Polish everywhere:** plain-language labels, a one-line helper under every control,
  a glossary for the jargon each screen uses, consistent section headers / metric rows /
  status badges, and a guided empty state in place of every bare table.
**Done when:** a first-time user lands on the Overview, is told in one line that the
numbers are samples and how to fix that, and — once connected — can see their best pages
ranked and launch a backlink run or an article for one of them in a single click.

