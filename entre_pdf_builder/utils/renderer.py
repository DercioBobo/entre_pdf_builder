"""
entre_pdf_builder.utils.renderer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Drop-in replacement for ``frappe.utils.pdf.get_pdf``.

Signature matches Frappe's original exactly so every caller — print button,
email attachments, frappe.get_print(as_pdf=True), ERPNext bulk print, and
WhatsApp notification apps — works without any modification.

Routing logic
-------------
1. If PDF Builder Settings.enabled == 0  →  fall through to wkhtmltopdf.
2. renderer == "Playwright"              →  Chromium via persistent browser pool.
3. renderer == "WeasyPrint"             →  pure-Python WeasyPrint.
4. renderer == "wkhtmltopdf (default)"  →  original Frappe renderer.
5. Any unhandled exception              →  log + fallback to wkhtmltopdf
                                           (if fallback_to_wkhtmltopdf == 1).
"""
from __future__ import unicode_literals

import io
import logging
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings helper
# ---------------------------------------------------------------------------

def _default_settings():
    return {
        "enabled": 1,
        "renderer": "Playwright",
        "fallback_to_wkhtmltopdf": 1,
        "log_render_time": 0,
        "default_page_size": "A4",
        "default_orientation": "Portrait",
        "margin_top": "15mm",
        "margin_bottom": "15mm",
        "margin_left": "15mm",
        "margin_right": "15mm",
        "chromium_args": (
            "--no-sandbox\n"
            "--disable-dev-shm-usage\n"
            "--disable-gpu"
        ),
    }


def _get_settings():
    """
    Read PDF Builder Settings, caching the result in ``frappe.local`` for the
    duration of the current request or background job.  Never raises — returns
    safe defaults on any error (DocType not yet migrated, DB unavailable, etc.)
    """
    import frappe

    _CACHE_KEY = "_entre_pdf_builder_settings"

    try:
        cached = getattr(frappe.local, _CACHE_KEY, None)
        if cached is not None:
            return cached
    except Exception:
        pass

    try:
        s = frappe.get_single("PDF Builder Settings")
        d = _default_settings()
        # Single DocType fields return None when never explicitly saved —
        # fall back to our defaults, NOT to 0/falsy values.
        settings = {
            "enabled":                 int(s.enabled)                 if s.enabled                 is not None else d["enabled"],
            "renderer":                s.renderer                     or d["renderer"],
            "fallback_to_wkhtmltopdf": int(s.fallback_to_wkhtmltopdf) if s.fallback_to_wkhtmltopdf is not None else d["fallback_to_wkhtmltopdf"],
            "log_render_time":         int(s.log_render_time)         if s.log_render_time         is not None else d["log_render_time"],
            "default_page_size":       s.default_page_size            or d["default_page_size"],
            "default_orientation":     s.default_orientation          or d["default_orientation"],
            "margin_top":              s.margin_top                   or d["margin_top"],
            "margin_bottom":           s.margin_bottom                or d["margin_bottom"],
            "margin_left":             s.margin_left                  or d["margin_left"],
            "margin_right":            s.margin_right                 or d["margin_right"],
            "chromium_args":           s.chromium_args                or d["chromium_args"],
        }
    except Exception:
        settings = _default_settings()

    try:
        setattr(frappe.local, _CACHE_KEY, settings)
    except Exception:
        pass

    return settings


# ---------------------------------------------------------------------------
# Option mapping
# ---------------------------------------------------------------------------

def _map_options(options, settings):
    """
    Convert a wkhtmltopdf-style options dict to Playwright ``page.pdf()`` kwargs.

    Supported keys
    --------------
    page-size             →  format
    orientation           →  landscape (bool)
    margin-top/bottom/left/right  →  margin dict
    no-background         →  disables print_background
    """
    options = options or {}

    page_size = options.get("page-size") or settings["default_page_size"]
    orientation = options.get("orientation") or settings["default_orientation"]
    landscape = orientation.strip().lower() == "landscape"
    no_bg = options.get("no-background") or options.get("no_background") or False

    return {
        "format": page_size,
        "landscape": landscape,
        "print_background": not no_bg,
        "margin": {
            "top": options.get("margin-top") or settings["margin_top"],
            "bottom": options.get("margin-bottom") or settings["margin_bottom"],
            "left": options.get("margin-left") or settings["margin_left"],
            "right": options.get("margin-right") or settings["margin_right"],
        },
    }


