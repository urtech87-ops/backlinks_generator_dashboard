---
name: blog-image-generator
description: Creates a featured image and 1–2 supporting images for a blog post, with SEO-friendly filenames and descriptive alt text. Uses a pluggable image API (configured by the user). If no image API is set yet, it writes detailed image briefs instead so the pipeline never blocks. Trigger from the orchestrator after the article is written, or when the user says "make images for this post" or "generate a featured image".
---

# Blog Image Generator

Produce images that help the post and its image SEO. Filenames and alt text matter
as much as the picture — they're what search and image search actually read.

## Configuration (one-time)

The image API is **pluggable** — the user names it and it's wired into the adapter
`generate_image(prompt, size)` (see `assets/image_adapter.py` once provided).
Common options: OpenAI Images / DALL·E, Stability, Replicate, Fal, or an
OpenRouter-hosted image model. Read the API key from the project `.env`
(e.g. `IMAGE_API_KEY`, `IMAGE_API_PROVIDER`).

**If no image API is configured**, do NOT stop the pipeline. Instead write
`images/*-brief.md` files (one per image) containing the prompt, intended size,
filename, and alt text, so the user can generate them manually or later. Report
"images: briefs only (no API configured)".

## What to create

1. **Featured image** — 1200×630 (social/OG friendly). Concept should reflect the
   article's core idea, clean and on-brand, no text baked in unless asked.
2. **1–2 in-body images** — illustrate a key section or the worked example.

## SEO rules (always apply, even for briefs)

- **Filename:** lowercase, hyphenated, describes the image and includes the primary
  keyword naturally, e.g. `llm-optimization-cost-small-business.png`. Never `image1.png`.
- **Alt text:** a real description of what's in the image (helps accessibility and
  image search), 8–15 words, keyword included only if it fits naturally.
- Save an `alt-text.json` mapping each filename to its alt text for the publisher.

## Prompt guidance

Write prompts that produce clean, modern, uncluttered visuals. Avoid: fake charts with
invented numbers, logos of real companies, recognizable real people, or anything that
implies data you don't have. Keep it illustrative, not misleading.

## Output

```
images/
├── <keyword-slug>-featured.png   (or -featured-brief.md if no API)
├── <keyword-slug>-inline-1.png   (or -brief.md)
└── alt-text.json
```
