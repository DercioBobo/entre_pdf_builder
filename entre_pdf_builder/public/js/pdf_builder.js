/**
 * entre_pdf_builder — frontend shim
 *
 * 1. Suppresses the "Invalid wkhtmltopdf version" warning.
 * 2. On the /printview page, replaces the "Get PDF" button with one that
 *    calls our Playwright endpoint directly.
 * 3. On every Form page, adds a "PDF (Playwright)" button inside the
 *    Print menu so the user can download a pixel-perfect PDF without
 *    ever leaving the document.
 */

frappe.ready(function () {

    // ── 1. Suppress wkhtmltopdf warning ────────────────────────────────────
    function _contains_wkhtmltopdf(options) {
        var msg = (typeof options === "string") ? options
            : (options && (options.message || options.msg || options.title || ""));
        return msg && msg.toLowerCase().indexOf("wkhtmltopdf") !== -1;
    }

    var _orig_msgprint = frappe.msgprint.bind(frappe);
    frappe.msgprint = function (options) {
        if (_contains_wkhtmltopdf(options)) return;
        return _orig_msgprint(options);
    };

    // frappe.show_alert is a separate channel Frappe sometimes uses
    if (frappe.show_alert) {
        var _orig_show_alert = frappe.show_alert.bind(frappe);
        frappe.show_alert = function (options, seconds) {
            if (_contains_wkhtmltopdf(options)) return;
            return _orig_show_alert(options, seconds);
        };
    }


    // ── Shared: build the Playwright download URL ───────────────────────────
    function playwright_pdf_url(doctype, name, print_format, letterhead) {
        var args = { doctype: doctype, name: name };
        if (print_format)  args.print_format  = print_format;
        if (letterhead)    args.letterhead     = letterhead;
        return "/api/method/entre_pdf_builder.api.download_pdf_playwright?"
            + new URLSearchParams(args).toString();
    }


    // ── 2. Replace "Get PDF" on the printview page ─────────────────────────
    function install_playwright_button() {
        var qs   = new URLSearchParams(window.location.search);
        var args = {
            doctype:       qs.get("doctype")       || "",
            name:          qs.get("name")          || "",
            print_format:  qs.get("format")        || "",
            letterhead:    qs.get("letterhead")    || "",
            no_letterhead: qs.get("no_letterhead") || "0",
            lang:          qs.get("_lang")         || ""
        };

        var pdf_url = "/api/method/entre_pdf_builder.api.download_pdf_playwright?"
            + new URLSearchParams(args).toString();

        // Override every element whose text is "Get PDF" or "pdf"
        document.querySelectorAll("a, button").forEach(function (el) {
            var txt = (el.innerText || el.textContent || "").trim().toLowerCase();
            if (txt === "get pdf" || txt === "pdf") {
                el.addEventListener("click", function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    window.open(pdf_url, "_blank");
                }, true);
            }
        });

        // Inject a clearly-labelled button next to Print
        var toolbar = document.querySelector(".print-toolbar, .page-head .btn-group, .page-head");
        if (toolbar) {
            var btn = document.createElement("a");
            btn.className = "btn btn-primary btn-sm";
            btn.innerText  = "PDF (Playwright)";
            btn.href       = pdf_url;
            btn.target     = "_blank";
            btn.style.marginLeft = "8px";
            toolbar.appendChild(btn);
        }
    }

    if (window.location.pathname === "/printview") {
        var tries = 0;
        var timer = setInterval(function () {
            tries++;
            if (document.querySelector(".print-format") || tries > 20) {
                clearInterval(timer);
                install_playwright_button();
            }
        }, 300);
    }


    // ── 3. Add "PDF (Playwright)" button to every Form page ────────────────
    function install_form_pdf_button() {
        var route = frappe.get_route();
        // Only on Form pages with a saved document
        if (!route || route[0] !== "Form" || !route[1] || !route[2]) return;
        if (!cur_frm || cur_frm.is_new()) return;
        // Don't add twice after a re-render
        if (cur_frm._playwright_pdf_added) return;
        cur_frm._playwright_pdf_added = true;

        cur_frm.add_custom_button(__("PDF (Playwright)"), function () {
            // Pick up whichever print format the user has selected in the
            // form's print preview panel (if open), otherwise leave blank
            // so the server uses the default.
            var print_format = "";
            var letterhead   = "";
            try {
                if (cur_frm.print_preview && cur_frm.print_preview.frm) {
                    print_format = cur_frm.print_preview.print_format || "";
                    letterhead   = cur_frm.print_preview.letterhead   || "";
                }
            } catch (e) { /* ignore */ }

            var url = playwright_pdf_url(
                cur_frm.doctype,
                cur_frm.docname,
                print_format,
                letterhead
            );
            window.open(url, "_blank");
        }, __("Print"));      // places it inside the ⋮ Print group
    }

    // Re-run every time the route changes (new form, same form refreshed, etc.)
    // Reset the _playwright_pdf_added flag so it can be re-injected after
    // Frappe rebuilds the toolbar on each refresh.
    $(document).on("page-change", function () {
        if (cur_frm) cur_frm._playwright_pdf_added = false;
        setTimeout(install_form_pdf_button, 400);
    });

    // Also run immediately in case the page loaded directly on a form URL.
    setTimeout(install_form_pdf_button, 800);

});
