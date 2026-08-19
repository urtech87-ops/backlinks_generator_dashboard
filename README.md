# SEO Command Center

A Streamlit dashboard that acts as the **conductor** for SEO and content work across
toolsvenue.com and toolacademy.com. It runs three agents under one roof:

| Agent | Model | What it does |
|---|---|---|
| **Analysis** | cheap (`ANALYSIS_MODEL`) | Reads Search Console + GA4, sorts every page into what it actually needs, and ranks what to do first |
| **Content + SEO** | strongest (`CONTENT_MODEL`) | Researches and writes SEO/AEO/GEO articles → WordPress **drafts** |
| **Backlink** | cheap (`BACKLINK_MODEL`) | Two lanes: auto-publish to platforms you own, and human-gated guest outreach |

Quality backlinks are the headline target. Fixing indexing and publishing genuinely
useful content is what makes them work — so the dashboard puts them in that order, even
when links are the thing you came for.

## Run it

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows/MINGW64
pip install -r requirements.txt
cp .env.example .env        # optional — you can fill everything in from the UI
streamlit run app.py
```

It opens on the **Overview**, already populated: with no credentials at all you get the
full Fix Plan from your real 16 August Search Console snapshot. Every missing key
degrades to a stated fallback — seed data, an image brief, a disabled button — never a
crash.

## The loop it's built around

```
Overview  →  run the analysis  →  an ordered list of what to do
                                      │
      ┌───────────────────────────────┼───────────────────────────────┐
      ▼                               ▼                               ▼
  🔴 fix / 🗑️ clear              🟠 rewrite · 🎯 strengthen        🟢 build links
  → Analysis (Fix Plan,          → Content, topic + keyword       → Backlinks, target
    filtered, page called out)     + direction filled in            page preselected
```

**Overview** is the conductor. Press **Run the analysis** and it reads your coverage,
your Search Console performance and the queries you already rank for, then sorts every
page into one of five things it needs — fix the URL, rewrite it, delete or noindex it,
build links to it, strengthen it for a keyword. Open a step and each page carries the
button that does the job, on the page that does it. Nothing is written or published from
Overview; it hands the work over with the boxes already filled in.

The order is deliberate and it is not the flattering one: broken URLs first, then
rejected content, then crawl budget, then links. A backlink to a page Google hasn't
indexed does nothing.

## Pages

| Page | What it's for |
|---|---|
| **🏠 Overview** | Run the analysis · indexing health · what to do next, with the button that does it · system status |
| **🔍 Analysis** | Fix Plan (filterable, per-bucket actions) · Indexing · Performance (GSC) · Audience (GA4) |
| **💡 Opportunities** | Content gaps from competitors + your own coverage · the optional keyword engine |
| **✍️ Content** | Topic → research → SEO/AEO/GEO article → images → WordPress **draft** |
| **🔗 Backlinks** | Lane A auto-publish (owned platforms) · Lane B guest outreach (you approve) |
| **⚙️ Settings** | Sites, per-agent models, every API key, connection tests |

Everything is reachable from the sidebar, and the sidebar also carries the site picker,
the date range, **Refresh live data**, and a plain list of what the app will never do.

## Setting it up

All configuration lives on **Settings** and saves to your local `.env` (git-ignored,
`chmod 600`). Nothing needs hand-editing, and a blank box means "use the built-in
default" rather than "wipe this setting".

1. **Settings → Google APIs** — point it at your service-account JSON, then grant that
   email access in Search Console (Settings → Users) and GA4 (Admin → Property access
   management).
2. **Settings → Test connections** — checks the sitemap, Search Console access, Search
   Analytics, URL Inspection and GA4 separately, and names the step that failed.
3. **Refresh live data** in the sidebar — replaces the seed snapshot with live coverage
   (one URL Inspection call per URL, so it takes a minute on a big site).
4. **Settings → AI models** — an OpenRouter key, then a model per agent. Cheap for
   Analysis and Backlinks; your strongest model for Content, because it has to rank.
5. Optional as you need them: WordPress application passwords per site, dev.to /
   Blogger keys, a search API key, SMTP for outreach, an image API, a keyword API.

## Writing an article

**Content** is the volume path: a topic goes in, the agent searches the web, writes the
article and its meta with `CONTENT_MODEL`, makes the images (or their briefs), and files
a WordPress **draft**.

1. **Topic**, optionally a primary keyword — or pull one from your real Search Console
   queries with the keyword engine. Pick the indexed pages it should link to (rejected
   pages aren't offered; linking to them spreads the problem).
2. **Research and write.** If search fails, the piece is written qualitatively and the
   page says so — it will not invent a statistic to fill the gap.
3. **Read the checks.** They're the writer skill's own rules applied in code: answer-first
   opening, question-shaped headings, an FAQ, meta lengths, a short slug, internal links,
   and every cited URL traced back to research this run actually found. A source the run
   never saw is flagged red and blocks the draft until you tick past it.
4. **File it.** Always `status: draft`. The run is also saved to `outputs/<slug>/` —
   article.md, meta.json, the research brief and the images.

The deeper **quality path** is the seven skills in `.claude/skills/`. Run them from Claude
Code in this folder ("run the content agent on X"); they read the same `.env`, and they
enforce the same standard the dashboard checks.

## Building a backlink (Lane A)

**Settings → Backlink platforms** — a dev.to API key, your four Blogger values, or a
WordPress application password. Then on **Backlinks → Auto-publish**:

1. **Pick the page you want links to.** Ranked by where a link does most good: pages
   within striking distance on real impressions, and pages Google has discovered but
   never crawled. Broken and quality-rejected pages aren't offered.
2. **Pick the platforms.** One article per platform, tailored to its audience — the same
   text twice is duplicate content.
3. **Generate**, then read it. The editor counts the target link: none is an error, more
   than one reads as link-building.
4. **Publish.** Tick *save as an unpublished draft* for a first run. Every attempt, live
   or failed, lands in `data/backlinks.csv`.

## Earning a guest post (Lane B)

Human-gated by design. The agent prospects, scores and writes; **you** approve every
send, and the host decides whether to publish. On **Backlinks → Guest outreach**:

1. **Pick the target page** — the same ranking Lane A uses.
2. **Find prospects.** Searches the phrases sites use when they *want* contributors
   (`"write for us"`, `"guest post guidelines"`, …), reads each page, and scores it on
   relevance and on whether it looks editorially run. Sites that sell links are forced to
   **skip** — buying links is a guidelines violation, not a cheaper option. You can add a
   site by hand. There is no domain-authority number anywhere, because nothing here can
   measure one.
3. **Shortlist** what's worth your time — saved to the tracker as *prospected*. Nothing
   has been contacted yet.
4. **Draft** a personalised pitch and, if you want, the guest article. The pitch is
   checked for mail-merge and link-request wording first.
5. **Approve and send.** With SMTP configured you tick an approval box and send one pitch
   with one click; without it you copy the pitch and send it yourself. Either way you mark
   it, and the board tracks prospected → pitched → accepted → live, declines kept on
   purpose so you don't pitch the same editor twice.

## Deciding what to write

**Opportunities** is the answer to "I don't know what to write". It scans competitors
(their sitemap plus a `site:` search, robots-respecting, capped at 3 sites / 4 pages),
your own coverage and your Search Console queries, and returns a ranked list of four
kinds of opportunity — striking distance, competitor gap, tool with no article,
rejected-on-quality rewrite — each with the evidence behind it and a button that hands it
to the writer or the backlink targeter.

Its **Keywords** tab is the optional keyword engine: Search Console first (the queries you
already rank for, striking-distance terms flagged), free Google autocomplete second, a
paid API only if you plug one in. It can be switched off in Settings, and every page says
so plainly when it is.

## Layout

```
app.py              Streamlit entry — sidebar + page dispatch
core/               config (reads and writes .env), settings schema, gsc, ga4,
                    openrouter, classifier, seed, tracker, search, mailer, images,
                    keywords (the optional keyword engine)
