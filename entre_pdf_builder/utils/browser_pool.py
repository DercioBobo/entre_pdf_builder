"""
entre_pdf_builder.utils.browser_pool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Thread-local Chromium browser pool for Playwright sync API.

Why thread-local?
-----------------
Playwright's sync API uses greenlets internally.  A ``sync_playwright()``
instance and the Browser object it produces are bound to the OS thread (and
greenlet dispatcher) that called ``sync_playwright().start()``.

Apache/mod_wsgi dispatches each HTTP request on a thread from its pool.
A naive global singleton would be created on thread-A and then accessed on
thread-B, causing::

    greenlet.error: Cannot switch to a different thread

The fix: each thread keeps its own ``(playwright, browser)`` pair in
``threading.local()``.  On a typical mod_wsgi server with 5 threads, up to
5 Chromium processes run — acceptable and more reliable than sharing one.

Public interface
----------------
``get_browser()``   — returns the Browser for the calling thread, launching
                      it on first call or after a crash.
``close_browser()`` — closes all browsers across all threads (called on
                      app shutdown via atexit).
"""
from __future__ import unicode_literals

import atexit
import logging
import os
import sys
import threading

logger = logging.getLogger(__name__)

# Thread-local storage: each thread has its own .pw and .browser
_local = threading.local()

# Global registry so close_browser() can clean up every thread's instance
_registry_lock = threading.Lock()
_registry = []  # list of (playwright_instance, browser)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_browsers_path():
    """
    Set PLAYWRIGHT_BROWSERS_PATH if not already set.

    mod_wsgi daemon processes run as a different OS user (e.g. ``daemon``)
    whose $HOME has no ~/.cache/ms-playwright.  We probe the most likely
    locations so Playwright can find Chromium regardless of which user the
    worker runs as.
    """
    if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
        return
    candidates = [
        os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright"),
        "/home/bitnami/.cache/ms-playwright",
        "/opt/bitnami/.cache/ms-playwright",
        "/root/.cache/ms-playwright",
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate
            logger.info("PDF Builder: using browsers at %s", candidate)
            return


def _get_chromium_args():
    """Return Chromium launch arguments from settings, merged with EC2 defaults."""
    defaults = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    try:
        import frappe
        raw = frappe.db.get_single_value("PDF Builder Settings", "chromium_args") or ""
        extra = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and line.strip() not in defaults
        ]
        return defaults + extra
    except Exception:
        return defaults


def _launch_for_thread():
    """
    Start a new ``sync_playwright`` instance and launch Chromium for the
    calling thread.  Stores the pair in ``_local`` and registers it in
    ``_registry`` for global cleanup.

    Returns:
        playwright.sync_api.Browser
    """
    from playwright.sync_api import sync_playwright

    _ensure_browsers_path()
    args = _get_chromium_args()

    # mod_wsgi replaces sys.stderr with an Apache log object that has no real
    # file descriptor.  Playwright calls sys.stderr.fileno() when spawning its
    # Node.js helper, which raises OSError.  Swap it for a real /dev/null fd
    # just for the duration of the start() call.
    saved_stderr = sys.stderr
    devnull = None
    try:
        devnull = open(os.devnull, "w")
        sys.stderr = devnull
        pw = sync_playwright().start()
    finally:
        sys.stderr = saved_stderr
        if devnull is not None:
            try:
                devnull.close()
            except Exception:
                pass

    browser = pw.chromium.launch(headless=True, args=args)
    logger.info(
        "PDF Builder: Chromium launched for thread %s (browser id=%s)",
        threading.current_thread().name,
        id(browser),
    )

    _local.pw = pw
    _local.browser = browser

    with _registry_lock:
        _registry.append((pw, browser))

    return browser


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_browser():
    """
    Return the Chromium Browser for the calling thread.

    Launches a new instance on first call or after a crash/disconnect.
    Never raises — callers handle exceptions and fall back to wkhtmltopdf.
    """
    browser = getattr(_local, "browser", None)

    if browser is not None:
        try:
            if browser.is_connected():
                return browser
        except Exception:
            pass
        logger.warning(
            "PDF Builder: browser disconnected on thread %s, relaunching",
            threading.current_thread().name,
        )
        _local.browser = None
        _local.pw = None

    return _launch_for_thread()


def close_browser():
    """
    Close all Chromium browsers and stop all Playwright instances across
    every thread.  Called automatically via atexit and from after_uninstall.
    """
    with _registry_lock:
        instances = list(_registry)
        _registry.clear()

    for pw, browser in instances:
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

    # Also clean up the calling thread's locals
    _local.browser = None
    _local.pw = None
    logger.info("PDF Builder: all Chromium instances closed.")


# Ensure cleanup on process exit
atexit.register(close_browser)
