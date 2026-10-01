# src/browser/engine.py
"""
Browser Engine for LiteSight.
Manages Chromium instance via Playwright with Fast-Path Indexed DOM extraction,
On-Device WebGPU privacy sanitization, and strict action execution guards.
Language: STE (Simplified Technical English).
"""

import re
import time
import asyncio
from pathlib import Path
import io
from typing import Dict, Any, Tuple, Optional, List
from PIL import Image
import numpy as np
import playwright.async_api as pw
from playwright.async_api import async_playwright

from ..orchestrator.exceptions import (
    StaleNodeException,
    ElementObscuredError,
    CanvasFallbackTrigger,
    PIIRedactionFailure
)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None


class BrowserEngine:
    """
    Controls browser lifecycle and executes guarded actions on the web page.
    Prioritizes integer-indexed DOM elements and supports zero-DOM coordinate execution.
    """

    def __init__(
        self,
        headless: bool = False,
        storage_state_path: Optional[str] = None,
        pii_config: Optional[Dict[str, Any]] = None
    ):
        self.headless = headless
        self.storage_state_path = storage_state_path
        self.pii_config = pii_config or {}
        self.playwright: Optional[pw.Playwright] = None
        self.browser: Optional[pw.Browser] = None
        self.context: Optional[pw.BrowserContext] = None
        self.page: Optional[pw.Page] = None
        self.local_state_tree: Dict[str, Tuple[int, int]] = {}
        self.latest_snapshot: Optional[Dict[str, Any]] = None
        self.message_bus: Optional[Any] = None
        self.scripts_to_inject: List[Path] = []
        self._background_tasks: set = set()

    def set_message_bus(self, bus):
        self.message_bus = bus

    async def initialize(self):
        """Starts Playwright browser and registers mutation, indexing, and privacy kernels."""
        mode_str = "Headless Mode" if self.headless else "Headed Mode"
        print(f"[BrowserEngine] Initializing Playwright ({mode_str})...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)

        context_kwargs = {}
        if self.storage_state_path and Path(self.storage_state_path).exists():
            print(f"[BrowserEngine] Restoring persistent session from: {self.storage_state_path}")
            context_kwargs["storage_state"] = self.storage_state_path

        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()

        # Scripts to inject on every page load
        base_dir = Path(__file__).parent.parent
        self.scripts_to_inject = [
            base_dir / "state" / "observer.js",
            base_dir / "state" / "snapshot.js",
            base_dir / "privacy" / "detector.js",
            base_dir / "privacy" / "canvas_masker.js",
            base_dir / "privacy" / "sanitizer.js",
            base_dir / "privacy" / "inspector_overlay.js",
        ]

        # Register non-blocking state mutation receiver callback across all tabs
        await self.context.expose_function("_liteSightStateUpdate", self._handle_mutations)

        # Inject scripts at context level so all tabs (and target="_blank" popups) automatically inherit them
        for script_path in self.scripts_to_inject:
            if script_path.exists():
                with open(script_path, "r", encoding="utf-8") as f:
                    js_code = f.read()
                await self.context.add_init_script(js_code)

        # Inject user-defined PII configuration if specified
        if self.pii_config:
            import json
            cfg_json = json.dumps(self.pii_config)
            await self.context.add_init_script(f"""
                if (window.LiteSightPIIDetector) {{
                    window.LiteSightPIIDetector.setConfig({cfg_json});
                }}
            """)

        # Listen for new tab creation (e.g. Amazon opening product in target="_blank")
        self.context.on("page", self._on_new_page)

        print("[BrowserEngine] Observer, Fast-Path Indexer, and WebGPU Privacy Kernels bound.")

    def _on_new_page(self, new_page: pw.Page):
        """Dispatches asynchronous tracking when a new tab/popup opens."""
        task = asyncio.create_task(self._switch_to_new_page(new_page))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _switch_to_new_page(self, new_page: pw.Page):
        """Switches active engine focus to newly opened tab."""
        self.page = new_page
        print(f"[BrowserEngine] New tab detected. Switching active target...")
        try:
            await new_page.bring_to_front()
            await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
        except (pw.Error, TimeoutError, Exception):
            pass

    async def navigate(self, url: str):
        """Navigates to URL and waits for dynamic client redirects/reloads to settle."""
        if not url or not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Insecure or invalid URL: '{url}'. Only http:// and https:// URLs are allowed.")

        print(f"[BrowserEngine] Navigating to {url}")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except pw.Error:
            # Some SPAs never finish loading; proceed with whatever rendered
            pass

        # Wait for any secondary client-side redirect or reload (e.g. Amazon session refresh)
        for _ in range(8):
            try:
                state = await self.page.evaluate("() => document.readyState")
                if state in ["interactive", "complete"]:
                    has_nodes = await self.page.query_selector("input, button, [role='button'], a")
                    if has_nodes:
                        break
            except pw.Error:
                pass
            await asyncio.sleep(0.5)

        await asyncio.sleep(1.0)

    async def get_indexed_dom_state(self, retries: int = 3) -> Dict[str, Any]:
        """
        Extracts Fast-Path Indexed DOM snapshot with retry resilience for in-flight navigations.
        Returns dictionary matching Section 7.B.1 schema.
        """
        for attempt in range(retries):
            try:
                # Ensure the page is still valid and not closed
                if self.page and self.page.is_closed() and self.context and self.context.pages:
                    self.page = self.context.pages[-1]

                # Ensure snapshot function exists; re-inject if needed
                fn_exists = await self.page.evaluate("() => typeof window.generateLiteSightSnapshot === 'function'")
                if not fn_exists:
                    snapshot_file = Path(__file__).parent.parent / "state" / "snapshot.js"
                    if snapshot_file.exists():
                        with open(snapshot_file, "r", encoding="utf-8") as f:
                            await self.page.evaluate(f.read())

                snapshot = await self.page.evaluate("() => window.generateLiteSightSnapshot()")
                if snapshot and isinstance(snapshot, dict):
                    elements = snapshot.get("elements", [])
                    if elements:
                        self.latest_snapshot = snapshot
                        return snapshot
                    elif attempt < retries - 1:
                        # Page might still be mounting interactive SPA elements
                        await asyncio.sleep(0.8)
                        continue
                if snapshot:
                    self.latest_snapshot = snapshot
                    return snapshot
            except pw.Error as err:
                err_msg = str(err).lower()
                if ("destroyed" in err_msg or "navigat" in err_msg or "closed" in err_msg) and attempt < retries - 1:
                    await asyncio.sleep(0.8)
                    continue
                if attempt == retries - 1:
                    print(f"[BrowserEngine] Warning: Snapshot extraction fallback after {retries} attempts: {err}")
            except Exception as err:
                print(f"[BrowserEngine] Warning: Snapshot extraction error: {err}")
                break

        return {
            "timestamp": int(time.time() * 1000),
            "url": self.page.url if self.page and not self.page.is_closed() else "",
            "elements": []
        }

    async def sanitize_visual_frame(self) -> Dict[str, Any]:
        """
        Executes on-device PII detection and context-preserving synthetic vector masking.
        Raises PIIRedactionFailure if sanitization kernel fails.
        """
        try:
            detection_res = await self.page.evaluate(
                "async () => await window.LiteSightPrivacyPipeline.sanitizeCurrentView()"
            )
            detected_count = detection_res.get("detectedCount", 0)
            redacted_count = detection_res.get("redactedCount", 0)
            monitored_count = detection_res.get("monitoredCount", 0)
            sensitivity = detection_res.get("config", {}).get("sensitivity", "BALANCED")

            # Update live inspector overlay (non-blocking diagnostic HUD)
            try:
                await self.page.evaluate(
                    """([detected, monitored, redacted, sens]) => {
                        if (window.LiteSightInspector) window.LiteSightInspector.updateSanitizedStats(detected, monitored, redacted, sens);
                    }""",
                    [detected_count, monitored_count, redacted_count, sensitivity]
                )
            except Exception:
                pass

            return detection_res
        except (pw.Error, KeyError, ValueError, RuntimeError) as err:
            print(f"[BrowserEngine] Privacy Kernel Error: {err}")
            raise PIIRedactionFailure(f"WebGPU privacy kernel failed frame sanitization: {err}")

    async def save_storage_state(self, path: Optional[str] = None) -> Optional[str]:
        """Saves current browser session cookies and localStorage to file."""
        target_path = path or self.storage_state_path or "storage_state.json"
        if self.context:
            await self.context.storage_state(path=target_path)
            print(f"[BrowserEngine] Persistent session saved to: {target_path}")
            return target_path
        return None

    async def dismiss_overlays(self):
        """Dismiss modal popups, cookie banners, and overlay dialogs that block clicks."""
        try:
            # Check for blocking dialogs / location prompts (do NOT press Escape blindly, as it closes cart drawers)
            overlay_selectors = [
                # Flipkart & general login modal close
                'button._2KpZ6l._2doB4z',
                'button._30XB9F',
                'span._30XB9F',
                'button:has-text("✕")',
                'button:has-text("×")',
                # Amazon & general dialog close
                '[data-action="a-popover-close"]',
                '.modal-close', '.close-btn', '.close-modal',
                '[aria-label="Close" i]',
                '[aria-label="Dismiss" i]',
                'button[data-dismiss="modal"]',
                '.a-popover-footer button',
                'div[role="dialog"] button[aria-label*="close" i]',
                # Newsletter / promotional / subscription popups
                'button:has-text("No thanks")',
                'button:has-text("No, thanks")',
                'button:has-text("Not now")',
                'button:has-text("Maybe later")',
                'button:has-text("Dismiss")',
                'button:has-text("Skip")',
                'button:has-text("Continue without supporting")',
                '[class*="newsletter" i] button[aria-label*="close" i]',
                '[class*="subscription" i] button[aria-label*="close" i]',
                # General cookie banners & GDPR prompts
                '#onetrust-accept-btn-handler',
                '#onetrust-reject-all-handler',
                '.cookie-accept',
                'button[id*="cookie" i]:has-text("Accept")',
                'button[class*="cookie" i]:has-text("Accept")',
                'button:has-text("Accept All")',
                'button:has-text("Accept all cookies")',
                'button:has-text("Accept Cookies")',
                'button:has-text("Allow All")',
                'button:has-text("Allow all cookies")',
                'button:has-text("I Agree")',
                'button:has-text("I agree")',
                'button:has-text("Got it")',
                'button:has-text("Agree & Continue")',
                'button:has-text("OK")',
            ]
            dismissed = 0
            for sel in overlay_selectors:
                if dismissed >= 2:
                    break
                try:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click(timeout=500)
                        dismissed += 1
                        await asyncio.sleep(0.1)
                except pw.Error:
                    continue
        except pw.Error:
            pass

    async def execute_action(
        self,
        operation: str,
        target_index: Optional[int] = None,
        text_value: Optional[str] = None,
        label: Optional[str] = None
    ) -> bool:
        """
        Executes action on discrete integer indexed element.
        Enforces freshness, occlusion, and non-DOM guards.
        """
        start_time = time.time()
        operation = operation.upper()

        if operation == "DONE":
            print("[BrowserEngine] Goal reached. Operation DONE.")
            return True

        if operation in ["SCROLL_DOWN", "SCROLL_UP"]:
            scroll_delta = 600 if operation == "SCROLL_DOWN" else -600
            print(f"[BrowserEngine] Executing {operation} (delta={scroll_delta}px)")
            try:
                # 1. Reliable JS window scroll
                await self.page.evaluate("([delta]) => { window.scrollBy({ top: delta, behavior: 'instant' }); }", [scroll_delta])
                # 2. Also dispatch wheel in viewport center to trigger event listeners
                vp = self.page.viewport_size or {"width": 1280, "height": 800}
                await self.page.mouse.move(vp["width"] / 2, vp["height"] / 2)
                await self.page.mouse.wheel(0, scroll_delta)
            except pw.Error:
                pass
            # Yield for layout reflow and lazy-loaded items
            await asyncio.sleep(0.8)
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._update_inspector_hud(f"{operation}", elapsed_ms)
            return True

        if operation in ["PRESS_ENTER", "ENTER"]:
            print(f"[BrowserEngine] Executing Fast-Path ENTER keypress")
            await self.page.keyboard.press("Enter")
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._update_inspector_hud("ENTER", elapsed_ms)
            return True

        if operation in ["EXTRACT_AND_ANSWER", "SUMMARIZE", "ANSWER"]:
            print(f"[BrowserEngine] Executing {operation} for query: '{text_value}'")
            try:
                # Wait briefly for dynamic AJAX table / list filtering to settle
                await asyncio.sleep(1.2)

                page_info = await self.page.evaluate("""() => {
                    const textBlocks = [];

                    // 1. Prioritize visible table rows (e.g. DataTables, problem statements, spec sheets)
                    const rows = document.querySelectorAll('table tbody tr');
                    for (const r of rows) {
                        const style = window.getComputedStyle(r);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            const cells = Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim()).filter(Boolean);
                            if (cells.length > 0) {
                                textBlocks.push(cells.join(' | '));
                            }
                        }
                    }

                    // 2. Structured cards, articles, and content blocks
                    const nodes = document.querySelectorAll('h1, h2, h3, h4, [role="article"], .card, .content, .problem-statement, .table');
                    for (const n of nodes) {
                        const t = (n.innerText || '').trim();
                        if (t.length > 25 && !textBlocks.some(b => b.includes(t))) {
                            textBlocks.push(t);
                        }
                    }

                    return {
                        title: document.title,
                        url: window.location.href,
                        text: textBlocks.slice(0, 50).join('\\n\\n') || (document.body ? document.body.innerText.substring(0, 4000) : '')
                    };
                }""")

                query_str = (text_value or "").lower()
                query_words = [w for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', query_str) if len(w) > 2 and w not in ['the', 'tell', 'what', 'then', 'and', 'for', 'with', 'about', 'is', 'query', 'context']]

                paragraphs = page_info["text"].split("\n\n")
                scored_paragraphs = []
                for p in paragraphs:
                    p_lower = p.lower()
                    score = sum(3 for qw in query_words if qw in p_lower)
                    # Significant boost for IDs / numbers (e.g. '26171')
                    for qw in query_words:
                        if qw.isdigit() and qw in p_lower:
                            score += 25
                    if score > 0:
                        scored_paragraphs.append((score, p))

                scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
                if scored_paragraphs:
                    extracted_snippet = "\n\n".join([p for _, p in scored_paragraphs[:3]])
                else:
                    extracted_snippet = page_info["text"][:1000] if page_info["text"] else "No textual content found on current page."

                print(f"\n=======================================================")
                print(f"  [LiteSight Intelligence & Extraction]")
                print(f"  Query: {text_value}")
                print(f"  Source: {page_info['url']}")
                print(f"-------------------------------------------------------")
                print(f"{extracted_snippet.strip()}")
                print(f"=======================================================\n")
            except Exception as e:
                print(f"[BrowserEngine] Extraction notice: {e}")
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._update_inspector_hud("ANSWER", elapsed_ms)
            return True

        if target_index is None:
            if operation == "WAIT":
                await asyncio.sleep(1.5)
                return True
            raise ValueError("Action target_index cannot be null for standard DOM interactions.")

        # Guard 1: Freshness check with dynamic label fallback
        try:
            element_handle = await self.page.query_selector(f'[data-litesight-index="{target_index}"], [data-ls-id="{target_index}"]')
            if not element_handle and label:
                # Fallback: re-query dynamically mounted/re-rendered element by text/label
                escaped = label.replace('"', '\\"').strip()
                if len(escaped) > 1:
                    try:
                        element_handle = await self.page.query_selector(
                            f'button:has-text("{escaped}"), a:has-text("{escaped}"), [aria-label*="{escaped}"]'
                        )
                    except pw.Error:
                        pass
            if not element_handle:
                raise StaleNodeException(f"Node [{target_index}] is stale or absent in current DOM tree.")

            # Guard 2: Canvas or non-DOM element check
            tag_name = await element_handle.evaluate("el => el.tagName.toLowerCase()")
            if tag_name in ["canvas", "webgl", "iframe"]:
                raise CanvasFallbackTrigger(f"Target [{target_index}] resides inside non-indexed <{tag_name}> element.")

            # Guard 3: Visibility and occlusion check
            is_visible = await element_handle.is_visible()
            box = await element_handle.bounding_box()
            if not is_visible or not box or box["width"] <= 0 or box["height"] <= 0 or box["x"] < -500:
                x_coord = box['x'] if box else 'None'
                raise ElementObscuredError(f"Target [{target_index}] is obscured, invisible, or off-screen cloak (x={x_coord}).")
        except pw.Error as err:
            err_msg = str(err).lower()
            if "destroyed" in err_msg or "navigat" in err_msg:
                raise StaleNodeException(f"Execution context was destroyed during navigation on node [{target_index}]: {err}") from err
            elif "not attached" in err_msg or "stale" in err_msg or "detached" in err_msg:
                raise StaleNodeException(f"Node [{target_index}] detached from DOM during query: {err}") from err
            else:
                raise StaleNodeException(f"Node [{target_index}] query failed: {err}") from err

        # Visual indicator and viewport adjustment
        try:
            await element_handle.evaluate("""el => {
                try {
                    const rect = el.getBoundingClientRect();
                    const pageY = rect.top + window.scrollY;
                    if (rect.top < 0 || rect.bottom > window.innerHeight) {
                        window.scrollTo({ top: Math.max(0, pageY - 80), behavior: 'instant' });
                    }
                    el.scrollIntoView({ behavior: 'auto', block: 'center' });
                    el.style.transition = 'all 0.2s ease';
                    el.style.outline = '3px solid #38bdf8';
                    el.style.boxShadow = '0 0 18px rgba(56, 189, 248, 0.85)';
                } catch(e) {}
            }""")
            # Brief human-observable pause to see targeted element
            await asyncio.sleep(0.4)
        except (pw.Error, AttributeError):
            pass

        # Dispatch operation
        try:
            if operation == "CLICK":
                print(f"[BrowserEngine] Executing Fast-Path CLICK on [{target_index}] at ({box['x'] + box['width']/2:.0f}, {box['y'] + box['height']/2:.0f})")
                prev_pages_count = len(self.context.pages) if self.context else 1
                try:
                    await element_handle.click(timeout=4000)
                except pw.Error as click_err:
                    err_lower = str(click_err).lower()
                    if "outside of the viewport" in err_lower or "obscured" in err_lower or "timeout" in err_lower:
                        print(f"[BrowserEngine] Native click resisted ({click_err}). Retrying with window scroll & force...")
                        try:
                            # Scroll window directly to ensure element is in viewport
                            await element_handle.evaluate("""el => {
                                const pageY = el.getBoundingClientRect().top + window.scrollY;
                                window.scrollTo({ top: Math.max(0, pageY - 80), behavior: 'instant' });
                            }""")
                            await asyncio.sleep(0.3)
                            await element_handle.click(force=True, timeout=2000)
                        except pw.Error as force_err:
                            force_lower = str(force_err).lower()
                            if "destroyed" in force_lower or "navigat" in force_lower:
                                raise
                            print(f"[BrowserEngine] Force click also resisted. Falling back to direct DOM dispatch...")
                            await element_handle.evaluate("el => { el.focus(); el.click(); }")
                    else:
                        raise

                # Check if click opened a new tab/popup (e.g. target="_blank" product detail)
                if self.context and len(self.context.pages) > prev_pages_count:
                    new_tab = self.context.pages[-1]
                    print(f"[BrowserEngine] Detected new tab navigation. Switching active target to new tab...")
                    self.page = new_tab
                    try:
                        await new_tab.bring_to_front()
                        await new_tab.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    await asyncio.sleep(1.5)
            elif operation in ["TYPE_TEXT", "TYPE_AND_SUBMIT"]:
                print(f"[BrowserEngine] Executing Fast-Path {operation} on [{target_index}] -> '{text_value}'")
                # Step 1: Focus/activate the input field (resilient to sticky headers and viewport checks)
                try:
                    await element_handle.focus()
                    await element_handle.click(timeout=1000, force=True)
                except pw.Error:
                    try:
                        await element_handle.focus()
                    except pw.Error:
                        pass
                await asyncio.sleep(0.1)  # Brief yield for SPA focus events

                # Step 2: Re-query element by index.
                fresh_handle = await self.page.query_selector(f'[data-litesight-index="{target_index}"], [data-ls-id="{target_index}"]')

                try:
                    if fresh_handle:
                        await fresh_handle.fill("")
                        await fresh_handle.type(text_value or "", delay=65)
                    else:
                        print(f"[BrowserEngine] Fresh handle not found for [{target_index}]; using keyboard dispatch.")
                        await self.page.keyboard.type(text_value or "", delay=65)
                except pw.Error as fill_err:
                    print(f"[BrowserEngine] Direct fill failed ({fill_err}); using keyboard dispatch.")
                    await self.page.keyboard.type(text_value or "", delay=65)

                # Auto-submit: press Enter after typing into search inputs
                if operation == "TYPE_AND_SUBMIT":
                    await asyncio.sleep(0.1)
                    await self.page.keyboard.press("Enter")
                    print(f"[BrowserEngine] Auto-submitted search query via Enter keypress.")
                    # Wait for navigation after search submission
                    try:
                        await self.page.wait_for_load_state("domcontentloaded", timeout=6000)
                    except Exception:
                        pass
                    await asyncio.sleep(2.0)  # Let search results render
            elif operation == "SELECT":
                print(f"[BrowserEngine] Executing Fast-Path SELECT on [{target_index}] -> '{text_value}'")
                val = (text_value or "").strip()
                selected = False
                try:
                    await element_handle.select_option(value=val, timeout=2000)
                    selected = True
                except pw.Error:
                    pass
                if not selected:
                    try:
                        await element_handle.select_option(label=val, timeout=2000)
                        selected = True
                    except pw.Error:
                        pass
                if not selected:
                    # Case-insensitive / partial match in JS
                    await element_handle.evaluate("""(el, targetText) => {
                        const targetLower = (targetText || '').toLowerCase();
                        let matched = false;
                        if (el.options) {
                            for (let i = 0; i < el.options.length; i++) {
                                const opt = el.options[i];
                                const oText = (opt.text || '').toLowerCase().trim();
                                const oVal = (opt.value || '').toLowerCase().trim();
                                if (oVal === targetLower || oText === targetLower || oText.includes(targetLower) || (targetLower.length > 2 && targetLower.includes(oText))) {
                                    el.selectedIndex = i;
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    matched = true;
                                    break;
                                }
                            }
                            if (!matched && el.options.length > 0) {
                                el.selectedIndex = 0;
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    }""", val)
            elif operation == "WAIT":
                await asyncio.sleep(1.5)
            else:
                print(f"[BrowserEngine] Unhandled operation: {operation}")
        except pw.Error as err:
            err_msg = str(err).lower()
            if "destroyed" in err_msg or "navigat" in err_msg:
                # The click action successfully dispatched and triggered page navigation
                print(f"[BrowserEngine] Navigation successfully triggered by click on [{target_index}]. Loading page...")
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(1.5)  # Allow destination page (e.g. product detail) to mount
                return True
            elif "not attached" in err_msg or "stale" in err_msg or "detached" in err_msg:
                raise StaleNodeException(f"Node [{target_index}] detached from DOM during {operation}: {err}") from err
            elif "not visible" in err_msg or "obscured" in err_msg:
                raise ElementObscuredError(f"Node [{target_index}] obscured during {operation}: {err}") from err
            else:
                raise StaleNodeException(f"Node [{target_index}] interaction failed: {err}") from err

        # Clear visual indicator
        try:
            await element_handle.evaluate("""el => {
                try {
                    el.style.outline = '';
                    el.style.boxShadow = '';
                } catch(e) {}
            }""")
        except (pw.Error, AttributeError):
            pass

        elapsed_ms = int((time.time() - start_time) * 1000)
        await self._update_inspector_hud(f"{operation} [{target_index}]", elapsed_ms)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=500)
        except Exception:
            pass
        return True

    async def execute_coordinate_action(
        self,
        operation: str,
        x: int,
        y: int,
        text_value: Optional[str] = None
    ) -> bool:
        """
        Executes action directly at screen coordinates (x, y).
        Enables Pure Visual Inference (Zero-DOM Dependency).
        """
        start_time = time.time()
        operation = operation.upper()

        print(f"[BrowserEngine] Executing Zero-DOM Coordinate Action: {operation} at ({x}, {y})")
        if operation == "CLICK":
            await self.page.mouse.click(x, y)
        elif operation == "TYPE_TEXT":
            await self.page.mouse.click(x, y)
            await asyncio.sleep(0.2)
            await self.page.keyboard.type(text_value or "", delay=40)
            await asyncio.sleep(0.4)
        elif operation in ["SCROLL_DOWN", "SCROLL_UP"]:
            scroll_delta = 600 if operation == "SCROLL_DOWN" else -600
            await self.page.mouse.move(x, y)
            await self.page.mouse.wheel(0, scroll_delta)
        elif operation == "WAIT":
            await asyncio.sleep(1.5)

        elapsed_ms = int((time.time() - start_time) * 1000)
        await self._update_inspector_hud(f"{operation} ({x},{y})", elapsed_ms)
        await asyncio.sleep(1.0)
        return True

    async def _update_inspector_hud(self, action_str: str, latency_ms: int):
        """Updates live metrics in the browser inspector HUD."""
        try:
            await self.page.evaluate(
                """([action, latency]) => {
                    if (window.LiteSightInspector) window.LiteSightInspector.updateAction(action, latency);
                }""",
                [action_str, latency_ms]
            )
        except (pw.Error, AttributeError):
            pass

    async def get_current_image(self) -> Any:
        """Captures frame tensor or array for foveated visual fallback."""
        try:
            png_bytes = await self.page.screenshot(type="png")
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            arr = np.array(img)  # (H, W, 3) uint8
            arr = arr.transpose(2, 0, 1)  # (3, H, W)
            if TORCH_AVAILABLE:
                return torch.from_numpy(arr.copy())
            return arr
        except Exception as e:
            print(f"[BrowserEngine] Screenshot capture failed: {e}. Returning blank frame.")
            if TORCH_AVAILABLE:
                return torch.zeros((3, 1080, 1920), dtype=torch.uint8)
            return np.zeros((3, 1080, 1920), dtype=np.uint8)

    def _handle_mutations(self, mutations):
        """Passively receives mutation diffs without polling."""
        for mutation in mutations:
            if mutation.get("type") == "childList":
                for node in mutation.get("addedNodes", []):
                    key = f"{node.get('tag', '')}_{node.get('text', '')}".lower()
                    if key.strip("_"):
                        self.local_state_tree[key] = (node.get("x", 0), node.get("y", 0))

        if self.message_bus and mutations:
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self.message_bus.publish("dom.mutation_batch", {"mutations": mutations}, sender="BrowserEngine")
                )
            except RuntimeError:
                pass  # No event loop available

    async def close(self):
        """Closes browser session gracefully."""
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
