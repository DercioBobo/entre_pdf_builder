/**
 * entre_pdf_builder — frontend shim
 *
 * 1. Suppresses the "Invalid wkhtmltopdf version" warning.
 * 2. On the /printview page, replaces the "Get PDF" button with one that
 *    calls our Playwright endpoint directly.
 */

frappe.ready(function () {

    // ── 1. Suppress wkhtmltopdf warning ────────────────────────────────────
    var _orig_msgprint = frappe.msgprint.bind(frappe);
    frappe.msgprint = function (options) {
        var msg = (typeof options === "string") ? options
            : (options && (options.message || options.msg || ""));
        if (msg && msg.toLowerCase().indexOf("wkhtmltopdf") !== -1) {
            return; // swallow — PDF Builder uses Playwright
        }
        return _orig_msgprint(options);
    };

    // ── 2. Replace "Get PDF" on the printview page ─────────────────────────
    function install_playwright_button() {
        // Build download URL from current printview query params
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

        // Override every element whose text is "Get PDF" or contains "pdf"
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

        // Also inject a clearly-labelled button next to Print
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

    // Run when the page is the printview
    if (window.location.pathname === "/printview") {
        // Wait for Frappe to finish rendering the page
        var tries = 0;
        var timer = setInterval(function () {
            tries++;
            if (document.querySelector(".print-format") || tries > 20) {
                clearInterval(timer);
                install_playwright_button();
            }
        }, 300);
    }

});
