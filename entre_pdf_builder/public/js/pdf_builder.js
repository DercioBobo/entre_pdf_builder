/**
 * entre_pdf_builder — frontend shim
 *
 * Suppresses Frappe's "Invalid wkhtmltopdf version" warning.
 * The warning is triggered by a client-side check for the wkhtmltopdf binary.
 * Since PDF Builder replaces wkhtmltopdf with Playwright on the server,
 * this warning is irrelevant and confusing to end users.
 */
frappe.ready(function () {

	// Intercept frappe.msgprint and drop the specific wkhtmltopdf message.
	const _orig_msgprint = frappe.msgprint.bind(frappe);
	frappe.msgprint = function (options) {
		const msg = (typeof options === "string") ? options
			: (options && (options.message || options.msg || ""));
		if (msg && msg.toLowerCase().indexOf("wkhtmltopdf") !== -1) {
			// Swallow — PDF Builder handles PDF generation via Playwright.
			return;
		}
		return _orig_msgprint(options);
	};

});
