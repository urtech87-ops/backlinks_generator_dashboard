"""
UI layer: reusable components (`ui.components`), the shared data loader
(`ui.data`), and one module per sidebar page in `ui.views`.

Pages are plain functions — `render(ctx)` — so `app.py` stays a thin shell
that picks a page and hands it the current site + date range.
"""

from .components import (            # noqa: F401  (re-exported for convenience)
    page_header, section, status_badge, show_badge, metric_row,
    empty_state, coming_soon, check_list, data_source_note,
)
