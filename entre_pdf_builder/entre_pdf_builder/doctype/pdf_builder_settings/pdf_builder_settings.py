# Copyright (c) 2024, Entre and contributors
# License: MIT — see LICENSE

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class PDFBuilderSettings(Document):
    """
    Controller for the PDF Builder Settings Single DocType.

    The only responsibility of this controller is to invalidate the
    per-request ``frappe.local`` settings cache whenever the document
    is saved, so the next request picks up the new values.

    Note: ``frappe.local`` is thread-local and request-scoped, so there is
    nothing to flush in Redis.  The cache dies naturally at the end of every
    request / background job.
    """

    def validate(self):
        self._validate_margins()

    def on_update(self):
        # Nothing to flush — frappe.local cache is request-scoped.
        # Kept as a hook point for future Redis caching.
        pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_margins(self):
        """Warn (not block) if a margin field is blank."""
        margin_fields = [
            "margin_top",
            "margin_bottom",
            "margin_left",
            "margin_right",
        ]
        for field in margin_fields:
            if not (getattr(self, field, None) or "").strip():
                frappe.msgprint(
                    f"<b>{self.meta.get_field(field).label}</b> is empty — "
                    "defaulting to <b>15mm</b> at render time.",
                    indicator="orange",
                    alert=True,
                )
