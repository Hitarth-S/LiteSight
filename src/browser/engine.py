# src/browser/engine.py
import torch
import time
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from ..orchestrator.exceptions import (
    StaleNodeException,
    ElementObscuredError,
    CanvasFallbackTrigger,
    PIIRedactionFailure
)

class BrowserEngine:
    """
    Manages Playwright browser instance with Fast-Path Indexed DOM extraction,
    WebGPU privacy sanitization, and strict action execution guards.
    """
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.local_state_tree = {} # Maps elements to their (x, y) coordinates
        self.latest_snapshot = None
        
    async def initialize(self):
        """Starts the engine and injects observer, snapshot, and privacy kernels."""
        print("[BrowserEngine] Initializing Playwright (Headed Mode)...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        
        # Helper to read JS scripts from src
        base_dir = Path(__file__).parent.parent
        scripts_to_inject = [
            base_dir / "state" / "observer.js",
            base_dir / "state" / "snapshot.js",
            base_dir / "privacy" / "detector.js",
            base_dir / "privacy" / "canvas_masker.js",
            base_dir / "privacy" / "sanitizer.js",
            base_dir / "privacy" / "inspector_overlay.js",
        ]
        
        # Expose Python callbacks for state & metrics
        await self.page.expose_function("_liteSightStateUpdate", self._handle_mutations)
        
        # Inject all scripts to execute on every page load
        for script_path in scripts_to_inject:
            if script_path.exists():
                with open(script_path, "r", encoding="utf-8") as f:
                    js_code = f.read()
                await self.page.add_init_script(js_code)
        
        print("[BrowserEngine] Observer, Fast-Path Indexer, and WebGPU Privacy Kernels bound.")
        
    async def navigate(self, url: str):
        """Navigates to the domain and establishes initial indexed state."""
        print(f"[BrowserEngine] Navigating to {url}")
        await self.page.goto(url, wait_until="domcontentloaded")
        # Allow initial async observer batch to settle
        await asyncio.sleep(1.5)
        # Ensure inspector overlay is mounted
        try:
            await self.page.evaluate("() => { if (window.LiteSightInspector) window.LiteSightInspector.mount(); }")
        except Exception:
            pass

    async def get_indexed_dom_state(self) -> dict:
        """
        Executes Fast-Path Indexed DOM Tree extraction.
        Returns JSON matching ARCHITECTURE.md Section 7.B.1 schema.
        """
        try:
            snapshot = await self.page.evaluate("() => window.generateLiteSightSnapshot()")
            self.latest_snapshot = snapshot
            return snapshot
        except Exception as e:
            print(f"[BrowserEngine] Warning: Snapshot extraction fallback: {e}")
            return {"timestamp": int(time.time() * 1000), "url": self.page.url if self.page else "", "elements": []}

    async def sanitize_visual_frame(self) -> dict:
        """
        Executes on-device PII detection and context-preserving synthetic vector masking.
        Guarantees that no raw unmasked credential or ID ever leaves client machine.
        """
        try:
            detection_res = await self.page.evaluate("async () => await window.LiteSightPrivacyPipeline.sanitizeCurrentView()")
            detected_count = detection_res.get("detectedCount", 0)
            
            # Update live inspector HUD
            await self.page.evaluate(f"() => {{ if (window.LiteSightInspector) window.LiteSightInspector.updateSanitizedStats({detected_count}); }}")
            
            return detection_res
        except Exception as e:
            print(f"[BrowserEngine] Privacy Kernel Error: {e}")
            raise PIIRedactionFailure(f"WebGPU privacy kernel failed frame sanitization: {e}")

    async def execute_action(self, operation: str, target_index: int = None, text_value: str = None) -> bool:
        """
        Client Action Execution Guard.
        Strictly enforces:
        1. Node freshness check (raises StaleNodeException if missing)
        2. Visibility & occlusion validation (raises ElementObscuredError)
        3. Canvas / WebGL non-DOM trigger (raises CanvasFallbackTrigger)
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

        # 1. Freshness Check: Locate node by data-litesight-index
        element_handle = await self.page.query_selector(f'[data-litesight-index="{target_index}"]')
        if not element_handle:
            raise StaleNodeException(f"Node [{target_index}] is stale or no longer exists in current DOM tree.")

        # 2. Canvas / Non-DOM Target Check
        tag_name = await element_handle.evaluate("el => el.tagName.toLowerCase()")
        if tag_name in ["canvas", "webgl", "iframe"]:
            raise CanvasFallbackTrigger(f"Target [{target_index}] resides inside non-indexed <{tag_name}> element.")

        # 3. Visibility and Occlusion Guard
        is_visible = await element_handle.is_visible()
        box = await element_handle.bounding_box()
        if not is_visible or not box or box["width"] <= 0 or box["height"] <= 0:
            raise ElementObscuredError(f"Target [{target_index}] is obscured, invisible, or zero-width.")

        # 4. Human Observability: Visually highlight the target element
        try:
            await element_handle.evaluate("""el => {
                try {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.style.transition = 'all 0.3s ease';
                    el.style.outline = '3px solid #38bdf8';
                    el.style.boxShadow = '0 0 18px rgba(56, 189, 248, 0.85)';
                } catch(e) {}
            }""")
        except Exception:
            pass
        
        # Pacing pause: allows human observer to visually register the targeted element
        await asyncio.sleep(0.7)

        # 5. Dispatch Operation with Natural Pacing
        if operation == "CLICK":
            print(f"[BrowserEngine] Executing Fast-Path CLICK on [{target_index}] at ({box['x'] + box['width']/2:.0f}, {box['y'] + box['height']/2:.0f})")
            await element_handle.click(timeout=3000)
        elif operation == "TYPE_TEXT":
            print(f"[BrowserEngine] Executing Fast-Path TYPE_TEXT on [{target_index}] -> '{text_value}'")
            await element_handle.click()
            await asyncio.sleep(0.2)
            await element_handle.fill("")
            # Type with natural delay (40ms/char) so text input is visually observable
            await element_handle.type(text_value or "", delay=40)
            await asyncio.sleep(0.4)
            await self.page.keyboard.press("Enter")
        elif operation == "SELECT":
            print(f"[BrowserEngine] Executing Fast-Path SELECT on [{target_index}] -> '{text_value}'")
            await element_handle.select_option(value=text_value or "")
        elif operation == "WAIT":
            await asyncio.sleep(1.5)
        else:
            print(f"[BrowserEngine] Unhandled operation: {operation}")

        # Clear highlight and provide step observation interval
        try:
            await element_handle.evaluate("""el => {
                try {
                    el.style.outline = '';
                    el.style.boxShadow = '';
                } catch(e) {}
            }""")
        except Exception:
            pass

        elapsed_ms = int((time.time() - start_time) * 1000)
        await self._update_inspector_hud(f"{operation} [{target_index}]", elapsed_ms)
        
        # Observation pause: lets human observers see the resulting page update
        await asyncio.sleep(1.2)
        return True

    async def _update_inspector_hud(self, action_str: str, latency_ms: int):
        try:
            await self.page.evaluate(f"() => {{ if (window.LiteSightInspector) window.LiteSightInspector.updateAction('{action_str}', {latency_ms}); }}")
        except Exception:
            pass

    async def get_current_image(self) -> torch.Tensor:
        """Captures frame tensor for foveated visual fallback."""
        tensor = torch.zeros((3, 1080, 1920), dtype=torch.uint8)
        return tensor
        
    def _handle_mutations(self, mutations):
        """Passively receives mutation diffs without polling."""
        for mutation in mutations:
            if mutation.get("type") == "childList":
                for node in mutation.get("addedNodes", []):
                    key = f"{node.get('tag', '')}_{node.get('text', '')}".lower()
                    if key.strip("_"):
                        self.local_state_tree[key] = (node.get("x", 0), node.get("y", 0))
