"""
Central config for the SEO Command Center.

Loads credentials + per-site settings from a .env file so nothing sensitive
lives in code. Mirrors the service-account pattern you already use for the
Google Sheets bot.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

# .env sits at the project root (one level up from this file's folder)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Read-only is all we need and safer for a dashboard.
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

# Path to the Google service-account JSON (same account can serve both APIs
# once you grant it access in GSC and GA4 — see README).
SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SA_FILE", str(ROOT / "config" / "service_account.json")
)


@dataclass
class Site:
    """One property you want to monitor."""
    key: str                    # short id used in the UI dropdown
    label: str                  # human name
    gsc_property: str           # exact Search Console property, e.g. "https://toolsvenue.com/"
    ga4_property_id: str = ""   # GA4 numeric property id, e.g. "480000000" (blank = no GA4 yet)
    sitemap_url: str = ""       # used to discover the URL list for inspection
    homepage: str = ""          # used for a couple of heuristics


# Add or edit sites here. The new site can start with just a GSC property.
SITES: list[Site] = [
    Site(
        key="toolsvenue",
        label="ToolsVenue",
        gsc_property=os.environ.get("TV_GSC_PROPERTY", "https://toolsvenue.com/"),
        ga4_property_id=os.environ.get("TV_GA4_ID", ""),
        sitemap_url=os.environ.get("TV_SITEMAP", "https://toolsvenue.com/sitemap_index.xml"),
        homepage="https://toolsvenue.com/",
    ),
    Site(
        key="toolacademy",
        label="ToolAcademy",
        gsc_property=os.environ.get("TA_GSC_PROPERTY", "https://toolacademy.com/"),
        ga4_property_id=os.environ.get("TA_GA4_ID", ""),
        sitemap_url=os.environ.get("TA_SITEMAP", "https://toolacademy.com/sitemap_index.xml"),
        homepage="https://toolacademy.com/",
    ),
]

SITES_BY_KEY = {s.key: s for s in SITES}


def credentials_available() -> bool:
    return Path(SERVICE_ACCOUNT_FILE).exists()
