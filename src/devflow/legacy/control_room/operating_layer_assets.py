"""Facade for operating-layer static assets.

The static files under ``static/`` are the canonical source for the browser.
They were extracted from the original Python string constants
(``operating_layer_html.py``, ``operating_layer_styles.py``,
``operating_layer_script.py``) which remain as fallback sources for backward
compatibility and for tests that do string containment checks
(``operating_layer_visual_qa.py``).

If the static files are present, they are the single source of truth at
runtime. The fallback to Python string constants only fires if the static
directory is missing (e.g. an incomplete install). In that case, a warning
is logged so the issue is not silently masked.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _read_asset(filename: str) -> str:
    """Read a static asset file, falling back to the Python string constant
    if the file is missing (e.g. during package install without static/).
    """
    path = _STATIC_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Fallback: import from the original Python string modules.
    # This ensures tests pass even if static files aren't present.
    logger.warning(
        "Static asset %s not found in %s; falling back to Python string constant. "
        "Run the asset extraction build step to generate static files.",
        filename,
        _STATIC_DIR,
    )
    if filename == "index.html":
        from devflow.legacy.control_room.operating_layer_html import INDEX_HTML
        return INDEX_HTML
    if filename == "app.css":
        from devflow.legacy.control_room.operating_layer_styles import APP_CSS
        return APP_CSS
    if filename == "app.js":
        from devflow.legacy.control_room.operating_layer_script import APP_JS
        return APP_JS
    raise FileNotFoundError(f"Unknown asset: {filename}")


INDEX_HTML: str = _read_asset("index.html")
APP_CSS: str = _read_asset("app.css")
APP_JS: str = _read_asset("app.js")

__all__ = ["APP_CSS", "APP_JS", "INDEX_HTML"]
