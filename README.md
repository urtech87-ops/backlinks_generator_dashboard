# SEO Command Center

A Streamlit dashboard that acts as the **conductor** for SEO + content work across
toolsvenue.com and toolacademy.com, driving three agents: **Analysis** (Search Console
+ GA4 triage and winner-ranking), **Content + SEO** (SEO/AEO/GEO writing → WordPress
drafts, in `.claude/skills/`), and **Backlink** (auto-publish to owned platforms +
human-gated guest outreach). Quality backlinks is the headline target; fixing indexing
and publishing genuinely useful content is what makes it work.

## Built in phases
This repo is designed to be built with **Claude Code**, one phase at a time. Start by
reading `CLAUDE.md`, then `PROGRESS.md` (current state), then `PHASES.md` (roadmap).

## Run
```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows/MINGW64
pip install -r requirements.txt
cp .env.example .env        # fill in what you have; blanks degrade gracefully
streamlit run app.py
```
Opens on the Fix Plan, populated from seed data now; connect Search Console + GA4 to go live.

## Layout
```
app.py              Streamlit entry (conductor)
core/               config, gsc, ga4, classifier, seed  (Analysis foundation)
agents/             analysis / backlink / content        (built in phases)
ui/                 clean UI helpers + pages             (Phase 2)
.claude/skills/     the SEO/AEO/GEO content agent (quality path)
CLAUDE.md           how Claude Code should work here
PHASES.md           the roadmap
PROGRESS.md         living status — paste into a fresh chat to resume
```
