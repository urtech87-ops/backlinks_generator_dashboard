"""
The settings *schema* — one place that describes every option the dashboard
knows about, in plain language.

`core/config.py` reads and writes the values; this file says what they are,
what to call them, and what to tell the user about them. The Settings page
renders itself from this, so adding an option in a later phase means adding a
Field here (and a line in `.env.example`) — not writing more UI.
"""

from dataclasses import dataclass, field as dc_field


@dataclass
class Field:
    key: str                       # .env key
    label: str                     # plain-language label
    help: str                      # one-line helper text under the input
    kind: str = "text"             # text | password | select
    options: tuple = ()            # for kind="select"
    option_labels: dict = dc_field(default_factory=dict)   # value -> plain-language name
    placeholder: str = ""
    secret: bool = False           # never echo the saved value back into the UI


@dataclass
class Group:
    key: str
    title: str
    blurb: str                     # one line: what this section is for
    fields: list = dc_field(default_factory=list)


# ── Per-site fields (rendered once per site, with its own prefix) ──────────
def site_fields(prefix: str, label: str) -> list[Field]:
    """Fields for one site. `prefix` is the site's env prefix, e.g. "TV"."""
    return [
        Field(f"{prefix}_GSC_PROPERTY", "Search Console property",
              f"Exactly as it appears in Search Console for {label} — "
              "usually the URL with a trailing slash.",
              placeholder="https://example.com/"),
        Field(f"{prefix}_SITEMAP", "Sitemap URL",
              "Where the dashboard finds the page list to check for indexing.",
              placeholder="https://example.com/sitemap_index.xml"),
        Field(f"{prefix}_GA4_ID", "GA4 property ID",
              "The numeric ID from GA4 → Admin → Property details. "
              "Leave blank if this site has no GA4 yet.",
              placeholder="480000000"),
        Field(f"{prefix}_HOMEPAGE", "Homepage",
              "Used to shorten URLs in tables and to build seed links.",
              placeholder="https://example.com/"),
        Field(f"{prefix}_WP_URL", "WordPress site URL",
              "Where drafts get created. Usually the same as the homepage, no trailing slash.",
              placeholder="https://example.com"),
        Field(f"{prefix}_WP_USERNAME", "WordPress username",
              "The WordPress user the dashboard posts drafts as."),
        Field(f"{prefix}_WP_APP_PASSWORD", "WordPress application password",
              "WP Admin → Users → Profile → Application Passwords. Not your login password.",
              kind="password", secret=True),
        Field(f"{prefix}_COMPETITORS", "Competitor sites",
              "Comma-separated domains the Opportunity Finder compares you against. "
              "Leave blank and it finds them by searching your niche instead.",
              placeholder="example.com, another-site.com"),
    ]


# ── Global groups ─────────────────────────────────────────────────────────
GOOGLE = Group(
    "google", "Google Search Console + Analytics",
    "One service account serves both APIs, and it is the step the whole dashboard "
    "stands on. Without it every number you see is sample data.",
    [
        Field("GOOGLE_SA_FILE", "Service-account JSON file",
              "Path to the downloaded key file, relative to the project folder. "
              "Add its client_email as a user in Search Console and GA4.",
              placeholder="config/service_account.json"),
    ],
)

MODELS = Group(
    "models", "AI models (per agent)",
    "One OpenRouter key, three model choices — cheap for analysis and backlinks, "
    "strongest for content.",
    [
        Field("OPENROUTER_API_KEY", "OpenRouter API key",
              "Used by the Analysis, Content and Backlink agents.",
              kind="password", secret=True),
        Field("ANALYSIS_MODEL", "Analysis agent model",
              "Reads Search Console + GA4 and triages pages. A cheap, fast model is fine.",
              kind="select"),
        Field("BACKLINK_MODEL", "Backlink agent model",
              "Drafts platform posts and outreach pitches. Cheap model, high volume.",
              kind="select"),
        Field("CONTENT_MODEL", "Content + SEO agent model",
              "Writes the articles that have to rank. Use the strongest model you have.",
              kind="select"),
    ],
)

