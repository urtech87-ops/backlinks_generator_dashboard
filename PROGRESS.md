# PROGRESS.md — living status (Claude Code updates this after every phase)

> **How to use:** If a chat gets long/expensive, start a new conversation and paste
> this file (or add it to a Project). It carries enough context to resume with zero
> history. Claude Code: after finishing a phase, update the checklist, the "Done /
> Next up" lines, and the timestamp below.

**Last updated:** 2026-09-21 · **Current phase:** Phase 18 done — **"Write article"
now scopes Content's suggestions + keyword picker to the page that was clicked, and
the sidebar's selected site survives a browser reload**
**Overall:** ▓▓▓▓▓▓▓▓▓▓ 100% (all nine roadmap phases shipped, eleven scoped additions —
Phase 9, 10, 11, Phase 11-fix, Phase 11-fix-2, Phase 13, Phase 14, Phase 15, Phase 16,
Phase 17 and Phase 18 below — on top of Phase 12's UX redesign. Phase 7 made Overview the conductor; Phase 8 made it the *spine*; Phase 11 put a
plain-English verdict on every ranked page; Phase 11-fix made that verdict honest when the
underlying check is missing or fails, instead of silently lying; Phase 11-fix-2 made the
data BEHIND that verdict honest too, by auto-loading live coverage the first time a
connected session read it — which Phase 13 then reversed, because "the first time it's
read" turned out to mean "every single rerun", and Streamlit reruns the whole script on
every click. Phase 12 is the layer a non-SEO person actually needs: building a backlink,
running guest outreach and writing an article are step-by-step wizards with a "Step X of N"
strip, one job per screen, and Next disabled until that step has actually produced
something to carry forward. What's left is not building — it's running the thing against
real keys; see **First real run** below.)

---

## System in one paragraph

Streamlit dashboard = conductor for two sites (toolsvenue.com, toolacademy.com). The
**Overview** page is the conductor in the literal sense: it runs the Analysis agent and
launches every other agent's work from the pages that come back. Three agents:
**Analysis** (`agents/analysis.py`, OpenRouter cheap for its optional written briefing)
reads Search Console + GA4, triages not-indexed pages into Plumbing / Content /
Crawl-budget, ranks winners, and turns all of it into an ordered to-do list; **Content + SEO** (strongest model)
writes SEO/AEO/GEO articles → WordPress drafts, on two paths: the volume path in the
Content page, and the deeper quality path in `.claude/skills/`;
**Backlink** (OpenRouter, cheap — the MAIN TARGET) runs two lanes: auto-publish to owned
platforms, and human-gated guest outreach. Growth really comes from fixing indexing +
quality content; backlinks are the visible target, not the engine.

## Key decisions / context (so a fresh chat has the "why")

- Root cause of past zero-traffic: ~half of toolsvenue's pages were not indexed
  (broken URLs, thin content Google rejected, crawl-budget). Backlinks to unindexed
  pages do nothing. Fix indexing first; link only to healthy pages.
- Backlinks: auto-publish only to OWNED platforms (dev.to, Blogger, their WP). Guest
  posting is human-gated by design — scaled auto guest-posting is a Google penalty.
- Content: quality over volume. Answer-first, real stats+sources, sourced quotes,
  question-shaped headings, FAQ, short clean slugs. No fabricated stats/volumes.
- Keyword research: GSC query data first (striking-distance terms), free autocomplete,
  optional pluggable paid API. Keyword branch is OPTIONAL — `KEYWORD_ENGINE=off` and every
  page degrades to "no keyword data", which is a stated state, not a failure.
- Model routing via `.env`: cheap for Analysis/Backlink, strongest for Content.
- WordPress publishing is ALWAYS draft.
- **Settings now writes `.env` itself** (`core/config.save()`): it preserves comments and
  ordering, chmods the file to 600, and reloads live — no restart, no hand-editing.
- **Blank = unset.** An empty value falls back to the built-in default, so clearing a
  box in Settings can never leave the app with an empty property/sitemap URL.
- **Per-site keys.** Everything site-specific is prefixed (`TV_*`, `TA_*`), including
  WordPress credentials. The single legacy `WP_*` keys still work as a fallback and are
  what the standalone `wordpress-publisher` skill reads outside the dashboard.
- **`publishers/` is where the guardrail lives.** That registry is the complete list of
  publish destinations and every entry is a platform the user owns. There is deliberately
  no third-party publisher — `agents.backlink.publish()` refuses anything not in it, so
  Lane A cannot post to someone else's site even by mistake.
- **Link targets are gated on indexing.** Only `Healthy` (compound) and `Crawl budget`
  (rescue) pages are offered as targets. Broken and quality-rejected pages are excluded,
  because a link to those is wasted — the same honest framing as the Fix Plan.
- **Lane B is a funnel with a person standing in it.** The agent searches, scores and
  writes; every state change is a click. The only outbound action in the whole lane is
  one email, sent one at a time, after an explicit "I have read this pitch" tick — and
  `publishers/PLATFORMS` still has no third-party entry, so there is no code path that
  posts to someone else's site.
- **Prospect scores are evidence, not authority.** There is no DA/DR anywhere: a score
  is built only from what's on the page (your niche words, real editorial guidelines, a
  contact address, an ordinary domain) and every point is listed back to you in plain
  language. Pages that advertise paid placement are forced to **skip** — buying links is
  a guidelines violation, not a low-quality option.
- **Declines are kept.** The board tracks declines on purpose: they're what stops you
  pitching the same editor twice.
- **No invented performance numbers.** With Search Console connected, targets rank on
  real impressions + average position. Without it, the page says so and shows the
  eligible list *unranked* rather than inventing a score.
- **A cited source has to be a source the run actually found.** The content agent hands
  the model a numbered research list and permits figures only from those snippets; then
  `check()` compares every URL in `meta.sources` back against that list and marks any
  stranger red. It's the one check that can catch a hallucinated citation, which is the
  failure mode that would do real damage here.
- **The volume path and the quality path share one standard.** The writer skill's rules
  (answer-first opening, question-shaped headings, FAQ, short slug, meta lengths,
  internal links) are the checks the dashboard runs, so the fast path can't quietly drift
  into thin content — the thing that got these pages de-indexed in the first place.
- **The image adapter is loaded, not copied.** `core/images.py` imports the skill's
  `assets/image_adapter.py` by path, so when the user wires a real provider there, the
  dashboard picks it up with no second edit.

## Phase checklist

- [x] **Phase 1 — Foundation & Analysis** — `core/` (config, gsc, ga4, classifier, seed)
      + the four analysis views, seeded with the real 16-Aug Search Console state
      (30 Plumbing / 11 Content / 10 Crawl-budget). Settings moved into the UI, and a
      one-click **connection test** now verifies GSC (properties → Search Analytics →
      URL Inspection) and GA4 step by step.
      *Note:* the test ships and is wired up, but it has never been run against the real
      properties from here — there are no credentials in this environment. Run
      **Settings → Test connections** once the service-account file is in place; it names
      the exact failing step if anything is off.
- [x] **Phase 2 — Clean UI shell & Settings** — sidebar nav (Overview · Analysis ·
      Content · Backlinks · Settings), reusable helpers in `ui/`, a full Settings page
      that reads/writes `.env`, per-agent model pickers fed by OpenRouter's live
      catalogue, and the theme applied.
- [x] **Phase 3 — Backlink agent · Lane A (auto-publish)** — winner ranking from Search
      Console, platform-tailored drafting with `BACKLINK_MODEL`, three publishers for
      platforms the user owns (dev.to, Blogger, own WordPress), and a CSV tracker. The
      Backlinks page is now a four-step flow: pick the target page → pick the platforms →
      generate → read and publish.
      *Note:* `daily_backlink_job.py` never reached the repo, so the publishers were
      written from each platform's API docs rather than ported. The Blogger
      refresh-token exchange is the standard Google flow and is isolated in
      `publishers/blogger.py → _access_token()` — if the original job script did anything
      different, replace **only** that function. Everything is verified against mocked
      APIs; none of the three has been run against a real account from here, because
      there are no platform keys in this environment.
- [x] **Phase 4 — Backlink agent · Lane B (guest outreach)** — prospecting from search
      footprints (`"write for us" + niche`), a transparent relevance/quality score per
      prospect, a personalised pitch + a tailored guest article per site, and an outreach
      board running prospected → pitched → accepted → declined → live in the SAME
      `data/backlinks.csv` Lane A writes to (new `lane` column). Sending email is
      optional and sits behind an approval tick-box; with no SMTP you copy the pitch.
      *Note:* this environment's proxy blocks general outbound HTTPS, so neither the live
      search nor the page reader could be run against real sites from here. What *was*
      verified: the failure path (a blocked DuckDuckGo returns a plain "throttled — add a
      key" message instead of crashing), the tracker's migration + stage folding, and the
      whole Lane B UI driven end to end with Streamlit's AppTest against stubbed
      prospects. First real run: **Settings → Prospecting → Test search**.
- [x] **Phase 5 — Content + SEO agent (volume path)** — topic → web research → an
      SEO/AEO/GEO article written by `CONTENT_MODEL` → images (or briefs) → a WordPress
      **draft**, all inside the Content page. The writer skill's rules are enforced in
      code (`agents/content.check()`), not just asked for in the prompt, and every cited
      source URL is traced back to research this run actually found — an invented URL is
      flagged red and blocks the draft until you tick past it.
      *Note:* this environment's proxy blocks general outbound HTTPS, so neither the real
      search nor a real OpenRouter call could be run from here. What *was* verified, with
      stubs: the full page driven end to end by Streamlit's AppTest (topic → draft →
      edits carried into the post → images → WordPress draft → saved run), the
      fabricated-source and unsourced-figure checks, the hard-check gate disabling the
      publish button, `status: draft` in the posted payload, image *briefs* never being
      uploaded as media, and Lane A's payload being unchanged by the new Article fields.
- [x] **Phase 6 — Opportunity Finder + optional Keyword engine** — a new **Opportunities**
      page (sidebar, between Analysis and Content) with two tabs. The Finder scans
      competitors (their sitemap + a `site:` search, robots-respecting, capped at 3 sites /
      4 pages), your own coverage and your Search Console queries, and returns a ranked list
      of four kinds of opportunity — striking distance, competitor gap, tool with no
      article, rejected-on-quality rewrite — each with the evidence behind it. Every card
      hands off: **Write this** fills the Content page's topic/keyword/direction, **Target
      with links** preselects the page in Lane A's target picker. The keyword engine
      (`core/keywords.py`) is GSC-first, expands with the skill's free autocomplete adapter,
      and has a paid slot that stays empty by default. It's switchable in Settings.
      *Note:* this environment's proxy blocks general outbound HTTPS, so no competitor site,
      no live Google autocomplete and no real Search Console property was reached from here.
      What *was* verified, with stubs: the bands (position 2 → winning, 12 → striking, 44 →
      deep, 5 impressions → not striking), the "never invent a volume" rule end to end, the
      whole page driven by Streamlit's AppTest (scan → cards → Write this → Content with the
      topic filled → Use a keyword → Target with links → Backlinks with the page
      preselected and its keywords listed), the engine switched **off** across all four
      pages, robots.txt Disallow being honoured, and a dead search provider leaving a note
      instead of an exception. First real run: **Opportunities → Scan for opportunities**.
