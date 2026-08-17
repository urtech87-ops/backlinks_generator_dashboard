---
name: content-agent-orchestrator
description: The manager skill for the SEO + AEO + GEO blog agent. Use this whenever the user gives a single blog topic (or a target page/keyword handed over from the SEO dashboard) and wants the whole pipeline run end to end — research, brand voice, competitor gap, a full SEO/AEO/GEO article, images, saved outputs, and a WordPress draft. Trigger on phrases like "write and publish a blog about X", "run the content agent on X", "turn this topic into a draft", or when a topic arrives from the dashboard's Opportunity Finder. This skill calls the five specialist skills in order; do not run them ad hoc when a full piece is requested.
---

# Content Agent Orchestrator

You are the manager. Given one topic, you run six steps in order, save everything
in a predictable place, and end with a WordPress draft. You call the specialist
skills — you do not reimplement them.

## Important reality (read first)

- There is **no** pre-existing `seo` skill in this environment. Do the research
  yourself with `web_search` and the two scraper skills. Ignore any instruction
  that says "use the seo skill".
- Quality beats volume. Thin, generic, auto-written content is exactly what gets
  "Crawled – currently not indexed" in Search Console. Every piece this agent
  produces must earn its place: real research, real sources, real internal links.
- Never fabricate statistics, quotes, or sources. If research turns up nothing
  solid on a claim, drop the claim.

## Inputs

- `topic` (required): the article subject, e.g. "How much does LLM optimization cost for small businesses?"
- `site` (default: the user's primary site): which brand/site this is for. Determines
  brand voice and internal-link targets.
- `competitors` (optional): 1–3 competitor URLs. If omitted, discover 2–3 during research.
- `primary_keyword` / `target_page` (optional): passed in when the dashboard hands
  over a keyword to reinforce or a well-performing page to support with a new article.

## Pipeline

Run these in order. After each step, write its output to disk (see Output layout)
before moving on, so nothing is lost if a later step needs a rerun.

1. **Research** — Use `web_search` to gather: the real questions people ask about
   the topic, 3–6 statistics each with a citable source, 1–3 quotable expert lines
   with attribution, and the current angle competitors take. Save a research brief.

2. **Brand voice + internal links** — Invoke **website-brand-scraper** on `site`.
   Get the brand's tone, the products/tools it offers, and the list of real internal
   URLs the article should link to (especially the relevant tool page).

3. **Competitor gap** — Invoke **competitor-site-scraper** on the competitors.
   Identify subtopics and questions they cover thinly or miss — that gap is the angle.

4. **Keyword research** — Invoke **keyword-researcher**. It builds the keyword brief
   GSC-first (the terms the site already ranks for, especially striking-distance ones),
   plus autocomplete/PAA and competitor keywords, and returns a primary keyword, a
   secondary/long-tail cluster, the real questions, intent, and a target page. This is
   what makes the content keyword-driven rather than guessed. Save `keyword-brief.md`.

5. **Write** — Invoke **blog-writer-seo-aeo-geo** with the research brief, brand
   profile, competitor gap, and the **keyword brief**. The primary keyword drives the
   title/H1/meta; the secondary cluster is worked in naturally; the questions become
   the FAQ. It returns `article.md` plus a `meta.json` (title, meta title/description,
   slug, tags, categories, FAQ, schema).

6. **Images** — Invoke **blog-image-generator** with the article and its headings.
   It returns a featured image + 1–2 in-body images with SEO filenames and alt text.
   (If no image API is configured yet, it writes image *briefs* instead and the
   pipeline continues — do not block on images.)

7. **Publish** — Invoke **wordpress-publisher** with the article, meta, and images.
   It uploads media and creates a **draft** (never auto-publish). Return the draft
   edit URL.

## Output layout

Save everything under a slugged folder so it's reusable and auditable:

```
outputs/<topic-slug>/
├── research/
│   ├── research-brief.md         # questions, stats+sources, quotes, angle
│   ├── brand-profile.md          # from website-brand-scraper
│   ├── competitor-gap.md         # from competitor-site-scraper
│   ├── keyword-brief.md          # from keyword-researcher (human-readable)
│   └── keywords.json             # primary + secondary cluster + questions + intent
├── content/
│   ├── article.md                # the post body
│   └── meta.json                 # title, meta, slug, tags, categories, faq, schema
└── images/
    ├── featured.png (or featured-brief.md)
    ├── inline-1.png
    └── alt-text.json
```

## Finish

End with a short run report: which steps ran, the output folder path, the WordPress
draft URL, and a one-line honest note on how strong the piece is (did research find
real stats/quotes, or is it thin — if thin, say so and suggest what to strengthen).

## How this fits the dashboard

The SEO dashboard decides **what** to write (gaps, keywords, pages worth supporting)
and handles points 1 and 2 (backlink targeting, opportunity finding). This agent is
the **quality writer** for the pages that matter. The dashboard's own content tab
handles high-volume drafts; use this skill when the piece needs to actually rank and
get cited.
