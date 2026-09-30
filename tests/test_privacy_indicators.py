import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from src.state.sanitizer import StateSanitizer


def test_privacy_visual_indicators_and_settings():
    """
    Verifies that:
    1. Empty sensitive inputs receive MONITORED status and visual indicator badges.
    2. Filled sensitive inputs/text receive REDACTED status and visual indicator badges.
    3. User-configured sensitivity levels and category toggles are respected dynamically.
    4. Toggling visual indicators off cleanly removes in-page overlays.
    """
    async def _run():
        base_dir = Path(__file__).parent.parent
        detector_code = (base_dir / "src" / "privacy" / "detector.js").read_text()
        inspector_code = (base_dir / "src" / "privacy" / "inspector_overlay.js").read_text()
        sanitizer_code = (base_dir / "src" / "privacy" / "sanitizer.js").read_text()

        html = """
        <!DOCTYPE html>
        <html>
        <head><title>LiteSight Privacy Test</title></head>
        <body style="padding: 40px; font-family: sans-serif;">
          <h2>LiteSight Test Form</h2>
          <div style="margin-bottom: 20px;">
            <label for="pwd">Password (Empty - should be MONITORED):</label><br/>
            <input type="password" id="pwd" name="password" placeholder="Enter password" style="width: 250px; padding: 6px;">
          </div>
          <div style="margin-bottom: 20px;">
            <label for="cc">Credit Card (Filled - should be REDACTED):</label><br/>
            <input type="text" id="cc" name="card_number" value="4111-2222-3333-4444" style="width: 250px; padding: 6px;">
          </div>
          <div style="margin-bottom: 20px;">
            <label for="mail">Email (Filled):</label><br/>
            <input type="email" id="mail" name="email" value="alex@example.com" style="width: 250px; padding: 6px;">
          </div>
          <p id="prose-cc">Your previous card on file was 5555-4444-3333-2222.</p>
        </body>
        </html>
        """

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html)

            # Inject scripts
            await page.evaluate(detector_code)
            await page.evaluate(inspector_code)
            await page.evaluate(sanitizer_code)

            # 1. Balanced mode inspection
            res = await page.evaluate("async () => await window.LiteSightPrivacyPipeline.sanitizeCurrentView()")
            assert res["detectedCount"] >= 3
            assert res["monitoredCount"] >= 1
            assert res["redactedCount"] >= 2

            # 2. In-page badges verification
            badges = await page.evaluate("""() => {
                const container = document.getElementById('litesight-visual-overlays-container');
                if (!container) return [];
                return Array.from(container.querySelectorAll('.ls-privacy-badge')).map(b => b.innerText.trim());
            }""")
            assert any("MONITORED" in b for b in badges)
            assert any("REDACTED" in b for b in badges)

            # 3. Element attributes verification
            pwd_privacy = await page.evaluate("() => document.getElementById('pwd').getAttribute('data-litesight-privacy')")
            cc_privacy = await page.evaluate("() => document.getElementById('cc').getAttribute('data-litesight-privacy')")
            assert pwd_privacy == "monitored"
            assert cc_privacy == "redacted"

            # 4. Disable email category
            res_no_email = await page.evaluate("""async () => {
                window.LiteSightPIIDetector.setConfig({ categories: { emails: false } });
                return await window.LiteSightPrivacyPipeline.sanitizeCurrentView();
            }""")
            email_detected = any(b["type"] == "EMAIL" for b in res_no_email["boxes"])
            assert not email_detected

            # 5. Disable visual indicators
            await page.evaluate("() => window.LiteSightInspector.toggleVisualIndicators(false)")
            overlay_html = await page.evaluate("() => document.getElementById('litesight-visual-overlays-container').innerHTML")
            assert overlay_html == ""

            await browser.close()

    asyncio.run(_run())
