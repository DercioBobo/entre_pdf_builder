from __future__ import unicode_literals

app_name = "entre_pdf_builder"
app_title = "Entre PDF Builder"
app_publisher = "Entre"
app_description = (
    "Replaces wkhtmltopdf with Playwright (Chromium) as the PDF renderer "
    "for ERPNext / Frappe — print button, email attachments, bulk print, "
    "frappe.get_print(as_pdf=True), and WhatsApp notification apps."
)
app_icon = "octicon octicon-file-pdf"
app_color = "blue"
app_email = "dev@entre.co.mz"
app_license = "MIT"
app_version = "1.0.0"

# ---------------------------------------------------------------------------
# Core override strategy (two layers):
#
# 1. before_request  — patches frappe.utils.pdf.get_pdf before every HTTP
#    request.  Covers the print button, email attachments, frappe.get_print,
#    bulk-print, and any other server-side caller.
#
# 2. __init__.py     — patches at import time so background workers and bench
#    CLI commands are also covered without waiting for a web request.
#
# Note: override_whitelisted_methods is intentionally NOT used here because
# frappe.utils.pdf.get_pdf is an internal utility, not a whitelisted endpoint.
# ---------------------------------------------------------------------------
before_request = ["entre_pdf_builder.utils.renderer.ensure_patch"]

# Suppress the wkhtmltopdf version warning in the browser UI
app_include_js = ["/assets/entre_pdf_builder/js/pdf_builder.js"]

# ---------------------------------------------------------------------------
# Install / uninstall lifecycle
# ---------------------------------------------------------------------------
after_install = "entre_pdf_builder.install.after_install"
after_uninstall = "entre_pdf_builder.install.after_uninstall"
