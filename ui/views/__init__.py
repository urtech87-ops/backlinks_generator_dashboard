"""
One module per sidebar page. Each exposes `render(ctx)`.

`Ctx` is everything the sidebar has already decided — which site you're looking
at, the date range, and whether Google credentials exist — so pages never have
to re-ask.
"""

from dataclasses import dataclass

from core import config


@dataclass
class Ctx:
    site: config.Site
    start: str          # ISO date, inclusive
    end: str            # ISO date, inclusive
    creds: bool         # Google service-account JSON present?


from . import (overview, analysis, opportunities, content, backlinks,  # noqa: E402
               settings)

# Sidebar order mirrors the system tree: data → decide → do → configure.
PAGES = {
    "Overview": ("🏠", overview.render,
                 "Where both sites stand and what to do next"),
    "Analysis": ("🔍", analysis.render,
                 "Fix Plan, indexing, performance and audience"),
    "Opportunities": ("💡", opportunities.render,
                      "Content gaps from competitors, plus your real keywords"),
    "Content": ("✍️", content.render,
                "Research and write articles into WordPress drafts"),
    "Backlinks": ("🔗", backlinks.render,
                  "Auto-publish to owned platforms, plus guest outreach"),
    "Settings": ("⚙️", settings.render,
                 "Sites, models, API keys and connection tests"),
}
