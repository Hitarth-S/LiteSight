import os
import pytest
from playwright.sync_api import sync_playwright


def test_in_page_redaction_preview_and_restore():
    """
    Verifies that:
    1. content.js previewRedaction() masks Aadhaar, PAN, Phone, Email, and Password in live DOM.
    2. Sensitive PII values are removed from document.body.textContent while preview is active.
    3. restorePage() reverses all DOM mutations in LIFO order.
    4. document.body.textContent after restore is byte-for-byte identical to the original pre-preview text.
    """
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "pii_page.html"))
    content_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extension", "content.js"))

    assert os.path.exists(html_path), f"pii_page.html not found at {html_path}"
    assert os.path.exists(content_js_path), f"content.js not found at {content_js_path}"

    with open(content_js_path, "r", encoding="utf-8") as f:
        content_js = f.read()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path}")
        original_text = page.evaluate("document.body.textContent")

        # Mock minimal chrome runtime messaging
        page.evaluate("""
            window.chrome = {
                runtime: {
                    onMessage: {
                        addListener: (cb) => { window.__msgListener = cb; }
                    }
                }
            };
        """)
        page.evaluate(content_js)

        # 1. Trigger PREVIEW_REDACTION
        preview_res = page.evaluate("""() => {
            let out;
            window.__msgListener({ type: 'PREVIEW_REDACTION' }, {}, (r) => { out = r; });
            return out;
        }""")

        assert preview_res is not None
        counts = preview_res.get("counts", {})
        assert counts.get("AADHAAR") == 1
        assert counts.get("PAN") == 1
        assert counts.get("PHONE") == 1
        assert counts.get("EMAIL") == 1
        assert counts.get("PASSWORD") == 1

        # Check DOM text content during preview
        masked_text = page.evaluate("document.body.textContent")
        assert "2345 6789 0124" not in masked_text
        assert "ABCDE1234F" not in masked_text
        assert "+91 98765 43210" not in masked_text
        assert "test.user@example.com" not in masked_text

        # Negative control numbers must remain unredacted
        assert "1234 5678 9013" in masked_text

        # 2. Trigger RESTORE_PAGE
        restore_res = page.evaluate("""() => {
            let out;
            window.__msgListener({ type: 'RESTORE_PAGE' }, {}, (r) => { out = r; });
            return out;
        }""")

        assert restore_res and restore_res.get("restored") is True

        # 3. Assert byte-for-byte exact equality
        restored_text = page.evaluate("document.body.textContent")
        assert restored_text == original_text

        browser.close()
