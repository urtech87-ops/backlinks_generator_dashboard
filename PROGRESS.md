# PROGRESS.md — living status (Claude Code updates this after every phase)

> **How to use:** If a chat gets long/expensive, start a new conversation and paste
> this file (or add it to a Project). It carries enough context to resume with zero
> history. Claude Code: after finishing a phase, update the checklist, the "Done /
> Next up" lines, and the timestamp below.

**Last updated:** 2026-08-17 · **Current phase:** Phase 1 (finishing) → Phase 2
**Overall:** ▓▓░░░░░ ~20% (foundation built; UI + three agents to go)

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

## Phase checklist

- [~] **Phase 1 — Foundation & Analysis** — built: `core/` (config, gsc, ga4, classifier,
      seed) + `app.py` with Fix Plan / Indexing / Performance / Audience tabs, seeded with
      the real 16-Aug Search Console state (30 Plumbing / 11 Content / 10 Crawl-budget).
      *Left:* minimal in-UI settings entry; verify live GSC + GA4 against a real property.
- [ ] **Phase 2 — Clean UI shell & Settings**
- [ ] **Phase 3 — Backlink agent · Lane A (auto-publish)** ← main target
- [ ] **Phase 4 — Backlink agent · Lane B (guest outreach)**
- [ ] **Phase 5 — Content + SEO agent (volume path)**
- [ ] **Phase 6 — Opportunity Finder + optional Keyword engine**
- [ ] **Phase 7 — Orchestration & polish**

## Done so far
- Repo scaffold, `CLAUDE.md`, `PHASES.md`, this file.
- `core/` package + Streamlit app with 4 analysis views (seed-backed, live-ready).
- Six content skills in `.claude/skills/` (orchestrator, brand + competitor scrapers,
  keyword researcher, SEO/AEO/GEO writer, image generator, WordPress publisher) with
  pluggable image + keyword adapters (dummy defaults).

## Next up (start here)
Finish Phase 1's leftovers, then do **Phase 2 (clean UI shell & Settings)**. Read
`PHASES.md` → Phase 2, then `app.py` and `core/config.py`, before writing anything.

## Still needed from the user (pluggable, safe to defer)
- Image API name (currently dummy → writes image briefs).
- Keyword API name (optional; GSC-first works free).
- WordPress username + Application Password per site (for draft publishing).
- Confirm toolacademy.com is self-hosted WordPress.
- Email/SMTP for the optional guest-outreach send (else copy-paste pitches).
