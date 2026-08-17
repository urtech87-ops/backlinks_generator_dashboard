# PROGRESS.md — living status (Claude Code updates this after every phase)

> **How to use:** If a chat gets long/expensive, start a new conversation and paste
> this file (or add it to a Project). It carries enough context to resume with zero
> history. Claude Code: after finishing a phase, update the checklist, the "Done /
> Next up" lines, and the timestamp below.

**Last updated:** 2026-08-17 · **Current phase:** Phase 3 done → Phase 4 (guest outreach)
**Overall:** ▓▓▓▓░░░ ~50% (foundation, UI shell and the backlink agent's auto-publish
lane are done; guest outreach + the content agent to go)

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
- [ ] **Phase 4 — Backlink agent · Lane B (guest outreach)** ← next
- [ ] **Phase 5 — Content + SEO agent (volume path)**
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
  Backlinks Lane A is now real (below); Lane B keeps the placeholder until Phase 4.
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
- Backlinks page Lane A is live: platform readiness naming the exact missing settings,
  a ranked target picker, a per-platform draft editor with a link-count check
  (0 links → error, 2+ → "this reads as link-building"), a "save as draft everywhere"
  option for a first run, and the tracker.

## Next up (start here)
**Phase 4 — Backlink agent, Lane B (guest outreach).** Read `PHASES.md` → Phase 4, then
`agents/backlink.py` (reuse `draft_article`'s prompt shape and `_parse_json`) and
`core/tracker.py` (the same CSV takes Lane B's stages via the `status` column — add
`prospected` / `pitched` / `accepted` to `STATUS_LABEL` rather than starting a second
file). Lane B's tab is in `ui/views/backlinks.py → _lane_b()`, still a `coming_soon`
block. The email settings it needs (`OUTREACH_FROM_EMAIL`, `SMTP_*`) already exist in
`core/settings.py` and `.env.example`.

**The one hard rule for Phase 4:** do not add a publisher for third-party sites.
`publishers/PLATFORMS` stays owned-platforms-only; outreach drafts a pitch and stops, a
human clicks send, and the host publishes.

**Before Phase 4, worth doing:** run Lane A once for real. Add a dev.to API key in
Settings, pick a target page, tick "save as an unpublished draft", and publish — that
confirms the drafting prompt and the dev.to publisher against a live account, which
nothing in this environment could.

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
- Email/SMTP for the optional guest-outreach send (else copy-paste pitches).
