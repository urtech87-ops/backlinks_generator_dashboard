# PROGRESS.md — living status (Claude Code updates this after every phase)

> **How to use:** If a chat gets long/expensive, start a new conversation and paste
> this file (or add it to a Project). It carries enough context to resume with zero
> history. Claude Code: after finishing a phase, update the checklist, the "Done /
> Next up" lines, and the timestamp below.

**Last updated:** 2026-09-14 · **Current phase:** Phase 11 done — **a plain-English
"what this page needs" verdict on every ranked page**
**Overall:** ▓▓▓▓▓▓▓▓▓ 100% (all nine roadmap phases shipped, plus two small scoped
additions — Phase 9 and Phase 10 — on top. Phase 7 made Overview the conductor;
Phase 8 made it the *spine*: it is the landing page, it shows your pages ranked on the
impressions they actually earn, and every row carries the three buttons that act on it —
Build backlinks · Write article · Fix — each pre-filling the agent that does the job. A
disconnected dashboard now says out loud that its numbers are SAMPLE data and offers the
one button that changes that. What's left is not building — it's running the thing against
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
  live data** in the sidebar. Then **Overview → Run the analysis** — that's the front door
  for everything below, and with Search Console live it ranks on real impressions and
  grows a 🎯 striking-distance step it can't show on seed data.
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
and its three buttons are built from. Run `pytest -q` before and after touching any of it —
`tests/test_phase8_ux.py` drives the whole journey through Streamlit's AppTest.

## Still needed from the user (pluggable, safe to defer)
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
