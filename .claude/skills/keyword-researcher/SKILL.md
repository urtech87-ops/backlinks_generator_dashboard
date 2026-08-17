---
name: keyword-researcher
description: Turns a topic or target page into a keyword brief the writer builds on — a primary keyword, a cluster of secondary and long-tail keywords, the real questions people ask, and search intent. Sources keywords GSC-first (the queries your pages already rank for, including striking-distance terms), plus free expansion (Google autocomplete, People Also Ask, competitor terms) and an optional pluggable paid keyword API. Use before writing so content targets real demand, not guesses. Trigger on "do keyword research", "find keywords for X", "competitor keywords", "which keywords should this page target", or from the orchestrator.
---

# Keyword Researcher

Produce a `keyword-brief.md` (+ `keywords.json`) so the article is built on keywords
with real demand. The honest rule: never invent search volumes. Rank by signals you
can actually verify — real GSC impressions, real autocomplete presence — and only show
volume/difficulty when a data source provides them.

## Sources, in priority order

1. **GSC Search Analytics (first-party, free) — use this first for an existing site.**
   Pull the `query` dimension (via the dashboard's `gsc.search_analytics(..., ["query"])`).
   From it, extract three gold seams:
   - **Already-ranking keywords** — terms the site gets impressions/clicks for.
   - **Striking-distance keywords** — average position ~5–20 with real impressions but
     low CTR. These are the fastest wins: one page already ranks, it just needs a push.
   - **Impression-rich, weak-page queries** — demand exists but the ranking page is thin
     → a content opportunity.

2. **Google autocomplete + People Also Ask + related searches (free).**
   Use `assets/keyword_adapter.py -> autocomplete_suggestions(seed)`. Captures the real
   phrasing and questions people use — feeds both keywords and the AEO/GEO FAQ section.

3. **Competitor keywords (free, approximate).**
   From `competitor-site-scraper` output, read rivals' titles, H1–H3s, meta, and repeated
   terms to infer the keywords they target. Note: this is their *targeting*, not their
   verified rankings/volumes — for those you need a paid source (below).

4. **Paid keyword API (optional, pluggable).**
   `assets/keyword_adapter.py -> get_metrics(keywords)` returns volume + difficulty when
   a provider is configured (DataForSEO, SEMrush, Ahrefs, Keywords Everywhere…). Dummy by
   default — returns no numbers rather than fake ones. The user names the tool later.

## Process

1. Gather seed + sources above.
2. Expand into candidates (autocomplete/PAA/related + GSC queries + competitor terms).
3. **Cluster** candidates by shared intent/topic.
4. Pick **1 primary** keyword + **5–15 secondary/long-tail** + **3–6 questions**.
5. Assign **intent** to each (informational / commercial / navigational).
6. Map the cluster to a **target page** — a new post, or an existing page to strengthen
   (prefer strengthening a striking-distance page when GSC shows one).

## Choosing the primary keyword (honest heuristic)

Best primary = real demand you can act on. Prefer, in order: a striking-distance GSC term
(fastest win) → a term with paid-API volume if available → an autocomplete-confirmed term
with clear intent. If none of these, mark the keyword **unvalidated** in the brief so the
user knows it's a guess, not data.

## Output

`keywords.json`:
```json
{
  "primary": {"keyword": "...", "intent": "...", "source": "gsc|autocomplete|api|competitor",
              "volume": null, "position_now": 12.4},
  "secondary": [{"keyword": "...", "intent": "...", "source": "...", "volume": null}],
  "questions": ["...", "..."],
  "target_page": "<new post | existing url to strengthen>",
  "notes": "striking-distance / unvalidated / etc."
}
```
Plus `keyword-brief.md` — a human-readable summary the writer reads. Hand `primary` and the
cluster to `blog-writer-seo-aeo-geo`; hand `questions` to its FAQ section.

## Feeds

- `blog-writer-seo-aeo-geo` — primary keyword + secondary cluster + questions.
- Opportunity Finder (dashboard) — which gaps have real demand.
- Backlink Targeter (dashboard) — which winning pages/keywords deserve links.