- [x] **Phase 7 — Orchestration & polish** — a new **`agents/analysis.py`** (the triage
      everything is conducted from) and an Overview page that is now the conductor:
      **Run the analysis** reads coverage + Search Console performance + your queries in
      one pass, and sorts every page into one of five things it needs — 🔴 fix the URL,
      🟠 rewrite it, 🗑️ delete/noindex it, 🟢 build links to it, 🎯 strengthen it for a
      keyword. The ordered to-do list opens onto the actual pages behind each step, each
      with the button that does the job: fix → Analysis with the Fix Plan filtered to that
      bucket and the page called out, rewrite/strengthen → Content with topic, keyword and
      direction filled in, link → Backlinks with the target preselected. Plus an optional
      plain-English briefing written by `ANALYSIS_MODEL` from the measured numbers only —
      the one place that (previously unused) setting is now spent. Consistency pass: one
      `c.status_rows()` readiness strip on every page, `metric_row` everywhere, the health
      figures computed once in the agent so no two pages can disagree, a bucket filter on
      the Fix Plan with per-bucket hand-offs, "filled in from …" banners on the receiving
      pages, singular/plural copy, the guardrails listed in the sidebar, and the unused
      `coming_soon` placeholder deleted. README rewritten for the finished system.
      *Note:* verified with Streamlit's AppTest — all six pages render for both sites, the
      whole conductor chain (run → fix / rewrite / link hand-off → the destination page
      with the boxes filled) drives end to end, the live path with stubbed Search Console
      figures produces striking-distance recommendations and fetches the `page` dimension
      exactly **once** per run, the briefing sees only the fact block, and with no
      credentials that fact block says "Performance figures: NOT AVAILABLE — do not
      estimate traffic". Still not run against real Google/OpenRouter credentials from
      here; this environment has none.

