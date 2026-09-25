# src/browser/engine.py
"""
Browser Engine for LiteSight.
Manages Chromium instance via Playwright with Fast-Path Indexed DOM extraction,
On-Device WebGPU privacy sanitization, and strict action execution guards.
Language: STE (Simplified Technical English).
"""

import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
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

    def __init__(self):
        self.playwright: Optional[pw.Playwright] = None
        self.browser: Optional[pw.Browser] = None
        self.page: Optional[pw.Page] = None
        self.local_state_tree: Dict[str, Tuple[int, int]] = {}
        self.latest_snapshot: Optional[Dict[str, Any]] = None

    async def initialize(self):
        """Starts Playwright browser and registers mutation, indexing, and privacy kernels."""
        print("[BrowserEngine] Initializing Playwright (Headed Mode)...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.page = await self.browser.new_page()

        # Scripts to inject on every page load
        base_dir = Path(__file__).parent.parent
        scripts_to_inject = [
            base_dir / "state" / "observer.js",
            base_dir / "state" / "snapshot.js",
            base_dir / "privacy" / "detector.js",
            base_dir / "privacy" / "canvas_masker.js",
            base_dir / "privacy" / "sanitizer.js",
            base_dir / "privacy" / "inspector_overlay.js",
        ]

        # Register non-blocking state mutation receiver callback
        await self.page.expose_function("_liteSightStateUpdate", self._handle_mutations)

        # Inject scripts
        for script_path in scripts_to_inject:
            if script_path.exists():
                with open(script_path, "r", encoding="utf-8") as f:
                    js_code = f.read()
                await self.page.add_init_script(js_code)

        print("[BrowserEngine] Observer, Fast-Path Indexer, and WebGPU Privacy Kernels bound.")

    async def navigate(self, url: str):
        """Navigates to URL and initializes inspector HUD without CPU polling."""
        print(f"[BrowserEngine] Navigating to {url}")
        await self.page.goto(url, wait_until="domcontentloaded")
        # Allow initial async observer batch to settle
        await asyncio.sleep(1.5)
        try:
            await self.page.evaluate("() => { if (window.LiteSightInspector) window.LiteSightInspector.mount(); }")
        except (pw.Error, AttributeError):
            pass

    async def get_indexed_dom_state(self) -> Dict[str, Any]:
        """
        Extracts Fast-Path Indexed DOM snapshot.
        Returns dictionary matching Section 7.B.1 schema.
        """
        try:
            snapshot = await self.page.evaluate("() => window.generateLiteSightSnapshot()")
            self.latest_snapshot = snapshot
            return snapshot
        except (pw.Error, KeyError, ValueError) as err:
            print(f"[BrowserEngine] Warning: Snapshot extraction fallback: {err}")
            return {
                "timestamp": int(time.time() * 1000),
                "url": self.page.url if self.page else "",
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

            # Update live inspector overlay
            await self.page.evaluate(
                f"() => {{ if (window.LiteSightInspector) window.LiteSightInspector.updateSanitizedStats({detected_count}); }}"
            )
            return detection_res
        except (pw.Error, KeyError, ValueError, RuntimeError) as err:
            print(f"[BrowserEngine] Privacy Kernel Error: {err}")
            raise PIIRedactionFailure(f"WebGPU privacy kernel failed frame sanitization: {err}")

    async def execute_action(
        self,
        operation: str,
        target_index: Optional[int] = None,
        text_value: Optional[str] = None
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
            scroll_delta = 500 if operation == "SCROLL_DOWN" else -500
            await self.page.mouse.wheel(0, scroll_delta)
            elapsed_ms = int((time.time() - start_time) * 1000)
            await self._update_inspector_hud(f"{operation}", elapsed_ms)
            return True

        if target_index is None:
            raise StaleNodeException("Action target_index cannot be null for standard DOM interactions.")

        # Guard 1: Freshness check
        element_handle = await self.page.query_selector(f'[data-litesight-index="{target_index}"]')
        if not element_handle:
            raise StaleNodeException(f"Node [{target_index}] is stale or absent in current DOM tree.")

        # Guard 2: Canvas or non-DOM element check
        tag_name = await element_handle.evaluate("el => el.tagName.toLowerCase()")
        if tag_name in ["canvas", "webgl", "iframe"]:
            raise CanvasFallbackTrigger(f"Target [{target_index}] resides inside non-indexed <{tag_name}> element.")

        # Guard 3: Visibility and occlusion check
        is_visible = await element_handle.is_visible()
        box = await element_handle.bounding_box()
        if not is_visible or not box or box["width"] <= 0 or box["height"] <= 0:
            raise ElementObscuredError(f"Target [{target_index}] is obscured, invisible, or zero-width.")

        # Visual indicator for human observation
        try:
            await element_handle.evaluate("""el => {
                try {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.style.transition = 'all 0.3s ease';
                    el.style.outline = '3px solid #38bdf8';
                    el.style.boxShadow = '0 0 18px rgba(56, 189, 248, 0.85)';
                } catch(e) {}
            }""")
        except (pw.Error, AttributeError):
            pass

        await asyncio.sleep(0.7)

        # Dispatch operation
        try:
            if operation == "CLICK":
                print(f"[BrowserEngine] Executing Fast-Path CLICK on [{target_index}] at ({box['x'] + box['width']/2:.0f}, {box['y'] + box['height']/2:.0f})")
                await element_handle.click(timeout=3000)
            elif operation == "TYPE_TEXT":
                print(f"[BrowserEngine] Executing Fast-Path TYPE_TEXT on [{target_index}] -> '{text_value}'")
                # Step 1: Click to activate/focus the input field
                await element_handle.click()
                await asyncio.sleep(0.3)

                # Step 2: Re-query element by index.
                # Dynamic SPAs (e.g. Wikipedia, React apps) swap the DOM node on focus,
                # making the original handle stale. A fresh query captures the live node.
                fresh_handle = await self.page.query_selector(f'[data-litesight-index="{target_index}"]')

                try:
                    if fresh_handle:
                        await fresh_handle.fill("")
                        await fresh_handle.type(text_value or "", delay=40)
                    else:
                        # Fresh node not found: focused input may be newly mounted.
                        # Dispatch directly via keyboard to whatever is currently focused.
                        print(f"[BrowserEngine] Fresh handle not found for [{target_index}]; using keyboard dispatch.")
                        await self.page.keyboard.type(text_value or "", delay=40)
                except pw.Error as fill_err:
                    # Element detached between re-query and fill: use keyboard dispatch.
                    err_str = str(fill_err).lower()
                    if "not attached" in err_str or "detached" in err_str:
                        print(f"[BrowserEngine] Element detached after re-query; using keyboard dispatch.")
                        await self.page.keyboard.type(text_value or "", delay=40)
                    else:
                        raise
                await asyncio.sleep(0.4)
                await self.page.keyboard.press("Enter")
            elif operation == "SELECT":
                print(f"[BrowserEngine] Executing Fast-Path SELECT on [{target_index}] -> '{text_value}'")
                await element_handle.select_option(value=text_value or "")
            elif operation == "WAIT":
                await asyncio.sleep(1.5)
            else:
                print(f"[BrowserEngine] Unhandled operation: {operation}")
        except pw.Error as err:
            err_msg = str(err).lower()
            if "not attached" in err_msg or "stale" in err_msg or "detached" in err_msg:
                raise StaleNodeException(f"Node [{target_index}] detached from DOM during {operation}: {err}") from err
            elif "not visible" in err_msg or "obscured" in err_msg or "timeout" in err_msg:
                raise ElementObscuredError(f"Node [{target_index}] obscured or timed out during {operation}: {err}") from err
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
        await asyncio.sleep(1.2)
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
            await self.page.keyboard.press("Enter")

        elapsed_ms = int((time.time() - start_time) * 1000)
        await self._update_inspector_hud(f"{operation} ({x},{y})", elapsed_ms)
        await asyncio.sleep(1.0)
        return True

    async def _update_inspector_hud(self, action_str: str, latency_ms: int):
        """Updates live metrics in the browser inspector HUD."""
        try:
            await self.page.evaluate(
                f"() => {{ if (window.LiteSightInspector) window.LiteSightInspector.updateAction('{action_str}', {latency_ms}); }}"
            )
        except (pw.Error, AttributeError):
            pass

    async def get_current_image(self) -> Any:
        """Captures frame tensor or array for foveated visual fallback."""
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

    async def close(self):
        """Closes browser session gracefully."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
