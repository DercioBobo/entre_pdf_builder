# entre_pdf_builder

A Frappe app that replaces **wkhtmltopdf** with **Playwright (Chromium)** as
the PDF renderer across the entire ERPNext / Frappe ecosystem — including the
print button, email attachments, `frappe.get_print(as_pdf=True)`, bulk print,
and any WhatsApp notification app that calls `frappe.utils.pdf.get_pdf`.

A **WeasyPrint** backend is also available for lightweight instances that do
not need a full browser.

## Requirements

| Component | Version |
|-----------|---------|
| Frappe / ERPNext | v13 or v15 |
| Python | ≥ 3.8 |
| OS | Ubuntu (Bitnami stack on AWS EC2) |

---

## Installation

### 1 — Fetch the app

```bash
bench get-app entre_pdf_builder https://github.com/entre/entre_pdf_builder
```

### 2 — Install on your site

```bash
bench install-app entre_pdf_builder
bench migrate
```

### 3 — Install Playwright into **both** virtualenvs

Bitnami ERPNext exposes two separate Python environments.  Playwright must be
present in **both** so the web workers (mod\_wsgi) and the background workers
(gonit) can each launch Chromium.

```bash
# ── virtualenv used by workers and Apache (mod_wsgi) ──────────────────────
/path/to/frappe-bench/env/bin/pip install playwright
/path/to/frappe-bench/env/bin/playwright install chromium --with-deps

# ── virtualenv used by bench CLI ──────────────────────────────────────────
/opt/bitnami/erpnext/venv/bin/pip install playwright
/opt/bitnami/erpnext/venv/bin/playwright install chromium --with-deps
```

> **Tip** — `--with-deps` installs the system libraries Chromium needs
> (fonts, nss, etc.).  On a fresh EC2 Ubuntu instance this is required.
> On subsequent upgrades you can omit it.

#### WeasyPrint (optional)

If you want to use the WeasyPrint backend instead, install it the same way:

```bash
/path/to/frappe-bench/env/bin/pip install weasyprint
```

### 4 — Restart workers

On Bitnami, **do not use `sudo bench restart`** — it often restarts the
wrong process tree.  Use gonit directly:

```bash
# Stop all Bitnami services
sudo /opt/bitnami/ctlscript.sh stop

# Wait a moment for processes to exit cleanly
sleep 5

# Start all Bitnami services
sudo /opt/bitnami/ctlscript.sh start
```

Or, to restart only the Frappe web and worker processes without touching the
database:

```bash
sudo gonit stop frappe-web frappe-schedule frappe-worker-default \
    frappe-worker-long frappe-worker-short

sleep 5

sudo gonit start frappe-web frappe-schedule frappe-worker-default \
    frappe-worker-long frappe-worker-short
```

### 5 — Verify the configuration

1. Log in to ERPNext as System Manager.
2. Search for **PDF Builder Settings**.
3. Confirm **Enabled** is checked and **Renderer** is set to `Playwright`.
4. Open any document (e.g. a Sales Invoice) and click **Print → PDF** to
   verify the output.

---

## Configuration reference

All settings live in the **PDF Builder Settings** Single DocType.  No
configuration files or environment variables are required.

| Field | Default | Description |
|-------|---------|-------------|
| **Enabled** | ✔ | Master toggle. Uncheck to fall back to wkhtmltopdf globally. |
| **Renderer** | Playwright | `Playwright`, `WeasyPrint`, or `wkhtmltopdf (default)`. |
| **Fallback to wkhtmltopdf on error** | ✔ | Automatically retries with wkhtmltopdf if the selected renderer raises an exception. |
| **Log Render Time** | ✗ | Writes render duration to the Frappe Error Log for performance monitoring. |
| **Default Page Size** | A4 | `A4`, `A3`, `Letter`, `Legal`. Overridden by per-format options. |
| **Default Orientation** | Portrait | `Portrait` or `Landscape`. Overridden by per-format options. |
| **Margin Top/Bottom/Left/Right** | 15mm | CSS-compatible values (`mm`, `cm`, `in`, `px`). |
| **Chromium Launch Arguments** | *(EC2 defaults)* | Extra CLI args for Chromium, one per line. |
| **Cache Rendered PDFs** | ✗ | Reserved for a future caching layer. |
| **Max Browser Contexts** | 5 | Reserved for a future context pool. |

---

## Public API

The following functions are whitelisted and callable from:

- **Server Scripts** — `frappe.call("entre_pdf_builder.api.<fn>", {...})`
- **Other Frappe apps** — `frappe.call(...)` / `frappe.make_post_request(...)`
- **REST clients** — `POST /api/method/entre_pdf_builder.api.<fn>`

### `get_pdf_bytes(doctype, name, print_format=None, letterhead=None)`

Returns a **base64-encoded** PDF string.  Safe to embed directly in JSON
responses.

```python
result = frappe.call(
    "entre_pdf_builder.api.get_pdf_bytes",
    doctype="Sales Invoice",
    name="SINV-0001",
)
# result is a base64 string
```

### `get_pdf_for_whatsapp(doctype, name, print_format=None)`

Returns a dict ready to pass to the **Evolution API v2** `sendMedia`
endpoint:

```json
{
  "base64":   "<base64-encoded PDF>",
  "filename": "sales-invoice-SINV-0001.pdf",
  "mimetype": "application/pdf"
}
```

### `attach_pdf_to_doc(doctype, name, print_format=None)`

Renders the PDF and saves it as a **private File attachment** on the document.
Returns the `File` docname.

---

## Architecture

```
frappe.utils.pdf.get_pdf          ← monkey-patched at import time
        │
        ▼
entre_pdf_builder.utils.renderer.get_pdf
        │
        ├── PDF Builder Settings disabled?  →  wkhtmltopdf (original)
        ├── renderer == "Playwright"        →  browser_pool.get_browser()
        │                                       → page.pdf()
        ├── renderer == "WeasyPrint"        →  weasyprint_renderer.render()
        ├── renderer == "wkhtmltopdf …"     →  wkhtmltopdf (original)
        └── any exception                   →  log_error()
                                             →  wkhtmltopdf (fallback)
```

The Chromium browser is a **module-level singleton** protected by a
`threading.Lock`.  Each render opens a fresh `BrowserContext` and closes it
immediately — the browser process stays warm.  Auto-reconnect is built in: if
Chromium crashes, the next `get_browser()` call relaunches it transparently.

---

## Uninstalling

```bash
bench uninstall-app entre_pdf_builder
bench migrate
```

The original `frappe.utils.pdf.get_pdf` (wkhtmltopdf) is restored
automatically — both in the running process (via the `after_uninstall` hook)
and after the next restart (the patch is simply never applied once the app is
no longer in `installed_apps`).  No core files are modified.

---

## License

MIT — see [LICENSE](LICENSE).
