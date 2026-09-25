# main.py
"""
Entry point for LiteSight Edge Web Agent.
Runs Fast-Path Indexed DOM, Pure Visual Zero-DOM Inference, or Local Multi-Agent Swarms.
Language: STE (Simplified Technical English).
"""

import asyncio
import argparse
from dotenv import load_dotenv
import playwright.async_api as pw

from src.orchestrator.executor import Orchestrator
from src.browser.engine import BrowserEngine
from src.vision.foveation import FoveatedTokenizer

# Load environment secrets strictly from .env
load_dotenv()


async def run_agent(
    target_url: str,
    initial_goal: str = None,
    pure_vision: bool = False,
    use_swarm: bool = False
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
    browser_api = BrowserEngine()

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

    await orchestrator.run(target_url, initial_goal)

    print("\nLiteSight Agent run completed.")
    print("Keeping browser window open for 10 seconds for human observation...")
    await asyncio.sleep(10)
    await browser_api.close()


def main():
    parser = argparse.ArgumentParser(description="LiteSight Edge-Optimized Privacy-First Web Agent")
    parser.add_argument("--url", type=str, required=True, help="Target URL to navigate to")
    parser.add_argument("--goal", type=str, default=None, help="Initial goal override (skips slow planner)")
    parser.add_argument("--pure-vision", action="store_true", help="Enable 100% pixel-to-coordinate zero-DOM mode")
    parser.add_argument("--swarm", action="store_true", help="Enable local multi-agent swarm architecture")
    args = parser.parse_args()

    asyncio.run(run_agent(
        target_url=args.url,
        initial_goal=args.goal,
        pure_vision=args.pure_vision,
        use_swarm=args.swarm
    ))


if __name__ == "__main__":
    main()
