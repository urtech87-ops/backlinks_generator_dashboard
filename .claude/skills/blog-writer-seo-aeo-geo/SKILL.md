---
name: blog-writer-seo-aeo-geo
description: Writes a complete blog article optimized for traditional search (SEO), answer engines (AEO), and generative AI engines (GEO — getting cited by ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude). Takes a research brief, brand profile, competitor gap, and optional target keyword, and returns the article body plus a meta.json (title, meta title/description, slug, tags, categories, FAQ, schema). Use whenever the actual article needs writing to a standard that can rank AND be quoted by AI. Trigger from the orchestrator, or when the user says "write the article", "draft the blog post", or "make this SEO/AEO/GEO optimized".
---

# Blog Writer — SEO + AEO + GEO

Write one article that does three jobs at once: ranks in Google (SEO), gets pulled
into answer boxes (AEO), and gets cited by AI engines (GEO). These are now partly
separate games — the overlap between top Google links and AI-cited sources has fallen
well below a quarter — so the piece must satisfy all three, not just one.

## Non-negotiables (what actually moves the needle)

Based on the controlled GEO research (Princeton et al.) and current 2026 practice,
these are the levers that measurably increase AI citation — use them in every piece:

- **Statistics with a clear, cited source.** Every major claim backed by a real
  figure and a link to where it came from. (Biggest measured lift.)
- **Direct expert quotes with attribution.** One or two short, real, sourced quotes.
- **Explicit source citations** throughout — link out to primary sources.
- **Fluent, substantive language.** Do NOT keyword-stuff, pad, or "dumb down".
  Those were tested and do nothing.
- **Never fabricate** a stat, quote, or source. If research didn't find it, leave it out.

## Structure (write in this order)

1. **H1 / working title** — clear, includes the primary keyword naturally.

2. **Answer-first opening (~120–200 words).** The first paragraph must *directly and
   completely answer the primary question*, not warm up to it. Someone (or an AI)
   should get the full answer from the opening alone. This is the single most
   important AEO/GEO move.

3. **Body — question-shaped H2/H3 headings.** Phrase headings the way people ask
   ("How much does X cost?", "Is X worth it for small teams?"). Under each, lead with
   a **self-contained 40–60 word answer block** that stands alone if an engine lifts
   it, then expand.

4. **One worked, concrete example** — a realistic scenario, numbers included.

5. **Internal links** — link to the brand's relevant tool/product page(s) from the
   brand profile, with natural, varied anchor text (not "click here", not the raw URL).

6. **FAQ section (3–6 Q&As)** — real questions from the research brief, each answered
   in 2–4 tight sentences. This feeds FAQPage schema and AEO directly.

7. **Conclusion + CTA** — short, and a clear call to try the brand's free tool.

8. **Entity clarity** — name the brand consistently and describe it in one clean
   sentence somewhere natural; this helps AI attribute the content to the brand.

## Voice

Match the brand profile's tone and POV. Never use AI-doorway filler ("X introduces…",
"X is dedicated to…", "In today's fast-paced world…", "Look no further"). Never open
with a cliché. Vary sentence length. Write like a knowledgeable human, not a template.

## Length

Aim for depth, not a word count — usually 1,200–1,800 words for a pillar piece. If the
topic is fully answered in less, stop. Padding hurts (it was tested; it does nothing).

## Output — two files

**`article.md`** — the full post in Markdown, headings and internal/external links in place.

**`meta.json`:**
```json
{
  "title": "<H1>",
  "meta_title": "<<= 60 chars, keyword near front>",
  "meta_description": "<<= 155 chars, answers the query, invites the click>",
  "slug": "<short, 3-5 words, hyphenated, NO keyword stuffing>",
  "primary_keyword": "<...>",
  "tags": ["<5 max>"],
  "categories": ["<1-2 real categories>"],
  "faq": [{"q": "...", "a": "..."}],
  "schema": ["Article", "FAQPage"],
  "sources": [{"claim": "...", "url": "..."}],
  "internal_links": [{"anchor": "...", "url": "..."}],
  "date_modified": "<ISO date>"
}
```

## Slug rule (learned the hard way)

Keep slugs short and clean — 3–5 words. Long keyword-stuffed slugs like
`free-online-jpeg-png-webp-image-compressor-toolsvenue` are a low-quality signal on
their own and correlate with "Discovered – not indexed". If a target page already has
a stuffed slug, recommend a short replacement + 301 in the run report.

## Schema

Always recommend `Article` + `FAQPage` JSON-LD, and `HowTo` if the piece is a tutorial.
Include a fresh `dateModified` — recency is a ranking and citation signal.
