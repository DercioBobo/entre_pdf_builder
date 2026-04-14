"""
entre_pdf_builder.utils.weasyprint_renderer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
WeasyPrint-based PDF renderer.

Activated when ``PDF Builder Settings.renderer == "WeasyPrint"``.

WeasyPrint is a pure-Python library that renders HTML/CSS to PDF without
needing a browser binary — useful for lightweight EC2 instances where
running Chromium is impractical.

Interface
---------
``render(html, options) -> bytes``

The *options* dict accepts the same wkhtmltopdf-style keys as the
Playwright renderer so the two backends are interchangeable at the
settings level.
"""
from __future__ import unicode_literals

import logging

logger = logging.getLogger(__name__)


def render(html, options=None):
    """
    Render *html* to PDF bytes using WeasyPrint.

    Args:
        html (str):    Full HTML string to render.
        options (dict): wkhtmltopdf-style options.  Understood keys:
                        ``page-size``, ``orientation``,
                        ``margin-top/bottom/left/right``.

    Returns:
        bytes: Raw PDF content.

    Raises:
        ImportError: if WeasyPrint is not installed.
        Any WeasyPrint rendering exception (caller handles fallback).
    """
    from weasyprint import HTML, CSS  # pylint: disable=import-error

    options = options or {}

    page_size = options.get("page-size", "A4")
    orientation = options.get("orientation", "Portrait")

    margin_top = options.get("margin-top", "15mm")
    margin_bottom = options.get("margin-bottom", "15mm")
    margin_left = options.get("margin-left", "15mm")
    margin_right = options.get("margin-right", "15mm")

    if orientation.strip().lower() == "landscape":
        size_css = f"size: {page_size} landscape;"
    else:
        size_css = f"size: {page_size} portrait;"

    page_css = CSS(string=f"""
        @page {{
            {size_css}
            margin-top: {margin_top};
            margin-bottom: {margin_bottom};
            margin-left: {margin_left};
            margin-right: {margin_right};
        }}
    """)

    logger.debug(
        "PDF Builder (WeasyPrint): rendering page_size=%s landscape=%s",
        page_size,
        orientation.strip().lower() == "landscape",
    )

    return HTML(string=html).write_pdf(stylesheets=[page_css])
