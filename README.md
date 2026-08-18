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
cp .env.example .env        # optional — you can fill everything in from the UI
streamlit run app.py
```
Opens on the Overview, populated from seed data now. Blanks degrade gracefully: with no
credentials you still get the full Fix Plan from your 16 Aug Search Console snapshot.

## Setting it up
Everything is configured from **Settings** in the sidebar — sites, per-agent models, and
every API key — and saved to your local `.env` (git-ignored, chmod 600). Nothing needs
hand-editing.

1. **Settings → Google Search Console + Analytics** — point it at your service-account
   JSON, then grant that email access in Search Console (Settings → Users) and GA4
   (Admin → Property access management).
2. **Settings → Test connections** — checks the sitemap, Search Console access, Search
   Analytics, URL Inspection and GA4 separately, and names the step that failed.
3. **Refresh live data** in the sidebar — replaces the seed snapshot with live coverage.

## Building a backlink (Lane A)
**Settings → Backlink platforms** — add a dev.to API key, your four Blogger values, or a
WordPress application password. Then on **Backlinks → Auto-publish**:

1. **Pick the page you want links to.** Ranked by where a link does most good: pages
   within striking distance on real impressions, and pages Google has discovered but
   never crawled. Broken and quality-rejected pages aren't offered — a link there is
   wasted.
2. **Pick the platforms.** One article is written per platform, tailored to its audience.
3. **Generate**, then read it. The editor flags the target link: none is an error, more
   than one reads as link-building.
4. **Publish.** Tick *save as an unpublished draft* for a first run. Every attempt, live
   or failed, lands in `data/backlinks.csv`.

## Earning a guest post (Lane B)
Human-gated by design. The agent prospects, scores and writes; **you** approve every
send, and the host decides whether to publish. Nothing here can post to a site you
don't own. On **Backlinks → Guest outreach**:

1. **Pick the target page** — the same ranking Lane A uses.
2. **Find prospects.** Searches the phrases sites use when they *want* contributors
   (`"write for us"`, `"guest post guidelines"`, …) in your niche, reads each page, and
   scores it on relevance and on whether it looks editorially run. Sites that sell links
   are marked **skip** — buying links is a guidelines violation. You can also add a site
   by hand. Search runs through **Settings → Prospecting**: DuckDuckGo needs no key;
   Serper, SerpAPI or Brave are steadier.
3. **Shortlist** what's worth your time — saved to the tracker as *prospected*. Nothing
   has been contacted at this point.
4. **Draft** a personalised pitch and, if you want, the guest article itself. The pitch
   is checked for mail-merge and link-request wording before you send it.
5. **Approve and send.** With SMTP configured (**Settings → Outreach email**) you tick
   an approval box and send one pitch with one click; without it you copy the pitch and
   send it from your own mailbox. Either way you mark it, and the **outreach board**
   tracks prospected → pitched → accepted → live, declines included.

## Pages
| Page | What it's for |
|---|---|
| **Overview** | Indexing health, what to do next, what's connected |
| **Analysis** | Fix Plan, Indexing, Performance (GSC), Audience (GA4) |
| **Content** | The SEO/AEO/GEO writing path → WordPress drafts |
| **Backlinks** | Lane A auto-publish (owned platforms) · Lane B guest outreach |
| **Settings** | Sites, models, API keys, connection tests |

## Layout
```
app.py              Streamlit entry — sidebar + page dispatch
core/               config, settings schema, gsc, ga4, openrouter, classifier, seed,
                    tracker, search (prospecting), mailer (optional pitch send)
agents/             backlink.py (Lane A) · outreach.py (Lane B) · analysis / content
                    still to come
publishers/         one module per platform you own: dev.to, Blogger, your WordPress
ui/                 components + data loader + one module per page in views/
.claude/skills/     the SEO/AEO/GEO content agent (quality path)
CLAUDE.md           how Claude Code should work here
PHASES.md           the roadmap
PROGRESS.md         living status — paste into a fresh chat to resume
```

## Ground rules the code enforces
- WordPress publishing is **always a draft**.
- Auto-publishing only ever targets platforms you own; guest posts wait for your click.
- Outreach sends nothing by itself: one pitch, one approval, one click — and no scaled
  or keyword-stuffed campaigns.
- No fabricated statistics or keyword volumes — no data means it says so.
