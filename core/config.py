"""
Central config for the SEO Command Center.

Loads credentials + per-site settings from a .env file so nothing sensitive
lives in code. Mirrors the service-account pattern you already use for the
Google Sheets bot.

Phase 2 added a *writable* layer: the Settings page reads values through
`get()` and saves them with `save()`, which rewrites `.env` in place
(preserving your comments and ordering) and reloads everything, so you never
have to hand-edit the file.
"""

import json
import os
import re
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

# .env sits at the project root (one level up from this file's folder)
ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)

# Read-only is all we need and safer for a dashboard.
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

DEFAULT_SA_FILE = "config/service_account.json"


# ── Reading values ─────────────────────────────────────────────────────────
def get(key: str, default: str = "") -> str:
    """
    Current value of a setting (from .env / the process environment).
    A blank value counts as "not set", so clearing a box in Settings falls back
    to the built-in default rather than leaving the app with an empty URL.
    """
    val = (os.environ.get(key) or "").strip()
    return val or default


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key, "").lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def is_set(key: str) -> bool:
    """True when a value exists and isn't one of our placeholders."""
    val = get(key)
    return bool(val) and val.upper() != "REPLACE_ME_LATER"


def resolve_path(value: str) -> Path:
    """Settings hold paths relative to the repo root; make them absolute."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (ROOT / p)


def service_account_file() -> str:
    return str(resolve_path(get("GOOGLE_SA_FILE", DEFAULT_SA_FILE)))


def credentials_available() -> bool:
    """True when the Google service-account JSON is actually on disk."""
    return Path(service_account_file()).exists()


def service_account_email() -> str:
    """
    The client_email inside the service-account JSON — the address you have to
    grant access to in Search Console and GA4. "" if the file is missing or
    isn't valid JSON.
    """
    try:
        with open(service_account_file(), encoding="utf-8") as fh:
            return json.load(fh).get("client_email", "")
    except Exception:
        return ""


# Kept for older imports; refreshed by reload().
SERVICE_ACCOUNT_FILE = service_account_file()


# ── Sites ──────────────────────────────────────────────────────────────────
@dataclass
class Site:
    """One property you want to monitor."""
    key: str                    # short id used in the UI dropdown
    label: str                  # human name
    env_prefix: str             # .env key prefix, e.g. "TV" -> TV_GSC_PROPERTY
    gsc_property: str           # exact Search Console property, e.g. "https://toolsvenue.com/"
    ga4_property_id: str = ""   # GA4 numeric property id, e.g. "480000000" (blank = no GA4 yet)
    sitemap_url: str = ""       # used to discover the URL list for inspection
    homepage: str = ""          # used for a couple of heuristics


# Add or edit sites here. Everything else about them is editable in Settings.
SITE_DEFAULTS = [
    {
        "key": "toolsvenue", "label": "ToolsVenue", "env_prefix": "TV",
        "gsc_property": "https://toolsvenue.com/",
        "sitemap_url": "https://toolsvenue.com/sitemap_index.xml",
        "homepage": "https://toolsvenue.com/",
    },
    {
        "key": "toolacademy", "label": "ToolAcademy", "env_prefix": "TA",
        "gsc_property": "https://toolacademy.com/",
        "sitemap_url": "https://toolacademy.com/sitemap_index.xml",
        "homepage": "https://toolacademy.com/",
    },
]


def _build_sites() -> list[Site]:
    sites = []
    for d in SITE_DEFAULTS:
        p = d["env_prefix"]
        sites.append(Site(
            key=d["key"],
            label=d["label"],
            env_prefix=p,
            gsc_property=get(f"{p}_GSC_PROPERTY", d["gsc_property"]),
            ga4_property_id=get(f"{p}_GA4_ID", ""),
            sitemap_url=get(f"{p}_SITEMAP", d["sitemap_url"]),
            homepage=get(f"{p}_HOMEPAGE", d["homepage"]),
        ))
    return sites


SITES: list[Site] = _build_sites()
SITES_BY_KEY = {s.key: s for s in SITES}


def ga4_ready(site: Site) -> bool:
    """
    True when GA4 can actually be queried for this site — the key file AND a
    property ID. Kept separate from `credentials_available()` on purpose: one
    service account serves both APIs, but a site with no GA4 property ID is not
    connected to GA4, and the UI must not claim it is.
    """
    return bool(credentials_available() and site.ga4_property_id)


def wp_credentials(site: Site) -> dict:
    """
    WordPress details for one site, with a fallback to the single legacy
    WP_* keys (which the standalone publisher skill still reads).
    """
    p = site.env_prefix
    return {
        "url": (get(f"{p}_WP_URL") or get("WP_SITE_URL", site.homepage)).rstrip("/"),
        "username": get(f"{p}_WP_USERNAME") or get("WP_USERNAME"),
        "app_password": get(f"{p}_WP_APP_PASSWORD") or get("WP_APP_PASSWORD"),
    }


# ── Writing values ─────────────────────────────────────────────────────────
_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _format_line(key: str, value: str) -> str:
    # Quote only when the value would otherwise be ambiguous.
    if value != value.strip() or any(c in value for c in "#\"'"):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def save(updates: dict) -> Path:
    """
    Write settings to `.env`, keeping existing comments, ordering and any keys
    we don't manage. New keys are appended at the end. Returns the .env path.
    """
    updates = {k: ("" if v is None else str(v)) for k, v in updates.items()}

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    if not lines and not ENV_PATH.exists() and (ROOT / ".env.example").exists():
        # First run: start from the documented template so comments survive.
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()

    seen = set()
    out = []
    for line in lines:
        m = _KEY_RE.match(line)
        key = m.group(1) if m else None
        if key in updates and key not in seen:
            out.append(_format_line(key, updates[key]))
            seen.add(key)
        else:
            out.append(line)

    missing = [k for k in updates if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# ---- Added from the dashboard Settings page ----")
        out.extend(_format_line(k, updates[k]) for k in missing)

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        ENV_PATH.chmod(0o600)          # secrets — keep them to the owner
    except OSError:
        pass                            # non-POSIX filesystem: not fatal

    # Apply immediately so the running app doesn't need a restart.
    for k, v in updates.items():
        os.environ[k] = v
    reload()
    return ENV_PATH


def reload() -> None:
    """Re-read .env and rebuild the derived config (sites, SA path)."""
    global SITES, SITES_BY_KEY, SERVICE_ACCOUNT_FILE
    load_dotenv(ENV_PATH, override=True)
    SITES = _build_sites()
    SITES_BY_KEY = {s.key: s for s in SITES}
    SERVICE_ACCOUNT_FILE = service_account_file()