# ---------------------------------------------------------------------------
# Backend renderers
# ---------------------------------------------------------------------------

def _render_playwright(html, options, settings):
    from entre_pdf_builder.utils.browser_pool import get_browser

    pw_options = _map_options(options, settings)
    browser = get_browser()

    # Primary: navigate to the live printview URL so the browser loads all
    # CSS and images exactly as it does for the user.  This is what makes
    # the PDF match the Chrome print preview.
    pdf_bytes = _render_via_url(browser, pw_options)
    if pdf_bytes is not None:
        return pdf_bytes

    # Fallback (background jobs / email attachments with no request context):
    # set_content with best-effort asset loading.
    return _render_via_set_content(browser, html, pw_options)


def _render_via_url(browser, pw_options):
    """
    Navigate to Frappe's /printview page with the current session cookie so
    the browser loads all assets (CSS, fonts, letterhead images) naturally.

    Returns PDF bytes, or None if not in a web-request context.
    """
    try:
        import frappe
        from urllib.parse import urlparse, parse_qs, urlencode

        request = getattr(frappe.local, "request", None)
        if request is None:
            return None

        request_url = getattr(request, "url", "") or ""
        if "download_pdf" not in request_url:
            return None

        # Extract params from the download_pdf URL
        parsed = urlparse(request_url)
        params = parse_qs(parsed.query, keep_blank_values=True)

        printview_params = {}
        for key in ("doctype", "name", "format", "no_letterhead", "letterhead", "_lang"):
            if key in params:
                printview_params[key] = params[key][0]

        site_url = _get_base_url()
        printview_url = f"{site_url}/printview?{urlencode(printview_params)}"

        sid = frappe.session.sid

        context = browser.new_context()
        try:
            # Authenticate so /files/ images and private assets load
            if sid and sid != "Guest":
                context.add_cookies([{
                    "name": "sid",
                    "value": sid,
                    "url": site_url,
                }])

            page = context.new_page()
            # Tell the browser to apply @media print rules —
            # this hides the toolbar and activates print layout
            page.emulate_media(media="print")

            page.goto(printview_url, wait_until="networkidle", timeout=30000)

            # Extra safety: hide any toolbar elements that survive @media print
            page.add_style_tag(content="""
                .print-toolbar, .page-head, .no-print,
                #toolbar-container, .navbar { display: none !important; }
            """)

            return page.pdf(**pw_options)
        finally:
            context.close()

    except Exception:
        logger.exception("PDF Builder: URL navigation approach failed, falling back")
        return None


def _render_via_set_content(browser, html, pw_options):
    """
    Render using set_content — used for background jobs where there is no
    HTTP request context.  Assets may not load fully.
    """
    site_url = _get_base_url()

    context = browser.new_context(base_url=site_url)
    try:
        try:
            import frappe
            sid = frappe.session.sid
            if sid and sid != "Guest":
                context.add_cookies([{
                    "name": "sid",
                    "value": sid,
                    "url": site_url,
                }])
        except Exception:
            pass

        page = context.new_page()
        page.emulate_media(media="print")
        page.set_content(html, wait_until="networkidle")
        page.add_style_tag(content="""
            .print-toolbar, .page-head, .no-print,
            #toolbar-container, .navbar { display: none !important; }
        """)
        return page.pdf(**pw_options)
    finally:
        context.close()


def _render_weasyprint(html, options, settings):
    from entre_pdf_builder.utils.weasyprint_renderer import render as wp_render
    return wp_render(html, options)


def _render_wkhtmltopdf(html, options, output):
    """Delegate to the original Frappe renderer (wkhtmltopdf)."""
    import frappe.utils.pdf as _pdf_mod
    original = getattr(_pdf_mod, "_original_get_pdf", None)
    if original is None:
        # Patch was never applied (e.g. app loaded but patching failed);
        # import the function from a fresh reference to the module object.
        import importlib
        _fresh = importlib.import_module("frappe.utils.pdf")
        original = getattr(_fresh, "_original_get_pdf", _fresh.get_pdf)
    return original(html, options, output)


