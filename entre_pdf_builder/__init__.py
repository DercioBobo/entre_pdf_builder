__version__ = "1.0.0"

# Apply the frappe.utils.pdf.get_pdf monkey-patch as early as possible so
# every code path — web workers, background workers, bench CLI — uses
# Playwright without any per-request overhead.
#
# The try/except is intentional: during `bench get-app` / `pip install` the
# Frappe runtime is not available, so the import fails silently.  The
# before_request hook in hooks.py provides a second guarantee for web workers.
try:
    from entre_pdf_builder.utils.renderer import ensure_patch as _ensure_patch
    _ensure_patch()
except Exception:
    pass
