# main.py
"""
Entry point for LiteSight Edge Web Agent.
Runs Fast-Path Indexed DOM, Pure Visual Zero-DOM Inference, or Local Multi-Agent Swarms.
Language: STE (Simplified Technical English).
"""

import asyncio
import argparse
from dotenv import load_dotenv
from typing import Optional
import playwright.async_api as pw

from src.orchestrator.executor import Orchestrator
from src.browser.engine import BrowserEngine
from src.vision.foveation import FoveatedTokenizer

# Load environment secrets strictly from .env
load_dotenv()


async def run_agent(
    target_url: str,
    initial_goal: Optional[str] = None,
    pure_vision: bool = False,
    use_swarm: bool = False,
    headless: bool = False,
    storage_state: Optional[str] = None,
    save_session: bool = False,
    pii_config: Optional[dict] = None
):
    """Initializes and runs the LiteSight agent lifecycle."""
    print("Initializing LiteSight Agent (Constrained Edge Mode)...")
    if pure_vision:
        print("[Main] Mode: Pure Visual Inference (Zero-DOM Dependency).")
    elif use_swarm:
        print("[Main] Mode: Local Multi-Agent Swarm with Local Message Bus.")
    else:
        print("[Main] Mode: Fast-Path Indexed DOM First.")

    vision_api = FoveatedTokenizer(base_resolution=(1920, 1080), patch_size=224)
    browser_api = BrowserEngine(headless=headless, storage_state_path=storage_state, pii_config=pii_config)

    print("[Main] Launching Browser Engine and injecting JS observer...")
    try:
        await browser_api.initialize()
    except NotImplementedError:
        print("[Main] Note: API initialized in simulated headless mode.")

    orchestrator = Orchestrator(
        vision_api=vision_api,
        browser_api=browser_api,
        pure_vision=pure_vision,
        use_swarm=use_swarm
    )

    print(f"\n[Slow Planner] Starting navigation phase for: {target_url}")
    try:
        await browser_api.navigate(target_url)
    except (pw.Error, TimeoutError) as nav_err:
        print(f"[Main] Navigation notice: {nav_err}")

    try:
        await orchestrator.run(target_url, initial_goal)

        if save_session or storage_state:
            await browser_api.save_storage_state(storage_state)

        print("\nLiteSight Agent run completed.")
        if not headless:
            print("Keeping browser window open for 10 seconds for human observation...")
            await asyncio.sleep(10)
    finally:
        await browser_api.close()


def main():
    parser = argparse.ArgumentParser(description="LiteSight Edge-Optimized Privacy-First Web Agent")
    parser.add_argument("--url", type=str, required=True, help="Target URL to navigate to")
    parser.add_argument("--goal", type=str, default=None, help="Initial goal override (skips slow planner)")
    parser.add_argument("--pure-vision", action="store_true", help="Enable 100%% pixel-to-coordinate zero-DOM mode")
    parser.add_argument("--swarm", action="store_true", help="Enable local multi-agent swarm architecture")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--storage-state", type=str, default=None, help="Path to JSON file to load/save session cookies and state")
    parser.add_argument("--save-session", action="store_true", help="Persist browser session cookies to storage state after run")
    parser.add_argument("--pii-sensitivity", type=str, choices=["relaxed", "balanced", "strict"], default="balanced", help="PII detection sensitivity level")
    parser.add_argument("--pii-categories", type=str, default=None, help="Comma-separated PII categories to actively scan/redact (e.g. 'credit_cards,passwords,emails,names')")
    parser.add_argument("--no-visual-indicators", action="store_true", help="Disable in-page visual privacy indicators/badges")
    args = parser.parse_args()

    # W3: Validate URL scheme to prevent file:// and javascript: attacks
    if not args.url.lower().startswith(("http://", "https://")):
        print("[Main] Error: Only http:// and https:// URLs are supported.")
        return

    # Parse PII configuration
    pii_config = {
        "sensitivity": args.pii_sensitivity,
        "visual_indicators": not args.no_visual_indicators
    }
    if args.pii_categories:
        enabled_cats = [c.strip().lower() for c in args.pii_categories.split(",") if c.strip()]
        all_cats = ["credit_cards", "passwords", "emails", "names", "phone_numbers", "government_ids"]
        pii_config["categories"] = {cat: (cat in enabled_cats) for cat in all_cats}

    asyncio.run(run_agent(
        target_url=args.url,
        initial_goal=args.goal,
        pure_vision=args.pure_vision,
        use_swarm=args.swarm,
        headless=args.headless,
        storage_state=args.storage_state,
        save_session=args.save_session,
        pii_config=pii_config
    ))


if __name__ == "__main__":
    main()