- [x] **Phase 8 — UX + completeness pass** — an audit of the core journey (connect →
      see what ranks → one click to links or an article) followed by the fixes it found.
      **Overview is now the landing page and the spine:** a three-step onboarding strip
      (connect · review · generate) that reads real state rather than a tutorial flag,
      indexing health, then **🏆 Your pages, ranked** — every page ordered by the
      impressions it actually earns, each row carrying **🔗 Build backlinks · ✍️ Write
      article · 🔧 Fix**, and each button disabled with the reason printed when it would
      be wasted (no backlink offered for a page Google can't reach). Striking-distance
      queries got their own section with the same hand-offs. **Not-connected state:** a
      banner at the top of every page saying the numbers are SAMPLE data, with a
      **Connect Search Console + GA4** button that deep-links into Settings → Google APIs
      (Settings' tabs became a radio section picker so a deep link can target one).
      **GA4 stopped being conflated with Search Console** — `config.ga4_ready(site)` needs
      the key file *and* a property ID, and it has its own status row everywhere.
      **Landing no longer needs a button press:** with credentials, Overview fetches its
      figures once on first paint and keeps them, which was the worst trap in Phase 7.
      Plus a polish pass: a `jargon_note()` glossary on every screen that uses SEO words,
      plain-language column names in place of Search Console's raw ones, per-metric
      tooltips, guided empty states, and "seed" renamed to "sample" wherever a user can
      see it.
      *Note:* this phase ships **`tests/test_phase8_ux.py`** — 16 AppTest cases, the
      repo's first committed tests (`pip install -r requirements-dev.txt && pytest -q`).
      They stub `core.gsc`'s three network functions, which is still the only way to
      exercise the live path from here: this environment has never had a Google key, and
      inventing one would be the exact sin the app refuses to commit. What they prove:
      Overview is the landing page, all six pages render, every non-Settings page says
      SAMPLE and offers the connect button, the connect button lands on Google APIs,
      **Refresh live data really does replace the sample snapshot with live coverage**,
      live performance appears without pressing Run, GA4 is not reported as connected
      without a property ID, every ranked row offers all three actions with the wasted
      ones disabled, and each of the three hand-offs arrives with the right page filled
      in. Also fixed on the way past: the Backlinks eligible-pages table put `""` in a
      numeric column, which made Arrow fail to serialise it.

- [x] **Phase 9 — Third site + new-site ranking + an active tracker** — a small, scoped
      addition, not a new phase of build.
      **ToolsHall (toolshall.com)** is now a third configured site: a `SITE_DEFAULTS`
      entry in `core/config.py` and matching `TS_*` keys in `.env.example`, in exactly
      the `TV_*`/`TA_*` pattern. ToolAcademy is untouched — all three sites coexist, and
      Settings' `for site in config.SITES` loops picked the third one up with no other
      code change.
      **`agents/backlink.rank_targets()` gained a new-site fallback.** A site with
      coverage rows but no Search Console performance (a brand-new property, most
      likely) used to rank its eligible pages by a score that was flat within each
      bucket, so the real order was alphabetical — arbitrary, not honest. It now sorts
      by structural importance instead (`_importance()`): homepage first, then
      shallower URLs, then tool pages ahead of articles at the same depth (the same
      tool/article split `agents/opportunity.own_coverage()` uses — duplicated rather
      than imported, since opportunity → outreach → backlink is already the import
      chain and importing back would be circular). Sites *with* performance data are
      untouched — same striking-distance score as before. A site with zero coverage
      rows still returns an empty list; Phase 9 does not invent targets for a page
      Google hasn't discovered.
      **The tracker is now active, not just a log.** `core/tracker.link_history()`
      reads how many non-failed attempts already point at a page and when the most
      recent one was; the Backlinks page's Lane A target picker shows "🔗 Already
      linked N times — most recent DATE" right on the selected row when that's true —
      the same spirit as Lane B's "you've already pitched this domain" notice.
      Informational only; it has never blocked a re-run and doesn't start now.
      *Note:* verified with a stubbed `core.gsc` (this environment still has no Google
      key) against a synthetic coverage frame: the new-site fallback orders homepage →
      shallow tool page → deeper article → crawl-budget page correctly, the live
      metrics path produces the exact same ordering as before Phase 9, a zero-coverage
      site still returns `[]`, and `link_history()` counts a live and a draft entry
      but skips a failed one for the same URL.

- [x] **Phase 10 — Two more owned publishers + a manual community tracker** — another
      small, scoped addition.
      **`publishers/hashnode.py` and `publishers/medium.py`** join `PLATFORMS` in the
      exact pattern of the other three: a `missing()` readiness check naming the exact
      settings still empty, `publish()`, and a registry entry with its own drafting
      style. Hashnode is GraphQL (`publishPost` live, `createDraft` for `as_draft`),
      needs `HASHNODE_TOKEN` + `HASHNODE_PUBLICATION_ID`. Medium needs one
      `MEDIUM_TOKEN`, looks up the author id from `/v1/me`, and uses Medium's own
      `publishStatus: draft` for `as_draft` — its docstring and its `PublishResult`
      detail both say plainly that Medium's API has no edit/delete endpoint, so a live
      post can only be fixed on Medium's own site afterward. Both sets of keys are in
      `.env.example` and `core/settings.py`'s **Owned backlink platforms** group, so
      Settings renders them with no UI code of their own. WordPress stays draft-only;
      `publishers.PLATFORMS` still has no third-party entry.
      **`core/tracker.py` gained a third lane, `"community"`**, for manual
      community/directory submissions (Reddit, Hacker News, Product Hunt,
      AlternativeTo, an "awesome" list). It reuses Lane B's exact shape — an
      append-only log (`log_community()`) folded into a current-stage-per-submission
      board (`community_board()` / `community_summary()`), stages `planned →
      submitted → live`. `log()` gained an optional `logged_at` override so a
      submission can be dated when it actually happened, not just "now". Nothing in
      this lane calls an API or reads the network — every row exists because a human
      filled in a form and pressed Save, the same honesty rule as Lane B's send step.
      **Backlinks page gained its own "🌐 Community & directory submissions" section**,
      below both lanes (not nested in either tab): a form (target page — with an
      optional picker from your own coverage pages — platform name from a short
      preset list or free text, date, status, resulting URL, a note), a metric row,
      the folded board, and an update-one-row flow mirroring Lane B's board step,
      plus a CSV export.
      *Note:* verified with the repo's own `core.tracker` (no stubbing needed — this
      lane touches no network): `log_community()` correctly folds planned → submitted
      for the same (platform, page) pair into one board row while a different page
      stays a separate row, `community_summary()` counts land in the right stage, and
      `pytest -q` (16/16, unchanged) plus a Streamlit `AppTest` pass driving the whole
      form — fill in target/platform/status/note, press **Save submission**, see the
      success message and the new row — with no exceptions. Not run against a real
      Hashnode or Medium account: this environment has no platform keys, same as
      dev.to and Blogger before it.

- [x] **Phase 14 — Real internal links + the site's own content structure** — a scoped
      change to the volume path's writing prompt, `agents/content.py` +
      `ui/views/content.py`. Two things, both about NEW article output only — nothing
      here touches or rewrites a live page.
      **1 · Internal links from the live sitemap, ranked by relevance.**
      `internal_link_options()` already only offered `Healthy` pages from `coverage_df`
      — which is itself built from `config.Site.sitemap_url` (read live by
      `gsc.discover_urls()`) cross-checked against live Search Console indexing via
      `ui.data.refresh_live()` — so the sitemap-plus-indexing gate was already correct.
      What it didn't do was rank them: it returned the first N healthy pages in sitemap
      order. It now takes `topic`/`keyword`, scores every candidate page by keyword
      overlap between the topic and the page's own URL/slug (new `_topic_words()` /
      `_slug_words()`, a small stopword list, no external NLP dependency), and sorts
      most-relevant-first. The Content page's Step 1 multiselect now defaults to the
      **top 4 by relevance** instead of the first 4 in sitemap order, and Step 2 passes
      the same topic/keyword when it rebuilds the list to resolve the picked URLs — no
      new network call anywhere; this still reads only the cache Phase 13 gated behind
      "Refresh live data". The writer's prompt (`_internal_block()`) now hands the model
      the top 12 ranked candidates, says plainly they're "ranked most relevant first",
      and asks for 2 to 4 of them in the article's closing section (previously "two or
      three" with no ranking).
      **2 · Match the site's own content structure.** `_prompt()`'s "HOW TO WRITE IT"
      section was rewritten from a flat numbered list into the six-part shape a real
      tool page uses: **intro → what it does → quick reference/how-to steps → when it's
      useful → FAQ → related tools/pages**, with the related-tools section explicitly
      the 2-4 ranked internal links from change 1. The prompt calls out the anti-pattern
      by name — a generic "Key Benefits" block repeated with no page-specific
      substance — and tells the model not to write that. The AEO rules from before
      (answer-first opening, question-shaped headings with self-contained answer
      blocks, one worked example, inline-cited sources) are kept, just placed inside
      the new structure rather than replacing it. `check()` and the "Internal links"/
      "Question-shaped headings"/"FAQ" rows are unchanged — the new structure is a
      superset of what they already verify, so a draft that matches it still passes.
      *Note:* no new test file — the change is a prompt/ranking change with no new
      branching a human decision depends on, and the existing suite doesn't stub
      OpenRouter's actual reply content. Verified instead by running
      `internal_link_options()` directly against a synthetic coverage frame: a topic
      about "jpeg" content ranks a `/jpeg-compressor` page above an unrelated
      `/pdf-merger` page, a `Broken`-bucket page is still excluded, and calling it with
      no topic still returns the same "just the healthy pages" list as before this
      phase (so the wizard's no-topic-yet caption path is unaffected). `pytest -q` —
      67/67, unchanged (this environment still has no Google/OpenRouter keys, so the
      full write→check round-trip against a real model reply is still unverified from
      here, same limitation every phase has noted).

## Done so far
- Repo scaffold, `CLAUDE.md`, `PHASES.md`, this file.
- `core/` package: `config` (now readable *and* writable), `settings` (the option
  schema every Settings control is generated from), `gsc` + `ga4` (now with
  `check_connection()`), `openrouter` (live model list + key test), `classifier`, `seed`.
- `ui/` package: `components` (section headers, metric rows, status badges, empty
  states, check lists, nav buttons), `data` (one shared coverage loader + health
  summary), and `views/` — one module per sidebar page.
- `app.py` is now a thin shell: sidebar (page, site, dates, refresh) → page module.
- Overview page: indexing health, an ordered "what to do next" list generated from the
  bucket counts, and a system-status strip showing what's connected.
- The Content page is now the real volume path (below), sitting alongside the quality
  path it links out to. Both Backlinks lanes are real too.
- Six content skills in `.claude/skills/` (orchestrator, brand + competitor scrapers,
  keyword researcher, SEO/AEO/GEO writer, image generator, WordPress publisher) with
  pluggable image + keyword adapters (dummy defaults).
- **`publishers/` package** — `base` (the shared `Article` / `PublishResult`, markdown→HTML,
  tag cleaning), `devto`, `blogger` (refresh-token OAuth + a `check_auth()` the UI exposes
  as a test button), `wordpress` (ported from the publisher skill; status is hard-coded to
  `draft`), and `__init__` holding the `PLATFORMS` registry every caller loops over.
- **`agents/backlink.py`** — `rank_targets()` (impressions + striking-distance scoring,
  with a written reason per page), `page_facts()` (reads the target page's own title and
  meta description so the article is about what the page actually is, not its slug),
  `draft_article()` (JSON-mode prompt that bans invented stats and asks for exactly one
  contextual link), and `publish()` which dispatches and logs.
- **`core/tracker.py`** — `data/backlinks.csv`, one row per publish attempt including
  failures, with `load()` / `summary()` for the UI and a CSV export.
- **`core/openrouter.chat()`** — the completion call the agents write with; handles 401 /
  402 / 404 with plain-language messages. Phase 5's content agent can reuse it as-is.
- **`agents/outreach.py`** (Lane B) — `find_prospects()` (five "write for us" footprints
  plus your own searches, deduped per domain, own/social/marketplace domains excluded),
  `score()` (relevance + quality out of 50 each, penalties for link sellers, a written
  reason per point), `prospect_from_url()` (score a site you already know),
  `draft_pitch()` + `pitch_checks()` (flags mail-merge and link-request wording), and
  `draft_guest_article()`. It reuses Lane A's `rank_targets`, `page_facts`, `_parse_json`
  and `_SYSTEM` rather than duplicating them; `page_facts()` gained an optional `html=`
  argument so a page fetched for scoring isn't fetched twice.
- **`core/search.py`** — the pluggable prospecting search: `duckduckgo` (default, no key),
  `serper`, `serpapi`, `brave`, plus `check()` behind a Settings test button. Read-only.
- **`core/mailer.py`** — optional SMTP. `send()` is called from exactly one place: the
  approval button. `check()` logs in without sending.
- **`core/tracker.py`** — now two lanes in one file via a `lane` column (an older CSV is
  migrated on first write, so Phase 3's rows survive). `log_guest()` appends one row per
  stage change; `guest_board()` folds that history into the current stage per prospect;
  `guest_summary()` feeds the board's metric row.
- Backlinks page Lane B is live: a readiness strip, the same target picker, prospect
  search + hand-added sites, a scored list with the evidence behind each score, a
  shortlist button, per-prospect pitch and article editors (with the link-count check),
  the approval/send step, and the outreach board with stage controls and a CSV export.
- Backlinks page Lane A is live: platform readiness naming the exact missing settings,
  a ranked target picker, a per-platform draft editor with a link-count check
  (0 links → error, 2+ → "this reads as link-building"), a "save as draft everywhere"
  option for a first run, and the tracker.
- **`agents/content.py`** (Phase 5) — the volume path. `research()` searches through the
  same `core/search.py` adapter Lane B prospects with (own domain excluded — your pages
  are internal links, not sources); `write()` makes ONE `CONTENT_MODEL` call that returns
  the article *and* its meta.json (title, meta title/description, slug, keyword, tags,
  categories, FAQ, schema, sources, internal links, image prompts); `check()` applies the
  writer skill's rules to what came back; `make_images()`, `save_run()` and
  `publish_draft()` finish the run. It reuses `backlink._parse_json` and
  `backlink.page_facts` rather than re-solving them.
- **No-research is a stated state, not a silent one.** If search fails, the prompt forbids
  every statistic and the page says the piece is qualitative and any figure is unvalidated.
- **`core/images.py`** — loads the *skill's* `image_adapter.py` by path and calls its
  `generate_image()`, refreshing its provider/key/model from Settings before each call
  (it reads them at import time, which would otherwise go stale in a long-running app).
  No image API → briefs, and drafting carries on.
- **`publishers/wordpress.py`** gained the rest of the publisher skill: media upload with
  alt text, featured image, slug and categories. `Article` gained `slug`, `categories` and
  `images`, all optional, so Lane A posts are byte-identical to before. Status is still
  hard-coded to `draft`.
- **Runs are saved to `outputs/<slug>/`** in the orchestrator skill's layout
  (`content/article.md`, `content/meta.json`, `research/research-brief.md`, `images/`,
  `run.json`), so a run is auditable, reusable, and readable by the standalone
  `publish.py`. The folder is git-ignored — it's your content, not the app's.
- Content page is live: readiness strip (WordPress · model · research · images), topic +
  optional keyword + direction, an internal-link picker fed only by *indexed* pages, the
  research summary with its sources, a quality-check panel, editable article/meta/FAQ,
  images (or briefs), "create the WordPress draft" / "save to outputs only", and a list of
  recent runs. A draft failing a hard check can't be filed until you tick past it.

- **`core/keywords.py`** (Phase 6) — the keyword engine, the skill's priority order in code.
  `gsc_keywords()` reads the `query` dimension and bands every term (**Already winning** <4,
  **Striking distance** 4-20 with ≥10 impressions, **Ranking deep** >20, **Unvalidated**);
  `page_map()` ties each query back to the page that ranks for it; `for_page()` is what the
  backlink targeter shows; `brief()` picks a primary the skill's way (striking distance →
  paid volume → autocomplete-confirmed → the topic itself, flagged). Autocomplete and the
  paid slot are *loaded from the skill's own* `assets/keyword_adapter.py` by path — the same
  trick `core/images.py` uses — so wiring a provider there lights up both paths at once.
- **A volume is never invented.** `Keyword.volume` stays `None` unless a paid provider
  returned a number, `volume_label` prints the word "unvalidated" in its place, and a term
  with no impressions and no volume says so on its own card.
- **`agents/opportunity.py`** (Phase 6) — the Finder. `find_competitors()` (top independent
  domains for your niche; your own sites and the social/aggregator list excluded),
  `map_competitor()` (robots.txt for the sitemap it advertises → topics, a `site:` search →
  real titles, and optionally 4 pages read for their question headings, with a delay
  between fetches), `own_coverage()` (your tools, your articles, your rejected pages),
  and four generators merged into one ranked list. It reuses Lane B's `domain_of`, `_fetch`
  and exclusion list, and `gsc.discover_urls` for sitemap walking, rather than re-solving them.
- **A score is a summary of listed reasons, not an authority** — the same rule as Lane B's
  prospect scores. Every opportunity prints the evidence that produced it.
- **Opportunities page** — Finder tab (readiness strip, niche + competitors, the caps
  exposed as controls, ranked cards with evidence/angle/hand-off buttons, what each
  competitor covers, CSV export) and Keywords tab (load your queries, the striking-distance
  table, a brief builder, CSV export). Off, the Keywords tab is an empty state with the
  three steps to switch it on.
- **The three agents now hand off to each other.** Opportunity → Content
  (`content_topic` / `content_keyword` / `content_notes`), Opportunity or keyword →
  Backlinks (`bl_focus_url` preselects Lane A's target, and says so if the page isn't
  link-eligible). Lane A's chosen target now lists the keywords it's closest on, marked 🎯
  for striking distance, from your own Search Console data.
- Content page gained an optional "pick the keyword from real data" expander; Overview's
  to-do list ends with "Decide what to write next" → Opportunities; Settings gained the
  **Keyword engine** switch and a per-site **Competitor sites** box (`TV_COMPETITORS` /
  `TA_COMPETITORS`).

- **`agents/analysis.py`** (Phase 7) — the triage the whole dashboard is conducted from.
  `health()` is now the single implementation of the indexing figures (`ui.data` delegates
  to it, so Overview and Analysis can never quote different numbers); `page_metrics()`
  fetches Search Console performance **once** per run and passes it into
  `backlink.rank_targets(metrics=…)` — the reason that function gained an optional
  `metrics` argument — so one report never queries the same dimension twice;
  `run()` returns a `Report` of ranked `Recommendation`s and the ordered `Step`s Overview
  draws; `briefing()` is the optional written summary.
- **Five things a page can need, and one place that decides which.** FIX / REWRITE /
  PRUNE / LINK / STRENGTHEN, with `KIND_PAGE` and `KIND_CTA` mapping each to the page that
  carries it out — so a hand-off is data, not a hard-coded button.
- **A rejected page that was never an article is pruned, not rewritten.** `/feed/`,
  `/blogs/author/zain/` and category archives come back as 🗑️ *delete or noindex* with
  their own step, and never reach the writer. `topic_from_url()` returning "" is the test,
  which is why the writer is never handed a topic like "blogs/author/zain".
- **Both link steps share a kind, so `Step.bucket` keeps them apart** — "rescue these 10
  uncrawled pages" and "compound these healthy ones" are different lists of pages, and a
  rescue target is amber here exactly as it is in the Backlinks target picker.
- **The briefing can only see measured numbers.** `facts_block()` is the entire input:
  with no Search Console it literally says "Performance figures: NOT AVAILABLE … Do not
  estimate traffic", and the deterministic list stays the authority whether or not you
  ever press the button. It's the only use of `ANALYSIS_MODEL`, which until Phase 7 was a
  setting the app never spent.
- **`c.status_rows()`** is now the one readiness strip: Overview's system status, the
  Content and Opportunities readiness, both Backlinks strips and the content quality
  checks all draw through it, so "ready" / "not set" / "on" / "off" mean the same thing
  everywhere. `coming_soon()` is gone — nothing is coming any more.
- **Every page can say where a hand-off came from.** `content_source` and `bl_focus_from`
  travel with the topic and the target URL, so the receiving page opens with "Filled in
  from the Overview — rewrite the page" rather than mysteriously pre-filled boxes.
- Fix Plan gained a bucket filter (`analysis_bucket`, which Overview sets), a "sent over
  from the Overview" callout for one page (`analysis_focus`), and per-bucket hand-off
  buttons; the sidebar gained a plain list of what the app will never do.

- **Phase 8 · `ui/components.py` gained the three pieces every page now leans on.**
  `connect_banner()` (the SAMPLE-data banner + the one button that fixes it, drawn once
  in `app.py` for every page except Settings), `onboarding_strip()` (the three-step
  spine, states read from real config rather than stored progress), and `jargon_note()`
  with a shared `JARGON` dictionary — so "impressions", "striking distance" and
  "crawl budget" are explained the same way wherever they appear.
- **Phase 8 · `agents/analysis.PageStat` + `ranked_pages()`** — one page as it actually
  performs, and the ranking Overview draws. With Search Console it sorts on real
  impressions; without it, it returns the link-eligible pages in coverage order with
  every row flagged `has_metrics = False`, because there is nothing to rank on and a
  zero would read like a measurement. Each stat knows which actions make sense
  (`can_link`, `needs_fix`, `topic`) and carries the reason when one doesn't, plus the
  striking-distance query its own page ranks for — which is what makes "Write article"
  hand the writer a real search instead of a slug.
- **Phase 8 · `config.ga4_ready(site)`** — GA4 is connected only when the key file *and*
  a property ID exist. Overview, the sidebar, the banner and Settings all read it, so no
  screen can claim GA4 is connected for a site that has no property ID.
- **Phase 8 · Settings is deep-linkable.** Its tabs became a `st.radio` section picker
  bound to `settings_section`, so any page can send you to the exact section that fixes
  the gap: the banner's button targets 🔑 Google APIs, and the GA4 row targets 🌐 Sites.
  The Google section gained a four-step "how to get the file" guide and a per-site
  readability strip.
- **Phase 8 · Overview auto-loads once.** `_report()` fetches live figures on first
  paint when credentials exist and keeps the result for that site + date range +
  coverage source, so landing on a connected dashboard shows what's ranking instead of
  an empty panel telling you to press a button. Pressing **Re-run the analysis** or
  refreshing coverage invalidates it.
- **Phase 8 · the repo has tests.** `tests/test_phase8_ux.py`, 16 AppTest cases, run
  with `pip install -r requirements-dev.txt && pytest -q`.
- **Phase 9 · ToolsHall** is a third `SITE_DEFAULTS` entry (`TS_*` keys), sitting
  alongside ToolsVenue and ToolAcademy without touching either.
- **Phase 9 · `agents/backlink._importance()` + the new-site branch in `rank_targets()`.**
  No-performance-data sites rank on structural importance (homepage → shallow →
  tool-over-article) instead of a tied score read out alphabetically.
- **Phase 9 · `core/tracker.link_history()`** — count + most-recent-date of non-failed
  prior attempts at one URL, read by the Backlinks page's new "already linked" warning.
- **Phase 10 · `publishers/hashnode.py` + `publishers/medium.py`** — two more owned
  auto-publish destinations, registered in `publishers.PLATFORMS` alongside dev.to,
  Blogger and WordPress. Medium's `publish()` and its Settings help text both flag
  that the API can create a post but never edit or delete one.
- **Phase 10 · `core/tracker`'s community lane** — `log_community()`,
  `community_board()`, `community_summary()`, `COMMUNITY_STAGES`, and a `logged_at`
  override on `log()` — a manual, no-network tracker for Reddit/HN/Product
  Hunt/AlternativeTo/"awesome"-list submissions, shown as its own section on the
  Backlinks page (`ui/views/backlinks.py::_community_section`).
- **Phase 11 · `agents/analysis.page_verdict()` + `VERDICT_THRESHOLDS`** — the one
  function and the one dict that turn a page's indexed status + position +
  impressions + CTR into exactly one of five plain-English verdicts (Not indexed
  / Improve the page / Backlink candidate / Fix the title-description / Winning),
  with a sixth honest "Not enough data yet" for a page nothing's been measured
  for. `PageStat.verdict` and `ui/views/analysis.py::_with_verdicts()` both call
  it, so Overview's winners list and the Performance tab's pages table always
  agree. `ui.components.legend()` + `VERDICT_LEGEND` explain the five in plain
  English on both screens.

- [x] **Phase 11 — A verdict on every page: what it needs, not just how it's doing** —
      a small, scoped addition, not a new phase of build.
      **`agents/analysis.page_verdict()`** is the one function that decides what a
      page needs next, and **`VERDICT_THRESHOLDS`** is the one dict every number in
      that decision comes from — position bands, the CTR floor — so tuning them
      never means hunting through the two screens that display the result. It
      classifies a page into exactly one of five plain-English verdicts, derived
      only from measured numbers (indexed status from the coverage classifier;
      position/impressions/CTR from a Search Console row) and never guessed:
      **Not indexed** (bucket isn't Healthy) → fix indexing first; **Improve the
      page** (position 20+, with impressions) → content, not a link, is what's
      missing; **Backlink candidate** (roughly position 4-20) → the only bucket
      that recommends a backlink, on purpose; **Fix the title/description**
      (position 1-3, CTR under the floor) → it ranks but isn't earning clicks;
      **Winning** (position 1-3, CTR over the floor) → leave it, monitor. A sixth,
      honest state — **Not enough data yet** — covers an indexed page Search
      Console has nothing measured for; it's deliberately left out of the legend,
      since it isn't one of the five real verdicts, the same "never fill a blank
      with a guess" rule the rest of the dashboard already follows.
      **`PageStat.verdict`** (a property, so Overview's winners list gets it for
      free) and **`ui/views/analysis.py`'s `_with_verdicts()`** (which reads the
      same coverage frame the Fix Plan and Indexing tabs already load, to know
      which pages are actually Healthy) both call the one function, so the
      Overview and the Performance tab can never disagree about what a page needs.
      **Overview's winners list** shows the verdict as a coloured badge plus its
      one-line reason under every row, right where the three action buttons
      already sit. **The Performance tab's pages table** gained two columns,
      Verdict and Why, on the same "which pages earn the most" table the Overview
      draws its ranking from. **`ui.components.legend()`** is a small new reusable
      piece — a collapsed expander of (icon, label, explanation) rows — and both
      screens use it to explain the five verdicts in plain English, aimed at
      someone with no SEO background; `VERDICT_LEGEND` in `agents/analysis.py` is
      the one list both legends are built from. Nothing here auto-generates a
      backlink or touches a publisher — this phase only diagnoses and labels.
      *Note:* verified with `page_verdict()` called directly against the position
      / CTR boundaries the spec named (19.9 → Backlink candidate, 20 → Improve the
      page; CTR exactly at the floor → Winning, just under it → Fix the
      title/description; indexed with zero impressions → Not enough data yet, not
      a guess) and with a Streamlit `AppTest` pass driving the whole app through a
      stubbed live Search Console: the Performance tab's dataframe carries Verdict
      + Why columns with no exception, and Overview's winners list renders a
      correctly-coloured badge and reason on every row, matching the same page's
      row in the Performance tab. `pytest -q` still 16/16 — this phase changed no
      existing behaviour, only added the verdict alongside it.

- [x] **Phase 12 — Task wizards: guide a non-SEO user step by step** — a UX
      redesign over the working engine, not a rewrite of it. The trigger: the
      owner keeps forgetting how to use the tool and is handing it to a friend
      with zero SEO background, and a dense multi-section page asks them to
      hold five decisions in their head at once.
      **`ui.components` gained the wizard kit** — `wizard_steps()` (the "Step X
      of N" strip: every step named, done ones ticked, the current one
      highlighted, a plain "Step X of N — <name>" caption underneath so it
      reads with no colour at all), and `wizard_back()` / `wizard_next()` /
      `wizard_restart()`, the buttons every wizard below is built from.
      `wizard_next()` takes a `disabled` + `help` pair on purpose: a step can
      only be walked past once it's actually produced something to carry
      forward, and the reason why not is on screen, not just a greyed-out
      button.
      **Backlinks Lane A is now a 4-step wizard** — pick the page → choose
      platforms → generate the draft → review & publish — replacing the one
      page that used to show all four at once. Platform readiness moved into
      a collapsed expander (open only when something's missing) instead of
      always-on clutter above the wizard. Step 2 still won't let you past with
      no platform configured; step 3 still won't let you past with no
      OpenRouter key; step 4 is exactly the old review-and-publish screen,
      now with a "🔁 Build another backlink" reset. The tracker stays below
      the wizard as a standing record, not a wizard step.
      **Backlinks Lane B is now the exact 5-stage wizard the brief asked
      for** — pick target page → find prospects → choose a site → review the
      drafted pitch + article → send/copy + track — where the old page
      folded "choose a site" and "draft it" into one dense step. Step 5's
      intro line says outright, in bold, that this is the one step a human
      has to do by hand; nothing before it is reachable without a target
      chosen first (jumping the step counter straight to step 3 with no
      target bounces back to a warning, never a crash — see the test below).
      **Content's writer path is now a 5-step wizard** — what's it about →
      research & write → review & edit → images → publish — over the same
      five sections Phase 5 already had, just one on screen at a time with
      Next gated on the step before it actually finishing (a topic before
      research, a draft before review, a draft before publish).
      **Every wizard survives a stale step number.** Switching site, or
      landing on a step via a stored hand-off, re-checks that step's own
      precondition (a chosen target, a stored draft) and bounces back to a
      plain warning rather than crashing on a `None` — proven directly in the
      tests below by jumping `session_state`'s step key without ever visiting
      step 1.
      Nothing underneath moved: same `agents/backlink.py`, `agents/outreach.py`
      and `agents/content.py` calls, same tracker, same guardrails
      (WordPress always draft, Lane A owned-platforms-only, Lane B human-gated
      send, no invented numbers). This phase only changed how much of the page
      is on screen at once and in what order.
      **Overview and the plain-language pass needed little new work** — Phase
      8 already made Overview a prioritised, real-data "do this next" list
      (the winners table's per-row verdict badge, reason and three action
      buttons *is* item 2 of the brief), and Phase 8/11 already lead every
      metric with its meaning before the raw number and glossary it in
      `jargon_note()` / `legend()`. This phase's one small addition on top:
      removed two headers that had gone double once their section was wrapped
      in a same-titled expander (`_platform_readiness()`,
      `_outreach_readiness()`).
      *Note:* `tests/test_phase12_wizards.py` (14 new `AppTest` cases, all on
      the sample snapshot — no credentials needed to drive any wizard): each
      wizard starts on step 1 of the right total; Next/Back actually move the
      step counter; Lane A's step 2 and step 3 refuse to advance without a
      platform or an OpenRouter key and say so; Lane B names all five stages
      and step 5 states the human-approval point in its own text; jumping
      straight to Lane B step 3 or Content step 3 without the prior step's
      state present bounces back to a warning instead of raising; both pages
      still render with no wizard state at all. `pytest -q` — 30/30 (the
      original 16 plus these 14) — the existing Phase 8 suite needed one
      fix: Lane A's target-and-metrics step used to be visible regardless of
      platform readiness, so gating the *whole wizard* on a platform being
      configured (my first draft) hid the picker `test_build_backlinks_pre-
      selects_the_page_on_the_backlinks_page` depends on. Fixed by moving the
      "no platform configured" refusal to where it always belonged — step 2 —
      leaving step 1's picker reachable exactly as before.

- [x] **Phase 11-fix — Every page was reading "Not indexed", even indexed ones**
      — a critical correctness bug, reported live against toolshall.com (143
      pages actually indexed in Search Console, real GA4/GSC traffic in
      range) where the Analysis > Performance tab showed **every** page as
      "Not indexed — fix indexing first". Diagnosis, then fix.
      **Root cause (confirmed by reading the code, not guessed):** a missing
      or failed indexing check was silently read as a confirmed "no", in two
      places at once. (1) `ui/views/analysis.py::_with_verdicts()` decided
      "indexed" by set membership in `coverage_df` and defaulted straight to
      `False` for any page missing from it — which is *every* page on a
      fresh session for a site with no seed fallback: `core/seed.py`'s
      `SEED_BY_SITE` only lists `"toolsvenue"`, so ToolsHall starts from an
      **empty** coverage frame until "Refresh live data" is pressed, no
      matter what the live Search Console Performance API (queried
      separately, and successfully — hence the real clicks/impressions the
      report described) says. (2) `agents/analysis.py::page_verdict()`'s
      `indexed` parameter was a plain bool, so "never checked" and "Google
      confirmed not indexed" were the same value. (3) Compounding it:
      `core/gsc.py::inspect_urls()` discarded the per-URL `error` that
      `inspect_url()` already captured, so even a full URL Inspection sweep
      that failed for every URL (auth/quota/a property-URL mismatch) came
      back as coverage `""` for every row with the failure invisible, and
      `ui/data.py::refresh_live()` reported that as a plain success
      ("Loaded live coverage for N URLs" 🟢) — this environment has never
      had a Google key to confirm which specific failure mode hit
      toolshall.com, but the code path is real and reproducible either way,
      independent of *why* the check came back empty.
      **The fix:** `indexed` is now a genuine tri-state everywhere it's
      decided or consumed — `True` / `False` / `None`, never a bool that
      collapses "unknown" into "no". A new classifier bucket,
      `core.classifier.UNKNOWN` ("Couldn't check"), carries a real
      inspection failure without it being folded into Plumbing/Content/Other;
      it's matched first in `_COVERAGE_MAP` (before any "not indexed"-style
      text) so an error message that happens to contain "404" is never
      mistaken for Google's own verdict. `page_verdict()` gained a sixth
      state, **`V_UNCHECKED` ("Couldn't check yet", 🩺)**, returned whenever
      `indexed is None`, with a reason that says outright this is not a
      confirmed "not indexed". `PageStat.indexed` returns `None` for the
      `UNKNOWN` bucket instead of `False`. `gsc.inspect_urls()` now returns
      `[(url, coverage, error), ...]` instead of dropping `error`, and
      `ui/data.py::refresh_live()` stores failed URLs as `"Couldn't check:
      <error>"` rows (so the Fix Plan shows the real error) and — the actual
      honesty fix — **stops reporting a 100%-failed refresh as a success**:
      `row_count` now counts only URLs Search Console actually answered for,
      so a total failure correctly returns `(0, "…couldn't be checked for
      any of the N URLs…")` and the sidebar shows red, not green.
      **Made visible everywhere the old bug was invisible:** the Fix Plan and
      Indexing tabs gained the "Couldn't check" bucket (its own colour, count,
      and one-line explanation) via `BUCKET_ORDER`; the Performance tab shows
      an explicit "🩺 No coverage data loaded" notice when `coverage_df` is
      empty, so a page of "Couldn't check yet" verdicts is explained instead
      of looking like a wall of question marks; Overview's indexing-health
      section surfaces a warning naming how many pages couldn't be checked;
      and `VERDICT_LEGEND` explains the new state in plain English (unlike
      `V_NO_DATA`, which stays deliberately out of the legend, `V_UNCHECKED`
      is included — it usually means something needs re-checking).
      *Note:* `tests/test_phase11fix_indexing_verdict.py` (13 new tests):
      `page_verdict(indexed=None, …)` returns `V_UNCHECKED` not
      `V_NOT_INDEXED`, and a real `indexed=False` still returns
      `V_NOT_INDEXED` (the fix doesn't swallow genuine negatives);
      `classifier.recommend()` buckets an inspection-failure coverage string
      as `UNKNOWN`, and an error message containing "404" still buckets as
      `UNKNOWN` rather than `PLUMBING`; a stubbed `gsc._service()` proves
      `inspect_urls()` now carries the real exception text through instead of
      dropping it; `refresh_live()` against a 100%-failure stub returns
      `(0, …)` with the real error quoted, and a partial-failure stub keeps
      the good rows while bucketing the bad one as `UNKNOWN`; and the
      sharpest one — `_with_verdicts()` fed an **empty** `coverage_df` (the
      exact ToolsHall/no-seed/no-refresh shape) alongside a live performance
      row with real clicks/impressions renders **"🩺 Couldn't check yet"**,
      not "🔴 Not indexed" — plus the two guardrail tests that a page
      *confirmed* Healthy still renders correctly and a page *confirmed*
      broken still says Not indexed, so the fix narrows the bug without
      widening into a new one. `pytest -q` — 43/43 (the existing 30 plus
      these 13), including the `test_phase8_ux.py` `connected` fixture's
      `gsc.inspect_urls` stub, updated to the new 3-tuple contract.
      **Not verified against toolshall.com's real, live Search Console data**
      — this sandbox has no Google service-account key (same limitation
      every phase before this one has noted), so "the exact failure mode
      that hit toolshall.com" (an inspection auth/quota error vs. simply
      never having pressed Refresh for a no-seed site) couldn't be
      distinguished from here. Both are now handled identically and
      correctly either way, and the reproduction test above forces the
      precise shape (empty coverage + real live performance) the bug report
      described. **First real run for this fix:** open Analysis >
      Performance for toolshall.com, press **Refresh live data** in the
      sidebar first, and confirm indexed pages now show a real verdict
      (Backlink candidate / Improve the page / Winning / Fix the
      title-description) instead of "Not indexed" — and if any page still
      shows 🩺 "Couldn't check yet" after a refresh, that page's own error is
      now visible on the Fix Plan's "Couldn't check" section rather than
      hidden.

- [x] **Phase 11-fix-2 — Connected but unrefreshed sessions silently showed
      the sample snapshot as if it were live** — a follow-on to Phase 11-fix,
      reported live against toolshall.com (which loads 173 live URLs
      correctly once refreshed): the Analysis tabs showed the OLD sample
      snapshot as if it were live until the user manually pressed **Refresh
      live data**. Pages read "Not indexed" purely because the tab was
      reading stale sample coverage — a manual refresh corrected it, but
      nothing on screen had warned the data was stale, and a non-expert user
      would have trusted the false verdicts.
      **Root cause:** having a Google key file on disk (`ctx.creds`) was
      conflated with "this session's coverage is live". `connect_banner()`
      only fires when credentials are *missing*, so a connected-but-not-yet-
      refreshed session got no loud banner at all — just the small
      `data_source_note()` badge, easy to miss, plus (for toolsvenue, which
      has a real seed) the OLD 16-Aug snapshot rendering with no visual
      difference from a live one.
      **The fix, without touching `page_verdict()` or the classifier (both
      already correct from Phase 11-fix):**
      **`ui/data.py` — coverage now auto-loads.** `coverage_rows()` tries a
      live refresh automatically the first time a site's coverage is read in
      a session, whenever a Google key file is present — a connected session
      no longer silently hands back the sample rows just because nobody
      pressed the button yet. `_autoload_live_coverage()` runs at most once
      per site per session (success or failure alike), so a slow or broken
      sweep can't repeat itself on every rerun, and `autoload_result()` lets
      a page read back what happened, once.
      **`ui/components.py` gained two pieces.** `stale_coverage_banner(source,
      creds)` is a LOUD, in-content warning — not just a badge — that fires
      specifically in the one state that used to be invisible: credentials
      connected, but this session is still on the sample snapshot (the
      auto-load hasn't run, or it ran and failed). It stays quiet when
      credentials are missing entirely, since `connect_banner()` already
      covers that loudly and the two would otherwise repeat each other.
      `autoload_notice(result)` reports the automatic load's own outcome
      (success or failure) right under the page header.
      **Overview, Analysis and Backlinks all wire both in** immediately
      after computing `coverage_frame()`/`coverage_rows()` — the three
      screens named in the bug report, plus Backlinks since Lane A/B target
      eligibility is bucket-derived from the same coverage.
      **Verdicts computed from sample coverage are now marked, not silently
      confident.** Overview's winners list catches the specific mismatch
      that caused the report — live Search Console *performance* figures
      loading fine (that API needs no refresh button) while *coverage*
      (from the separate URL Inspection sweep) was still the old snapshot —
      with its own warning when `report.source == "live"` but
      `coverage_source == "seed"`, and marks each row's verdict badge
      "(sample)" in that state. `ui/views/analysis.py::_with_verdicts()`
      gained the same `coverage_source` parameter and appends "(sample)" to
      the Verdict column when the coverage behind it is stale — but NOT when
      `coverage_df` is empty, which is the separate, already-correct
      "Couldn't check yet" story from Phase 11-fix, not a sample story.
      *Note:* `tests/test_stale_data_banner.py` (10 new tests) drives Overview,
      Analysis and Backlinks through Streamlit's AppTest: all three
      auto-load live coverage on first open with no button press and say so
      ("Loaded live coverage for 4 URLs"); all three warn loudly
      ("Tried to load live coverage automatically" + "Showing sample data")
      when the auto-load itself fails (bad sitemap URL); the not-connected
      state still shows only `connect_banner`'s message, not a duplicate;
      `_with_verdicts()` marks a stale-but-populated coverage frame
      "(sample)" but leaves a live one and an empty one alone; and a direct
      unit test against ToolsHall (no seed at all — the exact reported site)
      proves `coverage_rows()`/`coverage_frame()` auto-load on the very
      first read rather than starting empty. `tests/test_phase8_ux.py`'s
      Phase 8 sample-to-live test was rewritten to match the new, correct
      behaviour: it used to assert that a connected-but-unrefreshed session
      *still* showed "SAMPLE data" (the bug, enshrined as a passing test) —
      it now asserts the opposite, plus a new companion test for the
      auto-load-fails path, and `_text()` gained `st.error` to its capture
      list so a failure banner is actually assertable. `pytest -q` — 55/55
      (43 before this fix, +2 net in test_phase8_ux.py — one old test
      replaced by three new ones — plus 10 in the new file).
      **Verified against toolshall specifically** (the site named in the
      report): a direct test against `core.classifier.HEALTHY` bucket proves
      a page with no seed at all loads live and buckets correctly on first
      read, with no manual refresh, matching "toolshall now loads 173 live
      URLs correctly" — this sandbox still has no real Google key, so the
      live property itself remains unverified from here, same limitation
      every phase before this one has noted.

- [x] **Phase 13 — Stop auto-fetching live data; suggest topics from real
      data on Content** — two scoped changes, not a new phase of build.

      **1 · Stop auto-fetching live data.** Reported live: a data screen
      could fetch live Search Console/GA4 on open, spending API quota with
      no click involved. Reading the code turned up four separate places
      this happened, not one — because Streamlit reruns the *whole script*
      on any interaction anywhere on the page, "fetches on open" from
      Phase 11-fix-2 actually meant "fetches on every rerun":
      `ui.data._autoload_live_coverage()` (Phase 11-fix-2's own fix, now the
      thing being undone), Overview's `_report()` calling
      `analysis.run(..., live=True)` on first paint whenever credentials
      existed, the Analysis page's Performance and Audience tabs calling
      `gsc.search_analytics()` / `ga4.*()` directly and unconditionally on
      every render of those tabs, and the Backlinks page calling
      `bl.rank_targets()` with no cached metrics (so it fetched its own) on
      every render of Lane A/B's target picker, plus `_target_keywords()`
      calling `kw.for_page()` the same way whenever a target was selected.
      **The fix: this dashboard now calls Google in exactly one place.**
      `ui.data.refresh_live(site, start, end)` — wired to the sidebar's
      "🔄 Refresh live data" button, which already existed for coverage — now
      also fetches Search Console performance (`["page"]`, `["query"]` and
      `["page","query"]` dimensions, covering every shape the app needs) and
      GA4's four reports, and caches all of it for the session.
      `ui.data` gained the readers every page now uses instead of fetching:
      `performance_metrics()` / `performance_pages()` / `performance_queries()`
      / `performance_page_queries()` / `ga4_cache()` / `keywords()` — the last
      one turns the cached raw rows into `core.keywords.Keyword` objects with
      no network call, via new optional `rows=` / `page_rows=` parameters on
      `core.keywords.gsc_keywords()` / `page_map()` / `for_page()` (default
      `None` still fetches live, which is what the Opportunities page's own
      *explicit* "Load my Search Console queries" button and "Build the
      brief" button intentionally keep doing — an explicit, one-off click is
      not the silent problem this phase closes). `agents.analysis.run()` no
      longer fetches anything itself — it takes `metrics=` / `keywords=` as
      plain inputs, so the module that decides the ordering is now a pure
      function of whatever was already loaded. `agents.backlink.rank_targets()`
      was already able to take a pre-fetched `metrics=` dict; every UI call
      site now always passes one (never `None`), so its own live-fetch branch
      is unreachable from the app and stays only as a safety net for a future
      caller that doesn't have a cache to pass. The old auto-load plumbing
      (`_autoload_live_coverage`, `autoload_result`, `ui.components.autoload_notice`)
      is deleted, not deprecated. `ui.data.refresh_seq()` is a small addition
      that made the "figures update the moment you refresh, no second click"
      behaviour still work: Overview memoizes its computed `Report`, and
      without this the memo would keep replaying the report built from the
      cache *before* your last refresh. Every screen that used to fetch
      silently now either reads the cache and says so (`stale_coverage_banner`
      already existed for coverage; Performance/Audience gained the same
      "no figures loaded yet — press Refresh live data" empty state) or, for
      the one narrow per-page keyword lookup on Backlinks, shows nothing
      rather than fetching, with a one-line hint to refresh.
      *Note:* `tests/test_phase13_live_data_gate.py` (9 new tests) proves
      `gsc.search_analytics` is never called across two full reruns of any
      of Overview/Analysis/Content/Backlinks with no button pressed, that one
      press of Refresh live data populates the cache every later reader
      shares, and that the cache — not a live re-fetch — is what the Content
      suggestions and Analysis tabs read afterward. `tests/test_stale_data_banner.py`
      and `tests/test_phase8_ux.py` had their Phase 11-fix-2 auto-load tests
      rewritten to assert the opposite (no key on session_state until refresh,
      the loud sample banner instead of a quiet fetch) rather than deleted, so
      the original stale-verdict bug they guarded against is still covered —
      just closed by the banner alone now, not by fetching. `pytest -q` —
      67/67 (58 before this phase, +9 new). Not run against real Google
      credentials — same limitation every phase before this one has noted —
      but the *shape* of the fix (one call site, everything else reads a
      cache) is exactly what makes quota spend predictable once real keys
      are in.

      **2 · Suggest article topics from real data.** Content's Step 1 ("What
      should this article be about?") gained a "💡 Suggested topics, from
      real data" expander, drawn before the Topic box so it reads as the
      first thing on the step rather than an afterthought. Two sources, both
      already-cached and already-scored:
      · **Search Console queries you rank poorly on** — `core.keywords`'s
        existing `DEEP` band (position > 20, real impressions), read via the
        new `ui.data.keywords()` cache reader, each rendered as *"You get N
        impressions for 'X' but rank at P — write this,"* with N and P
        straight from the cached row.
      · **Competitor content gaps** — reused, not reimplemented: if the
        Opportunity Finder's own scan (`agents.opportunity.scan()`, kind
        `GAP`) has already run this session, its top gap opportunities and
        their real `reasons[0]` (e.g. "3 of 3 competitors cover this; you
        have nothing") are pulled straight from `st.session_state[opp_scan]`
        — no second scrape, and nothing runs a competitor read from the
        Content page itself, which would have been its own silent-fetch
        violation of change 1 above.
      Picking a suggestion (`st.button("Use this", on_click=...)`) fills
      `content_topic` / `content_keyword` the same way every other hand-off
      in this app fills them (the same pattern the keyword-brief picker
      already used) — typing a topic by hand still works exactly as before,
      and nothing writes or researches anything until Step 2's own button is
      pressed. With no live performance cached yet, the expander says so —
      *"No suggestions yet — refresh live data to get suggestions"* — quoting
      the sidebar button by name, and never shows a number it doesn't have.
      *Note:* the same `tests/test_phase13_live_data_gate.py` proves the
      empty state names Refresh live data and contains no invented figures,
      that a real DEEP-band query appears with its exact cached impressions
      and position after a refresh and that clicking "Use this" fills both
      boxes, that a striking-distance (position 4-20) query is correctly
      *excluded* — it's a different, already-close story that belongs to
      Overview/Opportunities — and that a cached competitor-gap scan surfaces
      its real reason text unchanged.

- [x] **Phase 15 — Two bug fixes: live data lost on reload, a filled-in
      topic reported as empty** — both reported live, both small and scoped.

      **Bug 1 · Sample data returned after a browser tab reload.**
      Repro: press Refresh live data (real data shows), reload the tab ->
      back to the sample snapshot. Cause: `ui/data.py` cached a refresh's
      coverage, Search Console performance and GA4 only in
      `st.session_state`, which a tab reload starts completely fresh —
      losing a real refresh was never actually different from never having
      refreshed at all, as far as the next page load was concerned.
      **The fix:** every successful `refresh_live()` now also writes its
      result to `data/live_cache/<site>.json`, alongside the timestamp it
      was refreshed at. A new `_hydrate_from_disk(site)` runs once per
      site per session, before `coverage_rows()` / `performance_cache()` /
      `ga4_cache()` / `has_live()` / `has_live_performance()` /
      `has_live_ga4()` read `session_state` — so a fresh session picks up
      the last real refresh from disk before ever falling back to seed.
      This reads a cache, never the network, so it doesn't reopen Phase
      13's "call Google in exactly one place" rule. A new
      `ui.data.last_refreshed(site)` reports when that was (from this
      session or a disk-hydrated earlier one), and `data_source_note()`
      now says **"🟢 Live data (last refreshed \<time\>)"** or **"🟡 SAMPLE
      data — never refreshed"** instead of the old undated wording — shown
      on Overview, Analysis, Backlinks and the sidebar alike. Sample only
      shows for a site with no disk cache at all, i.e. one that has
      genuinely never been refreshed, in this session or any earlier one —
      exactly the rule asked for. `data/live_cache/` is git-ignored, the
      same as the rest of `data/`'s generated state.
      **Bug 2 · "Go back and enter a topic first" with a topic plainly
      typed in.** Repro: type a topic on the Content page, click "Research
      & write" -> told to go back and enter one. Cause, found by reading
      Streamlit's own widget-state handling, not guessed: a widget's
      `session_state` entry is cleared once that widget stops being
      instantiated on a render — and step 1's `content_topic` text input
      (along with `content_keyword`, `content_notes` and the internal-link
      multiselect) is only ever rendered by `_c_topic()`, step 1's own
      function. The moment the wizard moved to step 2, those keys were
      living on borrowed time: they still read correctly on the very next
      render (the entry hadn't been swept yet), which is exactly why typing
      a topic and clicking "Research & write →" looked fine — but the
      *following* rerun on step 2 (clicking "🔎 Research and write the
      draft" itself is exactly such a rerun) found `content_topic` already
      gone and read back `""`. **The fix:** `_c_topic()` now copies its
      four field values into one plain, non-widget session key,
      `content_fields`, every time it renders — which happens at least
      once, on step 1, before Next can even be pressed. `_c_research_write()`
      (step 2) and its "Research and write the draft" button both read from
      `content_fields` instead of the raw widget keys, so the values it
      acts on are whatever step 1 actually last showed, not whatever
      Streamlit happened to still be holding onto.
      *Note:* `tests/test_phase15_persistence_and_topic.py` (5 new tests)
      proves both: a direct `ui.data` test refreshes a site, clears
      `st.session_state` outright (the same isolation a tab reload gives
      you), and confirms `coverage_rows()` / `coverage_frame()` still
      return "live" with the refreshed rows and `last_refreshed()` still
      answers — plus a matching AppTest pass through the actual Overview
      page (refresh in one `AppTest` "tab", read it back from a brand new
      one) and a companion test that a site with no disk cache at all still
      correctly reads as sample after the same clear. For the topic bug: a
      test reproduces the exact failure — type a topic, advance to step 2,
      force a second rerun there (matching what pressing the write button
      itself does) — and confirms the "go back" warning never appears and
      the topic still reads correctly; a second test stubs the write
      pipeline (`agents.content.research` / `page_facts` / `write`) end to
      end and presses the actual "🔎 Research and write the draft" button
      after that same extra rerun, confirming the run that lands in
      `session_state["content_run"]` carries the real typed topic, not "".
      A new `tests/conftest.py` gives every test its own throwaway
      live-cache directory (an autouse fixture patching
      `ui.data._CACHE_DIR` to `tmp_path`), so the new disk persistence
      never writes into the repo's real `data/live_cache/` from a test run
      or leaks a refresh from one test into another — two pre-existing
      tests' banner-text assertions were updated for the new dated wording
      (`"Live data from Search Console"` → `"Live data (last refreshed"`);
      nothing else about their behaviour changed. `pytest -q` — 72/72 (67
      before this phase, +5 new tests in the new file; the two wording
      updates above touch existing tests, not new ones).
      Not verified against a real browser tab reload or real Google
      credentials — this environment still has neither — but the
      reproduction is exact: `st.session_state.clear()` is precisely what a
      fresh Streamlit session starts from, and the AppTest pass drives the
      real `refresh_live()` → disk-write → fresh-session → disk-read path
      end to end with no shortcuts.

- [x] **Phase 16 — Per-site OUTPUT TEMPLATES: real HTML, not plain markdown**
      — reported live: generated articles came out as plain markdown, but
      neither site's editor takes markdown. ToolsVenue's tool pages and
      ToolsHall's blog posts are each their own hand-styled, inline-styled
      HTML, and they're structured differently from each other.
      **`agents/output_templates.py`** is the new module that does the
      repainting. It reads the same structured data `agents.content.write()`
      already returns — the body's own `## ` sections, plus `draft.meta`'s
      `faq` and `internal_links` — and never reparses or reinterprets what
      the model wrote, only redraws it: `render_toolsvenue()` produces the
      tool-page pattern (`<section>` blocks, a coloured-rule `<h2>`, an
      HTML `<table>` when a section is a numbered how-to of 3+ steps, FAQ as
      `<details>`, a related-tools `<aside>` sidebar, with a markdown-link
      scrape of the "related" section as a fallback if the model skipped
      the structured `internal_links` field); `render_toolshall()` produces
      the blog-post pattern (intro paragraph, plain `## H2` sections, FAQ as
      `<details>`, a related-tools list, and a closing CTA box that links to
      the most relevant related page, or the homepage with none). `render()`
      is the one entry point; `FORMAT_MARKDOWN` returns the draft's own
      markdown completely unchanged — the explicit fallback the brief asked
      for, always one pick away.
      **`core/config.py` gained the per-site setting.** `Site.output_format`
      (a new `{PREFIX}_OUTPUT_FORMAT` .env key, exactly the existing
      per-site pattern) plus `output_format(site)`, which resolves it: the
      site's own saved value, else a built-in per-`key` default
      (`DEFAULT_OUTPUT_FORMAT` — ToolsVenue → its HTML, ToolsHall → its
      HTML), else plain markdown for a site nobody's specified a template
      for yet (ToolAcademy, today). An unrecognised saved value (a typo'd
      manual .env edit) is treated the same as unset rather than crashing
      the writer. Editable in **Settings → Sites** (`core/settings.py`'s
      `site_fields()` gained the field, in the same hardcoded-options style
      the keyword-engine on/off field already uses) alongside every other
      per-site setting.
      **Generating for a site now outputs in that site's format
      automatically, per the brief.** `agents/content.py` gained
      `render_output(draft, site, fmt=None)` (resolves the format and calls
      the templates module) and both `to_article()` and `save_run()` now
      take an optional `fmt`, defaulting to `config.output_format(site)`
      when one isn't given — so nothing that already calls them with just a
      site has to change. `publishers/base.py`'s `Article` gained an
      optional `body_html` field ("" by default, so every existing caller —
      Lane A/B posts, and a markdown-format Content run — is byte-for-byte
      unaffected); `publishers/wordpress.py`'s `publish()` now posts
      `article.body_html or md_to_html(article.body_markdown)`, so a
      ToolsVenue/ToolsHall draft is filed to WordPress in its own real
      template, not markdown run through the same generic converter every
      other publisher uses.
      **The Content page's review step (step 3) gained the picker.** A new
      `_output_format_picker()` shows a selectbox defaulting to the site's
      own format, and a collapsed "📋 Paste-ready output" expander with
      `st.code(...)` (Streamlit's own copy button) showing exactly what
      would be filed or pasted — live against whatever's currently in the
      title/body/meta boxes above, via the same `_edited_draft()` step 4/5
      already use. The choice is written into `run["output_format"]` (a
      plain dict key, not the selectbox's own widget key) so it survives
      into step 5 the same way Phase 15 made the typed topic survive past
      step 1 — a widget's `session_state` entry is swept once it stops being
      instantiated, and step 5 doesn't redraw this selectbox. Step 5's own
      header now names the format it's about to file in, and both the
      "Create the WordPress draft" and "Save to outputs/ only" buttons pass
      it through to `publish_draft()` / `save_run()`. `save_run()` now also
      writes `content/article.html` alongside the always-written
      `content/article.md` whenever the resolved format isn't markdown, so
      the `outputs/<slug>/` folder keeps the raw source AND the paste-ready
      file; `run.json` records which format was used.
      **Nothing here touches or auto-publishes a live page** — WordPress
      publishing is still hard-coded to draft inside `publishers/wordpress.py`,
      unchanged; this phase only changes what the draft's *content* looks
      like.
      *Note:* the two templates are a best-effort match to the tool-page /
      blog-post patterns described, not a pixel-for-pixel copy of a real
      ToolsVenue or ToolsHall page — no real sample HTML was pasted in for
      this phase. `render_toolsvenue()` / `render_toolshall()` in
      `agents/output_templates.py` are the one place to tighten the markup
      if/when a real page's HTML is pasted in for comparison.
      `tests/test_phase16_output_templates.py` (16 new tests, no network or
      model call): both sites' defaults resolve correctly and an explicit
      save (or an unrecognised one) is handled correctly; ToolsVenue's HTML
      has the `<section>`/`<table>`/`<details>`/`<aside>` pieces, including
      the markdown-link-scrape fallback and skipping empty FAQ/related
      blocks entirely rather than rendering them hollow; ToolsHall's HTML
      has its `<h2>` sections, FAQ, related list and CTA box, including the
      CTA falling back to the homepage with no related pages; the markdown
      format returns the draft completely unchanged; `to_article()` only
      sets `body_html` for an HTML format (a markdown-format site, and a
      call with no site at all, both get `""`, unchanged from before this
      phase); `save_run()` writes `article.html` only for an HTML format,
      and an explicit `fmt=` overrides the site default; and two Streamlit
      `AppTest` passes drive the real Content wizard — the picker defaults
      to ToolsVenue's format with a real HTML preview rendered, and
      switching to Plain markdown on step 3 survives, unchanged, all the
      way to step 5's own header. `pytest -q` — 88/88 (72 before this
      phase, +16 new). Not run against a real WordPress account or a real
      model reply — this environment still has neither, the same
      limitation every phase before this one has noted — so the actual
      posted draft's HTML has been verified by direct inspection of
      `render_toolsvenue()` / `render_toolshall()`'s output against a
      realistic six-section article, not against a live WordPress post.

- [x] **Phase 17 — Save generated items, and before/after impact tracking** —
      two features, both reported as needed live: generation costs real
      money and nothing generated was kept between sessions, and there was
      no way to tell whether a page actually moved after a backlink or an
      article.
      **Feature 1 · Saved items (manual).** `core/saved_items.py`, in
      `core/tracker.py`'s spirit — plain files under `data/`, nothing
      hidden in a database — but its own shape: a saved item can be a full
      article, so this writes one JSON file per item, organized
      `data/saved_items/<site>/<YYYY-MM-DD>/`, plus a light CSV index
      (`data/saved_items/index.csv`) so browsing doesn't open every file
      just to show a title. `save_item()` records the full content, the
      target URL/platform, the type (`article` / `backlink`), the model
      used and a timestamp; `list_items()` reads the index only (filterable
      by site/type); `load_item()` opens one file's full content. **Saving
      is manual only** — nothing here is called except by a "💾 Save"
      button someone pressed: Content's step 3 review (the edited article,
      rendered in whatever output format is picked), Backlinks Lane A's
      step 4 per-platform draft, and Lane B's guest-article editor. A new
      sidebar page, **"Saved & Impact"** (`ui/views/saved_impact.py`,
      registered in `ui/views/__init__.py` between Backlinks and Settings),
      has a "💾 Saved items" tab: a site + type filter, a table of
      everything saved, and a picker that opens one item's full content in
      a copyable `st.code` block.
      **Feature 2 · Before/after impact tracking.** `core/impact.py`, same
      `data/` convention, its own CSV (`data/tracked_pages.csv`). A page
      enters tracking two ways, both wired in this phase: automatically —
      `_track_backlink_target()` in `ui/views/backlinks.py` fires the
      instant Lane A generates a draft or Lane B drafts a pitch/article for
      a target page, and `_track_new_article()` in `ui/views/content.py`
      fires the instant a Content run's WordPress draft is actually
      created at a real URL — or manually, via the new "➕ I worked on this
      page" form on the Saved & Impact page's "📈 Impact tracking" tab
      (paste or pick a URL, no auto-fetch). Either way,
      `impact.start_tracking()` snapshots whatever `ui.data.performance_metrics()`
      already has cached for that URL as the baseline (impressions, clicks,
      position, date) — **never a fresh API call**, respecting `ui/data.py`'s
      "call Google in exactly one place" rule — and is a no-op if the page
      is already tracked, so the baseline is set exactly once, at the point
      the page actually started being worked on, not overwritten by a
      later run. When nothing was cached yet, the baseline is honestly 0
      with `baseline_live=False` recorded, not silently presented as a
      measurement. The tab's comparison (`impact.compare()`) shows every
      tracked page's baseline + date, latest + date (from the sidebar's
      last refresh), the change, and days elapsed; under
      `impact.MIN_DAYS_FOR_A_READ` (14) it shows **"Too early to tell —
      short-term changes can be noise"** rather than any verdict, and a
      standing banner states the honest limit plainly: tracking only works
      forward from the moment a page is added, it cannot reconstruct a
      baseline for work done before that.
      **Guardrails kept:** nothing here auto-publishes, auto-fetches, or
      invents a number — both new modules only ever read whatever the
      sidebar's Refresh live data already cached. `data/saved_items/` was
      added to `.gitignore` alongside `data/live_cache/` and the tracker
      CSVs — this is the user's content, not the app's.
      *Note:* `tests/test_phase17_saved_items_and_impact.py` (13 new
      tests, direct unit tests against `core.saved_items` / `core.impact` —
      both have no Streamlit or network dependency, so this is the fastest
      way to pin the actual contract): a save persists and reloads
      byte-for-byte; listing filters by site and by type; a missing file
      loads as `None` rather than raising; starting tracking snapshots the
      exact baseline numbers/date passed in; a page already tracked keeps
      its FIRST baseline when generated for again; a baseline with nothing
      cached is marked `baseline_live=False`; `compare()` computes change
      and elapsed days correctly (checked against a known date pair) and
      returns `has_latest=False` with no invented "change" when nothing's
      cached for the latest side, and `None` for an untracked page; under
      14 days is flagged `too_early=True`, 14+ is not. All isolated to a
      `tmp_path` — never the repo's real `data/`. `pytest -q` — 101/101
      (88 before this phase, +13 new). Also smoke-tested by hand through
      Streamlit's `AppTest`: Content, Backlinks and the new Saved & Impact
      page all render with no exception in sample mode, and the manual "I
      worked on this page" form actually writes a tracked row that a
      **second, fresh** `AppTest` session (no shared session_state) still
      reads back — proving the CSV, not memory, is what's authoritative,
      the same property `ui/data.py`'s disk cache relies on. Not run
      against a real Google/OpenRouter credential from here — same
      limitation every phase before this one has noted.

- [x] **Phase 18 — Two reported bugs: page-scoped Content suggestions, and the
      sidebar's site surviving a reload** — both scoped fixes, no new pages.
      **Bug 1 — "Write article" was scoping the writer's notes to the clicked
      page but not its two real-data sections.** `ui/views/overview.py`'s two
      hand-offs (`_to_content_page`, and `_to_content` for STRENGTHEN/REWRITE
      recommendations) now also set `content_focus_url`. `ui/views/content.py`
      pops that transient key into a persistent `content_focus_page` on step
      1's first render (the same "persist past the widget sweep" trick
      `content_fields` already used), and threads it through:
      **"Suggested topics, from real data"** now calls a new
      `_page_topic_suggestions()` — that page's own Search Console queries
      via `core.keywords.for_page()`, striking-distance ones first, falling
      back to site queries that share words with the page's URL slug when
      Search Console has no page-level rows yet; competitor gaps (site-wide
      by construction) are left out entirely when a page is in focus.
      **"Pick the keyword from real data"** now calls a new
      `_keyword_helper_for_page()` in place of the generic `kw.brief()` flow —
      the page's own queries, with its striking-distance ones (real
      impressions, position 5-20) under an explicit "⭐ Recommended — real
      demand, close to ranking" heading. Nothing invented anywhere: there is
      still no paid keyword API, so "recommended" means real GSC demand
      close to ranking and nothing else. Landing on Content directly (no
      hand-off) is untouched — same site-wide suggestions as before. A
      "Show site-wide instead" link clears the focus by hand.
      **Bug 2 — the sidebar's site selector had no `key=`,** so `st.selectbox`
      had nothing to remember between reruns and always fell back to its
      first option — `config.SITES[0]` — including on a browser tab reload,
      which starts a brand-new Streamlit session. `ui/data.py` gained
      `save_selected_site()` / `last_selected_site()`, writing to
      `data/ui_state.json` on every change (skipped if unchanged) — the same
      "session_state alone isn't enough, it's wiped by a reload" pattern
      Phase 15 built for live data, just for one string instead of a whole
      cache. `app.py` now seeds `st.session_state["site_key"]` from that file
      before the selectbox is drawn (falling back to the first site if the
      saved key no longer exists, e.g. a site removed from `.env`), keys the
      widget on it, and persists on every rerun.
      *Note:* `tests/test_phase18_page_scope_and_site_persistence.py` (5 new
      tests, via Streamlit's AppTest): clicking "Write article" on either of
      two indexed pages with distinct striking-distance queries lands on
      Content showing **only** that page's own query as a suggestion and as
      a recommended keyword, labelled "Recommended", with the other page's
      query never appearing; navigating to Content directly keeps the old
      site-wide behavior (neither page's URL is claimed as a scope); picking
      ToolsHall in the sidebar and then opening a brand-new `AppTest`
      session (no shared `session_state`, the same isolation a real reload
      gives you) still shows ToolsHall, not the default ToolsVenue; a fresh
      install with nothing saved still defaults to the first site; and an
      empty/blank save is ignored rather than clearing what was saved.
      `pytest -q` — 106/106 (101 before this phase, +5 new). Not run against
      a real Google/OpenRouter credential from here — same limitation every
      phase before this one has noted.

## Next up (start here)
**The build is done — every phase through 9 is ticked.** What the project needs now is its
first real run: this environment has never had a Google key, an OpenRouter key or a
platform key, so every path has been verified against stubs and none against a live
account. Work the list below in order; each item is the first time a piece of this touches
reality. Phase 8 removed the last excuse for not starting — connect Google and the Overview
fills in by itself. ToolsHall (Phase 9) is configured but has no credentials here either —
it needs the same `TS_*` values filled in before it shows anything but sample data.

**First real run (in this order):**
- Connect Google: **Settings → Google APIs**, then **Test connections**, then **Refresh
  live data** in the sidebar — that one button is the front door for everything below now
  (Phase 13): it loads coverage, Search Console performance and GA4 in one go, and
  Overview ranks on real impressions and grows a 🎯 striking-distance step immediately,
  with no separate "run" step needed.
- Write one real article: add an OpenRouter key + a Content model, type a topic, and
  press **Research and write the draft**. That's the only way to see the drafting prompt
  and the quality checks against a live model. If DuckDuckGo throttles the research step,
  add a Serper key in **Settings → Prospecting** — the same provider serves both.
- File that draft to WordPress once, so the per-site application password is confirmed
  end to end (media upload included).
- Run Lane A once for real (dev.to key + "save as an unpublished draft").
- Run **Settings → Prospecting → Test search**, then prospect once for a real target page.
- Send one guest pitch by hand (copy path) before wiring SMTP.
- Run **Opportunities → Scan for opportunities** once against a real competitor domain —
  it's the only way to see how a real sitemap and real page titles come back. Save the
  competitors permanently in **Settings → Sites → Competitor sites**.

## How a fresh chat should read this
Everything is built, so a new session is maintenance, not construction: read `CLAUDE.md`,
then this file, then the module you're about to touch — and keep the guardrails
(draft-only WordPress, owned platforms only, human-gated outreach, no invented numbers).
The hand-off plumbing between pages is `st.session_state`: `content_topic` /
`content_keyword` / `content_notes` / `content_source` for the writer, `bl_focus_url` /
`bl_focus_from` for Lane A's target picker, `analysis_bucket` / `analysis_focus` for the
Fix Plan, and `nav` to change page. `agents/analysis.py` is what decides *which* of those a
page gets, and `ui/components.py` is what every page draws with. Phase 8 added two more
hand-off facts worth knowing: `settings_section` deep-links into one Settings section, and
`agents/analysis.ranked_pages()` produces the `PageStat` rows the Overview's winners table
and its three buttons are built from. Phase 18 added `content_focus_url` (transient, from
Overview) / `content_focus_page` (its persistent copy on the Content page) — when set, the
"Suggested topics" and keyword-picker sections scope to that one page instead of the whole
site; see `ui/views/content.py`'s `_page_topic_suggestions()` and
`_keyword_helper_for_page()`. Also Phase 18: the sidebar's selected site now persists to
`data/ui_state.json` via `ui.data.save_selected_site()` / `last_selected_site()`, the same
reload-survival trick the live-data cache already used. Run `pytest -q` before and after
touching any of it — `tests/test_phase8_ux.py` drives the whole journey through Streamlit's
AppTest, and `tests/test_phase18_page_scope_and_site_persistence.py` covers these two fixes.

## Still needed from the user (pluggable, safe to defer)
- Real sample HTML from a live ToolsVenue tool page and a live ToolsHall blog
  post, if the Phase 16 templates should match byte-for-byte rather than
  best-effort — paste them in and `agents/output_templates.py`'s
  `render_toolsvenue()` / `render_toolshall()` are the one place to tighten.
- Run **Settings → Test connections** with the real service-account file, so live GSC
  and GA4 are confirmed against the actual properties.
- Image API name (currently dummy → writes image briefs).
- Keyword API name (optional; GSC-first works free — the engine runs without it and simply
  shows no volumes).
- Competitor domains per site, if you'd rather name them than have the Finder search for
  them (**Settings → Sites → Competitor sites**).
- WordPress username + Application Password per site (now editable per site in Settings).
- Confirm toolacademy.com is self-hosted WordPress.
- **`daily_backlink_job.py`** — it was meant to be ported in Phase 3 but never reached the
  repo, so the publishers were written from the platform API docs instead. Still worth
  dropping in: if its Blogger auth differs from the standard refresh-token exchange,
  swap `publishers/blogger.py → _access_token()` for the original.
- Platform keys to actually switch Lane A on: dev.to API key, the four Blogger values
  (blog ID, client ID, client secret, refresh token), a Hashnode personal access token
  + publication ID, and/or a Medium integration token.
- Email/SMTP for the optional guest-outreach send (else copy-paste pitches) — plus
  `OUTREACH_FROM_NAME`, which signs the pitch.
- Optional: a search API key (Serper / SerpAPI / Brave) if DuckDuckGo throttles
  prospecting. Set the provider in **Settings → Prospecting**.
