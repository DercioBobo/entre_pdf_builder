"""
entre_pdf_builder.utils.browser_pool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Thread-safe persistent Chromium singleton.

Design
------
* One ``sync_playwright`` instance + one ``Browser`` object live for the
  lifetime of the process.
* Each render call opens a fresh ``BrowserContext`` (isolated from others)
  and closes it immediately after — the browser itself stays warm.
* A ``threading.Lock`` serialises launch/reconnect so multiple workers that
  start simultaneously don't race to create duplicate browsers.
* If the browser crashes or disconnects ``get_browser()`` transparently
  relaunches it on the next call.
* ``close_browser()`` is registered with ``atexit`` so Chromium is cleaned
  up even if the process exits unexpectedly.
"""
from __future__ import unicode_literals

import atexit
import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_playwright_instance = None
_browser = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_chromium_args():
    """
    Return the list of Chromium CLI arguments.

    Reads ``chromium_args`` from PDF Builder Settings and merges with the
    hard EC2-safe defaults.  Falls back to defaults only if Frappe or the
    DocType is unavailable (e.g. during tests or early startup).
    """
    defaults = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--single-process",
    ]
    try:
        import frappe
        raw = frappe.db.get_single_value(
            "PDF Builder Settings", "chromium_args"
        ) or ""
        extra = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and line.strip() not in defaults
        ]
        return defaults + extra
    except Exception:
        return defaults


def _launch():
    """
    Start a new Playwright instance and launch Chromium.

    Returns:
        tuple[playwright.sync_api.Playwright, playwright.sync_api.Browser]
    """
    from playwright.sync_api import sync_playwright

    args = _get_chromium_args()
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=args)
    logger.info(
        "PDF Builder: Chromium launched (browser id=%s, args=%s)",
        id(browser),
        args,
    )
    return pw, browser


def _is_connected(browser):
    """Return True if *browser* is still alive."""
    try:
        return browser.is_connected()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_browser():
    """
    Return the singleton Chromium Browser instance.

    Launches it on first call and auto-reconnects if it has crashed.
    Thread-safe.

    Raises:
        Exception: propagated from Playwright if Chromium cannot be launched.
    """
    global _playwright_instance, _browser

    # Fast path — no lock needed when browser is healthy
    if _browser is not None and _is_connected(_browser):
        return _browser

    with _lock:
        # Re-check under the lock (another thread may have launched it)
        if _browser is not None and _is_connected(_browser):
            return _browser

        # Browser is gone or was never started
        if _browser is not None:
            logger.warning("PDF Builder: browser disconnected, relaunching…")
            _browser = None

        pw, browser = _launch()
        _playwright_instance = pw
        _browser = browser
        return _browser


def close_browser():
    """
    Gracefully close the Chromium browser and stop the Playwright driver.

    Called automatically via ``atexit`` and explicitly from
    ``entre_pdf_builder.install.after_uninstall``.
    """
    global _playwright_instance, _browser

    with _lock:
        if _browser is not None:
            try:
                _browser.close()
                logger.info("PDF Builder: Chromium browser closed.")
            except Exception:
                logger.exception("PDF Builder: error while closing browser")
            _browser = None

        if _playwright_instance is not None:
            try:
                _playwright_instance.stop()
            except Exception:
                logger.exception("PDF Builder: error while stopping Playwright")
            _playwright_instance = None


# Register shutdown handler so Chromium is always cleaned up on process exit.
atexit.register(close_browser)
