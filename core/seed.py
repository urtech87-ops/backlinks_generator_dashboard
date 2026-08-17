"""
Seed data = your ACTUAL Search Console state, transcribed from the 6 screenshots
you sent (16 Aug 2026). The dashboard uses this so the Fix Plan is populated and
useful on day one — before you finish the GSC/GA4 API setup. Once live data is
connected, live data takes over automatically and this is just a fallback.

Each entry: (path, coverage_state). Domain is added per-site at load time.
Only toolsvenue has a seed; the new site starts empty until its APIs are live.
"""

TOOLSVENUE_SEED = [
    # ── Page with redirect (17) ────────────────────────────────────────────
    ("/home/ai-code-explainer", "Page with redirect"),
    ("/blogs/category/youtube-social-media-tools/", "Page with redirect"),
    ("/category/youtube-tools/", "Page with redirect"),
    ("/blogs/blog-headline-generator/", "Page with redirect"),
    ("/grammar-checker", "Page with redirect"),
    ("/author/zain/", "Page with redirect"),
    ("/ai-code-explainer/ai-youtube-idea-generator", "Page with redirect"),
    ("/home/", "Page with redirect"),
    ("/home/ai-youtube-idea-generator", "Page with redirect"),
    ("/blogs/age-calculator/", "Page with redirect"),
    ("/blogs/author/admin/", "Page with redirect"),
    ("/javascript-beautifier", "Page with redirect"),
    ("/blogs/workout-plan-generator/", "Page with redirect"),
    ("/blogs/category/text-conversion-tools/", "Page with redirect"),
    ("/blogs/how-to-rewrite-articles-like-a-pro-without-losing-meaning-or-quality/", "Page with redirect"),
    ("/blogs/youtube-thumbnail-ideas/", "Page with redirect"),
    ("/blogs/category/uncategorized/", "Page with redirect"),

    # ── Redirect error (9) ─────────────────────────────────────────────────
    ("/privacy-policy/privacy-policy", "Redirect error"),
    ("/currency-converter", "Redirect error"),
    ("/sample-page/", "Redirect error"),
    ("/image-watermarker/contact-us", "Redirect error"),
    ("/css-minifier/", "Redirect error"),
    ("/ai-article-rewriter/", "Redirect error"),
    ("/json-formatter", "Redirect error"),

    # ── Not found 404 (6) ──────────────────────────────────────────────────
    ("/*", "Not found (404)"),
    ("/blogs/category/image-media-tools/", "Not found (404)"),
    ("/blogs/category/ai-content-tools/", "Not found (404)"),
    ("/ascii-art-generator/contact-us", "Not found (404)"),
    ("/wp-*.php", "Not found (404)"),
    ("/author/admin/", "Not found (404)"),

    # ── Crawled - currently not indexed (11) ───────────────────────────────
    ("/youtube-thumbnail-ideas/", "Crawled - currently not indexed"),
    ("/color-palette-generator/", "Crawled - currently not indexed"),
    ("/image-watermarker/", "Crawled - currently not indexed"),
    ("/color-contrast-checker/", "Crawled - currently not indexed"),
    ("/html-minifier/", "Crawled - currently not indexed"),
    ("/youtube-hashtag-generator/", "Crawled - currently not indexed"),
    ("/bmi-calculator/", "Crawled - currently not indexed"),
    ("/blogs/why-every-developer-needs-a-json-formatter-clean-code-faster-debugging/", "Crawled - currently not indexed"),
    ("/feed/", "Crawled - currently not indexed"),
    ("/blogs/author/zain/", "Crawled - currently not indexed"),
    ("/blogs/category/developer-code-tools/", "Crawled - currently not indexed"),

    # ── Discovered - currently not indexed (10) ────────────────────────────
    ("/age-calculator-more-than-just-numbers-heres-why-we-all-love-counting-age/", "Discovered - currently not indexed"),
    ("/categories/ai-tools/", "Discovered - currently not indexed"),
    ("/categories/developer-tools/", "Discovered - currently not indexed"),
    ("/categories/images-tools/", "Discovered - currently not indexed"),
    ("/categories/text-tools/", "Discovered - currently not indexed"),
    ("/compress-pdf/", "Discovered - currently not indexed"),
    ("/free-ai-code-explainer-understand-any-code-in-seconds-toolsvenue/", "Discovered - currently not indexed"),
    ("/free-online-jpeg-png-webp-image-compressor-toolsvenue/", "Discovered - currently not indexed"),
    ("/html-beautifier-online-format-indent-clean-your-html-code-instantly/", "Discovered - currently not indexed"),
    ("/image-to-pdf-converter/", "Discovered - currently not indexed"),
]

# Duplicate-slug watch: clean tool URL vs. an old keyword-stuffed one for the
# same tool. Pick one, 301 the other, or they cannibalise each other in search.
SUSPECTED_DUPLICATES = [
    ("/compress-pdf/", "/free-online-jpeg-png-webp-image-compressor-toolsvenue/"),
    ("/html-minifier/", "/html-beautifier-online-format-indent-clean-your-html-code-instantly/"),
    ("/ai-code-explainer", "/free-ai-code-explainer-understand-any-code-in-seconds-toolsvenue/"),
]

SEED_BY_SITE = {
    "toolsvenue": TOOLSVENUE_SEED,
}


def seed_rows(site_key: str, homepage: str):
    """Return [(full_url, coverage_state), ...] for a site's seed, or []."""
    base = homepage.rstrip("/")
    return [(base + path, cov) for path, cov in SEED_BY_SITE.get(site_key, [])]
