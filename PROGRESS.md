# PROGRESS.md — living status (Claude Code updates this after every phase)

> **How to use:** If a chat gets long/expensive, start a new conversation and paste
> this file (or add it to a Project). It carries enough context to resume with zero
> history. Claude Code: after finishing a phase, update the checklist, the "Done /
> Next up" lines, and the timestamp below.

**Last updated:** 2026-08-18 · **Current phase:** Phase 4 done → Phase 5 (content agent)
**Overall:** ▓▓▓▓▓░░ ~60% (foundation, UI shell and BOTH backlink lanes are done — the
user's main target is built end to end; the content agent's in-dashboard path is next)

---

## System in one paragraph

Streamlit dashboard = conductor for two sites (toolsvenue.com, toolacademy.com). Three
agents: **Analysis** (OpenRouter, cheap) reads Search Console + GA4, triages not-indexed
pages into Plumbing / Content / Crawl-budget and ranks winners; **Content + SEO** (Claude,
strongest — lives in `.claude/skills/`) writes SEO/AEO/GEO articles → WordPress drafts;
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
  optional pluggable paid API. Keyword branch is OPTIONAL.
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
- [ ] **Phase 5 — Content + SEO agent (volume path)** ← next
- [ ] **Phase 6 — Opportunity Finder + optional Keyword engine**
- [ ] **Phase 7 — Orchestration & polish**

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
- The Content page is still an honest placeholder — it states what Phase 5 will build and
  shows live readiness (WordPress creds, models, image provider) instead of dead buttons.
  Both Backlinks lanes are now real (below).
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

## Next up (start here)
**Phase 5 — Content + SEO agent (volume path).** Read `PHASES.md` → Phase 5, then
`.claude/skills/blog-writer-seo-aeo-geo/SKILL.md` (the quality path this fast path has to
stay consistent with) and `.claude/skills/wordpress-publisher/assets/publish.py`. Reuse
`core/openrouter.chat()` and `agents/backlink._parse_json` for the JSON-mode drafting,
and `publishers/wordpress.py` for the draft (status is hard-coded to `draft` there —
leave it that way). The Content page is still the honest placeholder in
`ui/views/content.py`.

**Worth doing before Phase 5, now that both link lanes exist:**
- Run Lane A once for real: add a dev.to API key, tick "save as an unpublished draft",
  publish. That's the only way to confirm the drafting prompt and the dev.to publisher
  against a live account.
- Run **Settings → Prospecting → Test search**, then find prospects once for a real
  target page. If DuckDuckGo throttles you, add a Serper key — the provider is a
  dropdown, nothing else changes.
- Send one pitch by hand (copy path) before wiring SMTP. The board doesn't care which
  way it went out, and it tells you whether the pitch reads like a person wrote it.

## Still needed from the user (pluggable, safe to defer)
- Run **Settings → Test connections** with the real service-account file, so live GSC
  and GA4 are confirmed against the actual properties.
- Image API name (currently dummy → writes image briefs).
- Keyword API name (optional; GSC-first works free).
- WordPress username + Application Password per site (now editable per site in Settings).
- Confirm toolacademy.com is self-hosted WordPress.
- **`daily_backlink_job.py`** — it was meant to be ported in Phase 3 but never reached the
  repo, so the publishers were written from the platform API docs instead. Still worth
  dropping in: if its Blogger auth differs from the standard refresh-token exchange,
  swap `publishers/blogger.py → _access_token()` for the original.
- Platform keys to actually switch Lane A on: dev.to API key, and/or the four Blogger
  values (blog ID, client ID, client secret, refresh token).
- Email/SMTP for the optional guest-outreach send (else copy-paste pitches) — plus
  `OUTREACH_FROM_NAME`, which signs the pitch.
- Optional: a search API key (Serper / SerpAPI / Brave) if DuckDuckGo throttles
  prospecting. Set the provider in **Settings → Prospecting**.
