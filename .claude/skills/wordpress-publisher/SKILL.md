---
name: wordpress-publisher
description: Takes a finished article, its meta, and its images, and creates a WordPress DRAFT via the REST API — uploading images to the media library, setting the featured image, title, content, slug, excerpt (meta description), tags, and categories. Works with self-hosted WordPress (toolsvenue.com / toolacademy.com) using an Application Password. Always creates a draft, never auto-publishes. Trigger from the orchestrator as the final step, or when the user says "publish this to WordPress" or "create the draft".
---

# WordPress Publisher

Create a review-ready **draft** in WordPress. Never publish live automatically — the
user reviews first. Uses the standard self-hosted WP REST API with an Application
Password (Users → Profile → Application Passwords).

## Config (from project `.env`)

```
WP_SITE_URL=https://toolsvenue.com      # or https://toolacademy.com
WP_USERNAME=<your wp username>
WP_APP_PASSWORD=<application password, spaces kept or removed both work>
```

Pick the site from the article's `site` field so the same skill serves both sites.

## Steps

1. **Auth** — Basic auth header from `WP_USERNAME:WP_APP_PASSWORD` (base64).
2. **Upload images** — POST each image to `/wp-json/wp/v2/media` with its alt text.
   Keep the returned media `id`s. The featured image's id becomes `featured_media`.
3. **Resolve tags/categories** — look up or create tags and categories, collect ids.
4. **Create the draft** — POST to `/wp-json/wp/v2/posts` with `status: "draft"`,
   title, content (Markdown → HTML), slug, excerpt (= meta description),
   `featured_media`, tag ids, category ids.
5. **Return** the draft's edit URL: `<WP_SITE_URL>/wp-admin/post.php?post=<id>&action=edit`.

## Guardrails

- `status` is **always** `"draft"`. Do not set `publish`.
- If a media upload fails, continue with the post but report which image failed.
- Add the FAQ/Article JSON-LD from `meta.json` into the post (via a block or the
  site's SEO plugin fields if available). If you can't set schema via API, note it in
  the return so the user adds it on review.

## Reference implementation

A working, ready-to-run helper is bundled at `assets/publish.py`. It takes the
`content/` and `images/` folder from the orchestrator's output and creates the draft.
Adapt field names to the user's theme/plugins as needed.
