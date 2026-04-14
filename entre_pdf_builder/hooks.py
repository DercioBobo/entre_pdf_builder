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
# Core override — activates automatically on `bench install-app`.
# Replaces frappe.utils.pdf.get_pdf for all calls that go through Frappe's
# whitelisted method dispatch (print button, frappe.call, bulk-print API).
# ---------------------------------------------------------------------------
override_whitelisted_methods = {
    "frappe.utils.pdf.get_pdf": "entre_pdf_builder.utils.renderer.get_pdf",
}

# ---------------------------------------------------------------------------
# Guarantee the monkey-patch is applied for every HTTP request.
# This covers server-side calls (frappe.get_print, email attachments, etc.)
# that do NOT go through the whitelist.
# Background workers get patched via __init__.py at import time.
# ---------------------------------------------------------------------------
before_request = ["entre_pdf_builder.utils.renderer.ensure_patch"]

# ---------------------------------------------------------------------------
# Install / uninstall lifecycle
# ---------------------------------------------------------------------------
after_install = "entre_pdf_builder.install.after_install"
after_uninstall = "entre_pdf_builder.install.after_uninstall"
