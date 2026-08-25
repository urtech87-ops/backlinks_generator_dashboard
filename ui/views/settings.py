"""
Settings — every option in one place, in plain language.

Reads and writes the `.env` file through `core.config`, so nothing here needs
hand-editing a file. Secrets are write-only in the UI: once saved, the box
shows "saved" rather than the value, and leaving it blank keeps what's there.

The page is one section at a time, picked by a radio bound to `settings_section`
(Phase 8). That key is the deep link: any page can send you straight to the
section that fixes its problem — the sample-data banner targets 🔑 Google APIs,
the GA4 status row targets 🌐 Sites — which tabs could not do.
"""

import streamlit as st

from core import (config, ga4, gsc, mailer, openrouter, search,
                  settings as schema)
from ui import components as c


def render(ctx) -> None:
    c.page_header(
        "Settings",
        "Sites, models and API keys. Everything saves to your local .env file — "
        "which is git-ignored, so keys never leave this machine.",
    )

    exists = config.ENV_PATH.exists()
    c.show_badge("ok" if exists else "warn",
                 f".env {'found' if exists else 'will be created'} · {config.ENV_PATH}")
    st.write("")

    # Sections rather than tabs, because other pages deep-link into them: the
    # "Connect Search Console + GA4" button sets `settings_section` and lands
    # you on Google APIs instead of dropping you on Sites to go hunting.
    section = st.radio(
        "Which settings?", list(SECTIONS), key="settings_section", horizontal=True,
        help="Everything saves to your local .env file. Nothing is sent anywhere.",
    )
    st.caption(SECTION_HELP[section])
    st.divider()
    SECTIONS[section](ctx)


# ── Shared field rendering ─────────────────────────────────────────────────
def _field_input(field: schema.Field, default: str = ""):
    """
    Draw one setting, pre-filled with the value currently in effect (`default`
    covers settings that fall back to a built-in, like a site's sitemap URL).

    Returns the new value, or None meaning "leave unchanged" — used for secrets
    the user didn't retype.
    """
    saved = config.is_set(field.key)

    if field.kind == "select" and field.options:
        options = list(field.options)
        current = config.get(field.key, default or options[0])
        if current not in options:
            options.append(current)
        return st.selectbox(
            field.label, options, index=options.index(current),
            key=f"in_{field.key}", help=field.help,
            format_func=lambda v: field.option_labels.get(v, v),
        )

    if field.kind == "password" or field.secret:
        val = st.text_input(
            field.label, value="", type="password", key=f"in_{field.key}",
            help=field.help,
            placeholder="•••••••• saved — leave blank to keep it" if saved
                        else (field.placeholder or "not set yet"),
        )
        return val.strip() or None

    return st.text_input(field.label, value=config.get(field.key, default),
                         key=f"in_{field.key}", help=field.help,
                         placeholder=field.placeholder).strip()


def _save(values: dict, what: str) -> None:
    """Persist the non-skipped values and tell the user where they went."""
    updates = {k: v for k, v in values.items() if v is not None}
    if not updates:
        st.info("Nothing to save.")
        return
    path = config.save(updates)
    st.success(f"Saved {what} to {path}. Changes are live — no restart needed.")


def _group_tab(group: schema.Group) -> None:
    c.section(group.title, group.blurb)
    values = {f.key: _field_input(f) for f in group.fields}
    if st.button("💾 Save", key=f"save_{group.key}", type="primary"):
        _save(values, group.title.lower())


# ── Prospecting + outreach email ───────────────────────────────────────────
def _prospecting_tab(ctx=None) -> None:
    _group_tab(schema.PROSPECTING)

    st.caption(f"Currently prospecting with **{search.PROVIDERS[search.provider()]}**. "
               "Lane B only ever *reads* search results — it never posts anywhere.")
    if st.button("🔌 Test search", key="test_search",
                 help="Runs one real search so you know prospecting will work before "
                      "you rely on it."):
        with st.spinner("Running a test search…"):
            result = search.check()
        (st.success if result["ok"] else st.error)(result["detail"])


def _email_tab(ctx=None) -> None:
    _group_tab(schema.EMAIL)

    st.info("Email is optional and never automatic. The only thing that can send a "
            "pitch is the approval button on the Backlinks page, one pitch per click. "
            "Leave this blank and you copy the pitch instead.", icon="🛡️")
    gaps = mailer.missing()
    if gaps:
        st.caption(f"Not ready to send yet — still missing: {', '.join(gaps)}.")
    elif st.button("🔌 Test the mail login", key="test_smtp",
                   help="Connects and logs in. Sends nothing."):
        with st.spinner("Logging in to your mail server…"):
            result = mailer.check()
        (st.success if result["ok"] else st.error)(result["detail"])


