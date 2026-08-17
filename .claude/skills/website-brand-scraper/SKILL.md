---
name: website-brand-scraper
description: Reads the user's own website to capture brand voice, the products/tools they offer, and the real internal URLs a new article should link to. Use this before writing any blog post so the piece sounds like the brand and links to the right pages. Trigger when the orchestrator asks for a brand profile, or when the user says "learn my site's voice", "what should I internally link to", or "make it sound like us".
---

# Website Brand Scraper

Produce a `brand-profile.md` the writer can rely on. Read a sample of the user's
own pages and extract voice, offering, and internal-link targets. Do not guess —
read actual pages.

## Steps

1. **Get the URL list.** Fetch the site's `sitemap.xml` / `sitemap_index.xml`
   (`web_fetch`). Collect tool/product URLs and the top existing blog posts.
   If no sitemap, crawl the homepage and main nav links only.

2. **Sample real pages.** Fetch 5–10 representative pages: homepage, 3–5 tool/product
   pages, 2–3 blog posts. Read them for how the brand actually writes.

3. **Extract voice.** Note tone (formal/casual), sentence length, whether it uses
   "you"/"we", jargon level, and any recurring phrasings. Capture 2–3 short sample
   sentences that typify the voice (paraphrase, don't lift long passages).

4. **Extract offering + entities.** List the tools/products with their exact page
   URLs and one-line descriptions. This is the internal-link menu — the writer must
   link to the most relevant tool page(s) with natural anchor text.

5. **Flag the brand entity.** Exact brand name, how it should be described in one
   sentence, and any tagline. Consistent entity naming helps AI engines attribute
   content to the brand (GEO).

## Guardrails

- **Do not** copy the site's AI-doorway filler if you find it (e.g. "X introduces…",
  "X is dedicated to…"). Note it as a phrase to avoid, not to imitate.
- Respect `robots.txt`; fetch politely (a short delay between requests); cap at ~15 pages.

## Output — `brand-profile.md`

```
Brand: <name>
One-liner: <how to describe the brand in a sentence>
Voice: <tone, POV, sentence length, jargon level>
Voice samples: <2-3 short paraphrased typifying lines>
Tools / products (internal-link menu):
  - <Tool name> — <url> — <one-line what it does>
  - ...
Phrases to avoid: <any filler/doorway patterns found on-site>
```