CONTENT_TOOLS = Group(
    "content_tools", "Content tools (images + keywords)",
    "Both are pluggable and optional — left on 'dummy' the agents write briefs "
    "instead of calling an API, so nothing breaks.",
    [
        Field("IMAGE_API_PROVIDER", "Image provider",
              "'dummy' writes an image brief instead of generating a picture. "
              "Set this once you pick an image API.",
              placeholder="dummy"),
        Field("IMAGE_API_KEY", "Image API key",
              "Only needed when the provider above isn't 'dummy'.",
              kind="password", secret=True),
        Field("IMAGE_MODEL", "Image model",
              "The model name your image provider expects."),
        Field("KEYWORD_ENGINE", "Keyword engine",
              "Optional. On, it reads the queries you already rank for in Search Console, "
              "flags striking-distance terms and expands them with free Google "
              "autocomplete. Off, every page simply stops offering keyword data.",
              kind="select", options=("on", "off"),
              option_labels={"on": "On — Search Console first, autocomplete second",
                             "off": "Off — no keyword data anywhere"}),
        Field("KEYWORD_API_PROVIDER", "Keyword provider",
              "Optional. Search Console query data already gives you real keywords for free.",
              placeholder="dummy"),
        Field("KEYWORD_API_KEY", "Keyword API key",
              "Only needed when the keyword provider above isn't 'dummy'.",
              kind="password", secret=True),
    ],
)

PLATFORMS = Group(
    "platforms", "Owned backlink platforms",
    "Auto-publishing is only ever allowed on platforms you own. Guest posts stay "
    "human-approved.",
    [
        Field("DEVTO_API_KEY", "dev.to API key",
              "dev.to → Settings → Extensions → DEV Community API Keys.",
              kind="password", secret=True),
        Field("BLOGGER_BLOG_ID", "Blogger blog ID",
              "The numeric ID of your Blogger blog."),
        Field("BLOGGER_CLIENT_ID", "Blogger OAuth client ID",
              "From the Google Cloud project you set Blogger up in."),
        Field("BLOGGER_CLIENT_SECRET", "Blogger OAuth client secret",
              "Paired with the client ID above.", kind="password", secret=True),
        Field("BLOGGER_REFRESH_TOKEN", "Blogger refresh token",
              "Lets the agent post without you logging in each time.",
              kind="password", secret=True),
    ],
)

PROSPECTING = Group(
    "prospecting", "Guest-post prospecting (search)",
    "How Lane B finds sites that accept guest posts. DuckDuckGo needs no key and "
    "works out of the box; a paid provider is steadier if you prospect often.",
    [
        Field("SEARCH_API_PROVIDER", "Search provider",
              "Where prospect searches run. DuckDuckGo is free but can throttle a "
              "burst of queries.",
              kind="select",
              options=("duckduckgo", "serper", "serpapi", "brave"),
              option_labels={
                  "duckduckgo": "DuckDuckGo — free, no key (best effort)",
                  "serper": "Serper.dev — Google results, needs a key",
                  "serpapi": "SerpAPI — needs a key",
                  "brave": "Brave Search API — needs a key",
              }),
        Field("SEARCH_API_KEY", "Search API key",
              "Only needed when the provider above isn't DuckDuckGo.",
              kind="password", secret=True),
    ],
)

EMAIL = Group(
    "email", "Outreach email (optional)",
    "Only used to send guest-post pitches you have already read and approved, one "
    "click at a time. Leave it blank and Lane B still works — you copy the pitch and "
    "send it from your own mailbox.",
    [
        Field("OUTREACH_FROM_EMAIL", "Send pitches from",
              "The address hosts will see and reply to.",
              placeholder="you@example.com"),
        Field("OUTREACH_FROM_NAME", "Your name",
              "Used to sign the pitch and as the From name. Editors reply to people.",
              placeholder="Alex Smith"),
        Field("SMTP_HOST", "SMTP host",
              "Your mail provider's outgoing server.", placeholder="smtp.gmail.com"),
        Field("SMTP_PORT", "SMTP port",
              "587 for STARTTLS, 465 for SSL.", placeholder="587"),
        Field("SMTP_USER", "SMTP username",
              "Usually the same as the address above."),
        Field("SMTP_PASSWORD", "SMTP password",
              "An app password, not your main mailbox password.",
              kind="password", secret=True),
    ],
)

GROUPS = [GOOGLE, MODELS, CONTENT_TOOLS, PLATFORMS, PROSPECTING, EMAIL]

# Model pickers need a live option list, so the Settings page fills these in.
MODEL_FIELD_KEYS = ("ANALYSIS_MODEL", "BACKLINK_MODEL", "CONTENT_MODEL")
