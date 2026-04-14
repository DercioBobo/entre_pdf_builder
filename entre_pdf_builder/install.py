"""
entre_pdf_builder.install
~~~~~~~~~~~~~~~~~~~~~~~~~~
Lifecycle hooks executed by Frappe on app install / uninstall.
"""
from __future__ import unicode_literals

import frappe


def after_install():
    """
    Called by `bench install-app entre_pdf_builder`.

    For Single DocTypes Frappe creates the record automatically during
    `bench migrate`; defaults come from the DocType JSON field definitions.
    This hook just logs a confirmation and forces a commit so the record
    is visible immediately.
    """
    try:
        frappe.db.commit()
        frappe.msgprint(
            "Entre PDF Builder installed successfully. "
            "Open <b>PDF Builder Settings</b> to review the configuration.",
            title="Entre PDF Builder",
            indicator="green",
        )
    except Exception:
        frappe.log_error(
            title="PDF Builder: after_install error",
            message=frappe.get_traceback(),
        )


def after_uninstall():
    """
    Called by `bench uninstall-app entre_pdf_builder`.

    Restores the original frappe.utils.pdf.get_pdf so wkhtmltopdf is
    used immediately in the running process.  After the next `bench restart`
    the patch is never applied (app no longer in installed_apps), so this
    is belt-and-suspenders safety for the current live process.
    """
    # Restore original get_pdf in the running process
    try:
        import frappe.utils.pdf as _pdf_mod
        original = getattr(_pdf_mod, "_original_get_pdf", None)
        if original is not None:
            _pdf_mod.get_pdf = original
            try:
                del _pdf_mod._original_get_pdf
            except AttributeError:
                pass
            _pdf_mod._entre_patched = False
    except Exception:
        pass

    # Gracefully shut down the Chromium browser
    try:
        from entre_pdf_builder.utils.browser_pool import close_browser
        close_browser()
    except Exception:
        pass
