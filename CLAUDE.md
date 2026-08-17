# CLAUDE.md — read this first, every time

This file is auto-loaded by Claude Code. It governs how you work in this repo.

## What this project is

An SEO + content **command center** for two sites (toolsvenue.com, toolacademy.com).
A Streamlit dashboard is the **conductor**. Under it run three agents:

- **Analysis agent** (OpenRouter, cheaper model) — reads Search Console + GA4, triages
  not-indexed pages, finds well-performing "winner" pages, spots gaps.
- **Content + SEO agent** (Claude / strongest model) — researches and writes
  SEO/AEO/GEO articles → WordPress drafts. Quality path lives in `.claude/skills/`.
- **Backlink agent** (OpenRouter, cheap model) — the user's MAIN TARGET. Two lanes:
  auto-publish to owned platforms, and human-gated guest-post outreach.

The user's real goal is quality backlinks, but growth actually comes from fixing
indexing and publishing genuinely useful content. Keep that honest framing.

## PRIME DIRECTIVE — before you write any code

1. **Read `PROGRESS.md`** — it tells you the current phase and what's done/left.
2. **Read `PHASES.md`** — do the phases in order; only work the current phase.
3. **Read the existing code** in the module(s) you're about to touch. Never rewrite
   working code you haven't read. Reuse `core/` (config, gsc, ga4, classifier, seed).
4. Do the phase's work. Keep changes scoped to that phase.
5. **On finishing a phase: update `PROGRESS.md`** — tick its checklist, move it to
   "done", write one line on what shipped, refresh "Next up" and the timestamp.

If a chat gets long, the user starts a fresh one and drops `PROGRESS.md` into it.
So `PROGRESS.md` must always be enough to resume without the chat history.

## Conventions

- Python 3.10, Streamlit. Run from repo root: `streamlit run app.py`.
- Imports are package-based: `from core import config, gsc, ga4, seed`. Do NOT
  flatten into loose files — keep the `core/`, `agents/`, `ui/` packages.
- Secrets live in `.env` (never commit it). New keys go in `.env.example` too.
- Fail soft: if a credential/API isn't set, degrade gracefully (seed data, briefs,
  disabled buttons) — never crash the dashboard.
- Per-agent model comes from settings/`.env` (e.g. `ANALYSIS_MODEL`, `BACKLINK_MODEL`,
  `CONTENT_MODEL`). Cheap for analysis/backlinks, strongest for content.

## Hard guardrails (do not violate)

- WordPress publishing is **always `status: draft`**. Never auto-publish live.
- Backlinks: auto-publish only to platforms the user OWNS (dev.to, Blogger, their WP).
- Guest posting: automate prospecting + drafting + tracking ONLY. A human approves the
  send and the host publishes. NEVER auto-post to third-party sites, and never build
  scaled/keyword-stuffed guest campaigns — that is a Google link-spam penalty.
- Never fabricate statistics, keyword volumes, or quotes. No data → say "unvalidated".
- Content quality over volume. Thin AI pages are what got the site de-indexed before.

## UI principle

The dashboard must be **clean and self-explanatory**. Every feature discoverable from
the sidebar; every option labeled in plain language with a one-line helper; sensible
empty/seed states; no raw jargon. The information architecture mirrors the system tree:
Overview → Analysis → Content → Backlinks → Settings.