# ── Sites ──────────────────────────────────────────────────────────────────
def _sites_tab(ctx=None) -> None:
    c.section("Your sites",
              "Which properties the dashboard watches, and where it files drafts. "
              "Add or remove sites in core/config.py → SITE_DEFAULTS.")
    site_tabs = st.tabs([s.label for s in config.SITES])
    for tab, site in zip(site_tabs, config.SITES):
        with tab:
            st.caption(f"Settings for **{site.label}** — stored as "
                       f"`{site.env_prefix}_*` keys in .env.")
            # Pre-fill with what's in effect now, so saving never blanks a
            # setting that was quietly using its built-in default.
            p = site.env_prefix
            in_effect = {
                f"{p}_GSC_PROPERTY": site.gsc_property,
                f"{p}_SITEMAP": site.sitemap_url,
                f"{p}_GA4_ID": site.ga4_property_id,
                f"{p}_HOMEPAGE": site.homepage,
                f"{p}_WP_URL": config.wp_credentials(site)["url"],
                f"{p}_WP_USERNAME": config.wp_credentials(site)["username"],
            }
            values = {}
            for field in schema.site_fields(p, site.label):
                values[field.key] = _field_input(field, in_effect.get(field.key, ""))
            if st.button("💾 Save site", key=f"save_site_{site.key}", type="primary"):
                _save(values, site.label)


# ── Google ─────────────────────────────────────────────────────────────────
def _google_tab(ctx) -> None:
    st.info("**This is step 1 of the whole dashboard.** One Google service-account file "
            "unlocks both Search Console (which pages are indexed, what they rank for) "
            "and GA4 (who actually turns up). Until it's here, every number you see is "
            "sample data.", icon="🔌")

    with st.expander("How to get the file, in four steps", expanded=not ctx.creds):
        st.markdown(
            "1. In **Google Cloud Console**, create a project (or open an existing one) "
            "and enable the **Search Console API** and the **Google Analytics Data API**.\n"
            "2. Under **IAM & Admin → Service Accounts**, create a service account and "
            "add a **JSON key**. Download it.\n"
            "3. Save that file inside this project folder — `config/service_account.json` "
            "is the default — and put its path in the box below.\n"
            "4. Grant the service account's email address access: in **Search Console → "
            "Settings → Users and permissions** (Full or Restricted), and in "
            "**GA4 → Admin → Property access management** (Viewer is enough)."
        )
        st.caption("The file never leaves this machine. Only its *path* is written to "
                   ".env.")

    _group_tab(schema.GOOGLE)

    email = config.service_account_email()
    if config.credentials_available():
        if email:
            st.success(f"Key file found. Grant this address access in both tools: "
                       f"`{email}`")
        else:
            st.warning("A file is there, but it isn't valid service-account JSON — "
                       "re-download the key from Google Cloud.")
    else:
        st.warning(f"No key file at `{config.service_account_file()}` yet, so the "
                   "dashboard is running on the sample snapshot and every live-only "
                   "view is empty.")

    _ga4_status()

    st.divider()
    c.section(f"Test connections · {ctx.site.label}",
              "Checks each API separately, so a failure tells you exactly which step "
              "to fix. Uses the site selected in the sidebar.")
    st.caption("The URL Inspection check makes one real API call, so it counts against "
               "your daily quota (2,000/day — this uses one).")

    if st.button("🔌 Run connection test", key="run_conn_test", type="primary"):
        site = ctx.site
        with st.spinner("Testing Search Console and GA4…"):
            checks = gsc.check_connection(site.gsc_property, site.sitemap_url,
                                          site.homepage)
            checks += ga4.check_connection(site.ga4_property_id)
        st.session_state["conn_checks"] = checks

    checks = st.session_state.get("conn_checks")
    if checks:
        c.check_list(checks)
        if all(chk["ok"] for chk in checks):
            st.success("All green. Press **Refresh live data** in the sidebar to replace "
                       "the sample snapshot with live coverage, then open the Overview.")
            c.nav_button("🏠 Back to the Overview", "Overview", key="conn_to_overview",
                         type="primary",
                         help="Your pages, ranked on real figures, with the buttons that "
                              "act on each one.")
        else:
            st.caption("Fix the red line above and run the test again — each check is "
                       "independent, so the first failure names the exact step.")


