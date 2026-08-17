---
name: competitor-site-scraper
description: Reads competitor websites to map the topics, questions, and FAQs they cover — and, more importantly, the ones they cover thinly or miss. Use this to find the content gap that becomes the user's opportunity and the angle for a new article. Trigger when the orchestrator asks for a competitor gap, or when the user says "what are competitors writing about", "find a content gap", or "what's my opportunity".
---

# Competitor Site Scraper

Produce a `competitor-gap.md` that tells the writer where the opening is. The goal
is not to copy competitors — it's to find the question they answer badly or not at all,
and own it better.

## Steps

1. **Resolve competitors.** Use the URLs given. If none, `web_search` the primary
   keyword and take the top 2–3 non-user domains that are direct competitors.

2. **Map their coverage.** For each competitor, fetch the sitemap or blog index and
   list the titles/slugs of posts related to the topic. Fetch 2–4 of the most
   relevant posts and note: which subtopics they cover, which questions they answer,
   their FAQ entries, their depth, and their freshness (last updated).

3. **Find the gap.** Compare against the research brief's real user questions.
   Identify: questions no competitor answers well, subtopics they treat thinly,
   outdated data you can beat with fresher figures, and formats they lack
   (no FAQ, no comparison, no worked example, no numbers).

4. **Pick the angle.** State in one line the specific angle the article should take
   to be more useful than what's ranking now.

## Guardrails

- Respect `robots.txt`; fetch politely with a delay; cap at ~3 competitors and
  ~4 pages each. This is analysis, not scraping at scale.
- Never reproduce competitor text. Summarize coverage in your own words. Record
  facts and figures only with their original source, not the competitor's wording.

## Output — `competitor-gap.md`

```
Competitors analyzed: <domains>
What they cover well: <bullets>
Gaps / weak spots:
  - <question or subtopic they miss or treat thinly>
  - <outdated stat you can beat, with the fresher source>
  - <missing format: FAQ / comparison / example / data>
Recommended angle: <one line — the specific way to be more useful>
```