agents/             analysis.py    the triage Overview conducts from
                    content.py     topic → research → article → WordPress draft
                    backlink.py    Lane A: rank targets, draft, publish
                    outreach.py    Lane B: prospect, score, pitch, guest article
                    opportunity.py competitor + coverage gap finder
publishers/         one module per platform you own: dev.to, Blogger, your WordPress
ui/                 components (headers, badges, metric rows, readiness strips, empty
                    states), the shared data loader, one module per page in views/
data/               backlinks.csv — both lanes, one row per event (git-ignored)
outputs/            what the content agent wrote (git-ignored — it's your content)
.claude/skills/     the seven-skill content agent (the quality path)
CLAUDE.md           how Claude Code should work here
PHASES.md           the roadmap · PROGRESS.md  living status
```

## Ground rules the code enforces

- **WordPress publishing is always a draft.** `publishers/wordpress.py` hard-codes it.
- **Auto-publishing only ever targets platforms you own.** `publishers/PLATFORMS` is the
  complete list of destinations and has no third-party entry, so there is no code path
  that posts to someone else's site.
- **Guest posts wait for you.** The only outbound action in Lane B is one email, sent one
  at a time, after an explicit approval tick.
- **No fabricated numbers.** No performance data means the ordering says it's
  unvalidated; no keyword volume means the word "unvalidated" is printed where the number
  would go; a cited source that the research run never found is flagged red.
- **Links come last.** Broken URLs, then rewrites, then crawl budget, then links —
  everywhere in the app, because that's the order that actually works.
- **Your keys stay on your machine.** Everything saves to the local `.env`.

## Built in phases

This repo was built with **Claude Code**, one phase at a time: foundation and analysis →
UI shell and settings → backlinks Lane A → backlinks Lane B → the content agent →
Opportunity Finder and keyword engine → orchestration and polish. All seven are done;
`PROGRESS.md` is the living record and is written to be pasted into a fresh chat.