def _ga4_status() -> None:
    """
    GA4 gets its own line, because one key file is not the same as GA4 being
    readable: without a property ID per site there is nothing to query, and the
    dashboard must not report that as connected.
    """
    st.write("")
    c.section("Which sites can be read", "Search Console needs the property to match; "
                                         "GA4 additionally needs a numeric property ID "
                                         "per site.")
    rows = []
    for site in config.SITES:
        ready = config.ga4_ready(site)
        rows.append({
            "name": site.label,
            "state": "ok" if ready else ("warn" if config.credentials_available()
                                         else "idle"),
            "label": "GA4 ready" if ready else "no GA4 property ID",
            "detail": (f"Search Console: {site.gsc_property} · GA4 property "
                       f"{site.ga4_property_id}." if ready else
                       f"Search Console: {site.gsc_property} · no GA4 property ID saved, "
                       "so the Audience view stays empty for this site."),
        })
    c.status_rows(rows)
    st.button("Add a GA4 property ID", key="ga4_to_sites",
              on_click=lambda: st.session_state.update(settings_section="🌐 Sites"),
              help="Opens the Sites section, where each site's GA4 property ID lives.")


# ── Models ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60 * 60, show_spinner="Loading the model list from OpenRouter…")
def _model_options(key_present: bool) -> list:
    """
    OpenRouter's live catalogue, cached for an hour. [] if unreachable.
    `key_present` is part of the cache key so saving a key re-fetches the list.
    """
    return openrouter.list_models()


def _models_tab(ctx=None) -> None:
    group = schema.MODELS
    c.section(group.title, group.blurb)

    key_value = _field_input(group.fields[0])          # OPENROUTER_API_KEY

    live = _model_options(config.is_set("OPENROUTER_API_KEY"))
    if live:
        st.caption(f"Model list loaded live from OpenRouter — {len(live)} models available.")
    else:
        st.caption("Couldn't reach OpenRouter's model list, so these are offline "
                   "defaults. Pick **Other…** to paste any model id your key can call.")

    values = {group.fields[0].key: key_value}
    for field in group.fields[1:]:
        values[field.key] = _model_picker(field, live)

    col_save, col_test = st.columns([1, 3])
    with col_save:
        if st.button("💾 Save models", key="save_models", type="primary"):
            _save(values, "model settings")
    with col_test:
        if st.button("🔌 Test OpenRouter key", key="test_openrouter"):
            with st.spinner("Checking the key…"):
                result = openrouter.check_key()
            (st.success if result["ok"] else st.error)(result["detail"])

    st.caption("Rule of thumb: cheap models for analysis and backlinks (high volume, "
               "simple judgement), your strongest model for content (it has to rank).")


OTHER = "Other… (type it below)"


def _model_picker(field: schema.Field, live: list) -> str:
    """A dropdown of real model ids, with a free-text escape hatch."""
    current = config.get(field.key)
    suggested = openrouter.SUGGESTED.get(field.key, "")
    catalogue = live or openrouter.FALLBACK_MODELS
    options = sorted({*catalogue, *(x for x in (current, suggested) if x)})
    options.append(OTHER)

    index = options.index(current) if current in options else len(options) - 1
    choice = st.selectbox(field.label, options, index=index,
                          key=f"pick_{field.key}", help=field.help)
    if choice == OTHER:
        choice = st.text_input(f"{field.label} — model id",
                               value=current, key=f"other_{field.key}",
                               placeholder="vendor/model-name",
                               help="Any id OpenRouter accepts.").strip()
    if suggested and choice != suggested:
        st.caption(f"Suggested for this agent: `{suggested}`")
    return choice


# ── The sections, in the order you'd set them up ───────────────────────────
# Keys double as the labels on the picker, so a deep link is just the label.
SECTIONS = {
    "🌐 Sites": _sites_tab,
    "🔑 Google APIs": _google_tab,
    "🤖 AI models": _models_tab,
    "🎨 Content tools": lambda ctx=None: _group_tab(schema.CONTENT_TOOLS),
    "🔗 Backlink platforms": lambda ctx=None: _group_tab(schema.PLATFORMS),
    "🔎 Prospecting": _prospecting_tab,
    "✉️ Outreach email": _email_tab,
}

SECTION_HELP = {
    "🌐 Sites": "One entry per site: the exact Search Console property, the sitemap the "
               "page list is read from, the GA4 property ID, and where WordPress drafts "
               "are filed.",
    "🔑 Google APIs": "The one service-account file that unlocks both Search Console and "
                     "GA4 — the step everything else in this dashboard stands on.",
    "🤖 AI models": "One OpenRouter key, three model choices. Cheap models for analysis "
                   "and backlinks; your strongest model for content that has to rank.",
    "🎨 Content tools": "Images and keywords. Both optional — left unset, the agents write "
                       "image briefs and skip search volumes rather than inventing either.",
    "🔗 Backlink platforms": "Accounts you own, and the only places this app may publish "
                            "by itself.",
    "🔎 Prospecting": "How guest-post prospects are searched for. Read-only: prospecting "
                     "never contacts anyone.",
    "✉️ Outreach email": "Optional. The only thing that can ever send is the approval "
                        "button on the Backlinks page, one pitch at a time.",
}
