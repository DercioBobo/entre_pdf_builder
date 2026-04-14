"""
entre_pdf_builder.api
~~~~~~~~~~~~~~~~~~~~~~
Whitelisted public API.

Callable from:
  - Server Scripts:          frappe.call("entre_pdf_builder.api.<fn>", ...)
  - Other Frappe apps:       frappe.call(...)  /  frappe.make_post_request(...)
  - REST clients:            POST /api/method/entre_pdf_builder.api.<fn>

All functions check document-level permissions before rendering.
All exceptions are caught, logged to Frappe's Error Log, and re-raised
so the caller receives a meaningful HTTP error rather than a silent failure.
"""
from __future__ import unicode_literals

import base64

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_doc_pdf(doctype, name, print_format=None, letterhead=None):
    """
    Shared render path used by all three public functions.
    Returns raw PDF bytes.
    """
    html = frappe.get_print(
        doctype,
        name,
        print_format=print_format,
        letterhead=letterhead,
    )
    from entre_pdf_builder.utils.renderer import get_pdf
    return get_pdf(html)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_pdf_bytes(doctype, name, print_format=None, letterhead=None):
    """
    Render a document to PDF and return a base64-encoded string.

    Args:
        doctype (str):          DocType name  (e.g. "Sales Invoice").
        name (str):             Document name (e.g. "SINV-0001").
        print_format (str):     Optional Print Format name.
        letterhead (str):       Optional Letterhead name.

    Returns:
        str: Base64-encoded PDF bytes (safe to embed in JSON responses).
    """
    frappe.has_permission(doctype, doc=name, throw=True)

    try:
        pdf_bytes = _render_doc_pdf(doctype, name, print_format, letterhead)
        return base64.b64encode(pdf_bytes).decode("utf-8")
    except Exception:
        frappe.log_error(
            title="PDF Builder: get_pdf_bytes failed",
            message=frappe.get_traceback(),
        )
        raise


@frappe.whitelist()
def get_pdf_for_whatsapp(doctype, name, print_format=None):
    """
    Render a document to PDF and return a dict ready for the
    Evolution API v2 ``sendMedia`` endpoint.

    Args:
        doctype (str):      DocType name.
        name (str):         Document name.
        print_format (str): Optional Print Format name.

    Returns:
        dict: {
            "base64":   "<base64-encoded PDF>",
            "filename": "sales-invoice-SINV-0001.pdf",
            "mimetype": "application/pdf"
        }
    """
    frappe.has_permission(doctype, doc=name, throw=True)

    try:
        pdf_bytes = _render_doc_pdf(doctype, name, print_format)
        b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        filename = f"{frappe.scrub(doctype)}-{name}.pdf"
        return {
            "base64": b64,
            "filename": filename,
            "mimetype": "application/pdf",
        }
    except Exception:
        frappe.log_error(
            title="PDF Builder: get_pdf_for_whatsapp failed",
            message=frappe.get_traceback(),
        )
        raise


@frappe.whitelist()
def download_pdf_playwright(doctype, name, print_format=None, letterhead=None,
                            no_letterhead=0, lang=None):
    """
    Direct Playwright PDF download — completely bypasses wkhtmltopdf and
    Frappe's PDF pipeline.  Navigates to /printview with the current session
    cookie so every asset (CSS, fonts, images) loads exactly as in the browser.

    Called from the custom PDF button injected by pdf_builder.js.
    """
    frappe.has_permission(doctype, doc=name, throw=True)

    try:
        from entre_pdf_builder.utils.renderer import render_printview_to_pdf

        pdf_bytes = render_printview_to_pdf(
            doctype=doctype,
            name=name,
            print_format=print_format,
            letterhead=letterhead,
            no_letterhead=int(no_letterhead or 0),
            lang=lang,
        )

        filename = f"{frappe.scrub(name)}.pdf"
        frappe.local.response.filename = filename
        frappe.local.response.filecontent = pdf_bytes
        frappe.local.response.type = "pdf"

    except Exception:
        frappe.log_error(
            title="PDF Builder: download_pdf_playwright failed",
            message=frappe.get_traceback(),
        )
        raise


@frappe.whitelist()
def attach_pdf_to_doc(doctype, name, print_format=None):
    """
    Render a document to PDF and save it as a private File attachment.

    Args:
        doctype (str):      DocType name.
        name (str):         Document name.
        print_format (str): Optional Print Format name.

    Returns:
        str: The ``name`` (primary key) of the created File document.
    """
    frappe.has_permission(doctype, doc=name, throw=True)

    try:
        pdf_bytes = _render_doc_pdf(doctype, name, print_format)
        filename = f"{frappe.scrub(doctype)}-{name}.pdf"

        # frappe.utils.file_manager.save_file is stable across v13 and v15
        from frappe.utils.file_manager import save_file
        file_doc = save_file(
            fname=filename,
            content=pdf_bytes,
            dt=doctype,
            dn=name,
            is_private=1,
        )
        return file_doc.name
    except Exception:
        frappe.log_error(
            title="PDF Builder: attach_pdf_to_doc failed",
            message=frappe.get_traceback(),
        )
        raise