# ---------------------------------------------------------------------------
# PDF merging helper (PdfFileWriter output= contract)
# ---------------------------------------------------------------------------

def _merge_into_output(pdf_bytes, output):
    """
    Append all pages from *pdf_bytes* into an existing ``PdfFileWriter``
    instance, matching the contract of the original wkhtmltopdf path.

    Compatible with:
      - pypdf >= 3  (``PdfReader``, ``add_page``)
      - PyPDF2 2.x  (``PdfReader``, ``add_page``)
      - PyPDF2 1.x  (``PdfFileReader``, ``addPage``)
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            from PyPDF2 import PdfFileReader as PdfReader  # type: ignore[no-redef]

    reader = PdfReader(io.BytesIO(pdf_bytes))

    # Normalise page-accessor across versions
    try:
        pages = reader.pages
    except AttributeError:
        pages = [reader.getPage(i) for i in range(reader.numPages)]  # type: ignore[attr-defined]

    # Normalise add-page method across versions
    add_page = getattr(output, "add_page", None) or getattr(output, "addPage")

    for page in pages:
        add_page(page)

    return output


# ---------------------------------------------------------------------------
# Public drop-in replacement
# ---------------------------------------------------------------------------

def get_pdf(html, options=None, output=None):
    """
    Drop-in replacement for ``frappe.utils.pdf.get_pdf``.

    Parameters
    ----------
    html : str
        Full HTML string to render.
    options : dict, optional
        wkhtmltopdf-style options dict.  Keys understood:
        ``page-size``, ``orientation``, ``margin-top/bottom/left/right``,
        ``no-background``.
    output : PdfFileWriter, optional
        If provided, rendered pages are merged into this writer and the
        writer is returned — exactly as wkhtmltopdf does.

    Returns
    -------
    bytes | PdfFileWriter
        Raw PDF bytes, or the populated *output* writer if one was passed.
    """
    import frappe

    try:
        settings = _get_settings()
    except Exception:
        settings = _default_settings()

    # Master toggle
    if not settings.get("enabled"):
        return _render_wkhtmltopdf(html, options, output)

    renderer = settings.get("renderer", "Playwright")

    # Pass-through to wkhtmltopdf when explicitly selected
    if renderer == "wkhtmltopdf (default)":
        return _render_wkhtmltopdf(html, options, output)

    start_time = time.time() if settings.get("log_render_time") else None
    pdf_bytes = None

    try:
        if renderer == "Playwright":
            pdf_bytes = _render_playwright(html, options, settings)
        elif renderer == "WeasyPrint":
            pdf_bytes = _render_weasyprint(html, options, settings)
        else:
            return _render_wkhtmltopdf(html, options, output)

    except Exception:
        # Log the error but never propagate an unhandled exception that
        # would break a user-facing print action.
        try:
            frappe.log_error(
                title="PDF Builder: Playwright unavailable",
                message=frappe.get_traceback(),
            )
        except Exception:
            logger.exception("PDF Builder: could not log render error to Frappe")

        if settings.get("fallback_to_wkhtmltopdf"):
            try:
                return _render_wkhtmltopdf(html, options, output)
            except Exception:
                try:
                    frappe.log_error(
                        title="PDF Builder: wkhtmltopdf fallback also failed",
                        message=frappe.get_traceback(),
                    )
                except Exception:
                    pass
                raise
        raise

    finally:
        if start_time is not None and pdf_bytes is not None:
            elapsed = time.time() - start_time
            try:
                frappe.log_error(
                    title="PDF Builder: Render time",
                    message=f"Renderer: {renderer} | Elapsed: {elapsed:.3f}s",
                )
            except Exception:
                pass

    if output is not None:
        return _merge_into_output(pdf_bytes, output)
    return pdf_bytes


# ---------------------------------------------------------------------------
# Monkey-patch helper
# ---------------------------------------------------------------------------

def ensure_patch():
    """
    Guarantee that every known Frappe call-site for get_pdf points to our
    implementation.

    Two levels are required:
    1. frappe.utils.pdf.get_pdf       — the module attribute (covers any code
                                        that accesses it via the module object).
    2. Per-module local bindings       — modules that did
                                        ``from frappe.utils.pdf import get_pdf``
                                        at import time hold a reference to the
                                        original function; we overwrite those
                                        bindings directly.

    Safe to call multiple times (idempotent).  Called:
      - At module import time (covers background workers and CLI).
      - Via the ``before_request`` hook on every HTTP request.
    """
    try:
        import frappe.utils.pdf as _pdf_mod
        if not getattr(_pdf_mod, "_entre_patched", False):
            _pdf_mod._original_get_pdf = _pdf_mod.get_pdf
            _pdf_mod.get_pdf = get_pdf
            _pdf_mod._entre_patched = True
    except Exception:
        logger.exception("PDF Builder: could not patch frappe.utils.pdf")

    # frappe.utils.print_format — powers the PDF print button and
    # frappe.utils.print_format.download_pdf (the endpoint the UI calls).
    try:
        import frappe.utils.print_format as _print_format
        if getattr(_print_format, "get_pdf", None) is not get_pdf:
            _print_format.get_pdf = get_pdf
    except Exception:
        pass

    # frappe.model.print_format — older Frappe versions route through here.
    try:
        import frappe.model.print_format as _model_pf
        if getattr(_model_pf, "get_pdf", None) is not get_pdf:
            _model_pf.get_pdf = get_pdf
    except Exception:
        pass

    # frappe.utils.pdf (re-check the module-level alias some callers use)
    try:
        import frappe
        if getattr(frappe.utils, "get_pdf", None) is not None:
            frappe.utils.get_pdf = get_pdf
    except Exception:
        pass


# Apply patch the moment this module is imported.
ensure_patch()


# ---------------------------------------------------------------------------
# Direct Playwright renderer — navigates to /printview, no set_content
# ---------------------------------------------------------------------------

def _get_base_url():
    """
    Derive the site base URL (scheme + host) from the live HTTP request.

    The request URL is the definitive source — it is exactly the address the
    user's browser connected to, so Playwright will be able to reach it too.
    We intentionally do NOT fall back to frappe.utils.get_url() / site_config,
    because the configured hostname may differ from the IP/domain currently in
    use (e.g. EC2 public IP vs. internal hostname).

    For background jobs where no request is in flight, fall back to
    http://127.0.0.1 so Playwright connects over the loopback interface.
    """
    import frappe
    from urllib.parse import urlparse

    try:
        request = getattr(frappe.local, "request", None)
        if request and getattr(request, "url", None):
            p = urlparse(request.url)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass

    # No active request (background job / bench command) — use loopback so
    # Playwright can reach the local Frappe/Gunicorn/Apache process.
    return "http://127.0.0.1"


def render_printview_to_pdf(doctype, name, print_format=None, letterhead=None,
                            no_letterhead=0, lang=None):
    """
    Navigate to Frappe's /printview page with the current session cookie and
    render to PDF.  This is the most faithful path: CSS, fonts and images all
    load exactly as they do in the user's browser.

    Used by the custom PDF button (api.download_pdf_playwright).
    """
    import frappe
    from urllib.parse import urlencode
    from entre_pdf_builder.utils.browser_pool import get_browser

    settings = _get_settings()
    pw_options = _map_options({}, settings)

    base_url = _get_base_url()

    params = {"doctype": doctype, "name": name, "no_letterhead": no_letterhead or 0}
    if print_format:
        params["format"] = print_format
    if letterhead:
        params["letterhead"] = letterhead
    if lang:
        params["_lang"] = lang

    printview_url = f"{base_url}/printview?{urlencode(params)}"
    logger.info("PDF Builder: navigating to %s", printview_url)

    sid = frappe.session.sid
    browser = get_browser()
    context = browser.new_context()
    try:
        if sid and sid != "Guest":
            context.add_cookies([{"name": "sid", "value": sid, "url": base_url}])

        page = context.new_page()
        page.emulate_media(media="print")
        page.goto(printview_url, wait_until="networkidle", timeout=30000)

        # Hide toolbar elements that survive @media print
        page.add_style_tag(content="""
            .print-toolbar, .page-head, .no-print,
            #toolbar-container, .navbar { display: none !important; }
        """)

        return page.pdf(**pw_options)
    finally:
        context.close()
