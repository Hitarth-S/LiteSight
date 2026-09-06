import asyncio
import argparse
from dotenv import load_dotenv
from src.orchestrator.executor import Orchestrator
from src.browser.engine import BrowserEngine
from src.vision.foveation import FoveatedTokenizer

# Load environment variables (e.g. OPENAI_API_KEY)
load_dotenv()

async def run_agent(target_url: str, initial_goal: str = None):
    print("Initializing LiteSight Agent (Constrained Edge Mode)...")
    vision_api = FoveatedTokenizer(base_resolution=(1920, 1080), patch_size=224)
    browser_api = BrowserEngine()
    
    print("[Main] Launching Browser Engine and injecting JS observer...")
    try:
        await browser_api.initialize()
    except NotImplementedError:
        print("[Main] Note: Lightpanda API is still initializing/stubbed. Continuing in simulated mode.")
        
    orchestrator = Orchestrator(vision_api, browser_api)
    
    print(f"\n[Slow Planner] Starting planning phase for: {target_url}")
    try:
        await browser_api.navigate(target_url)
    except Exception:
        pass
    
    await orchestrator.run(target_url, initial_goal)
    
    print("\nLiteSight Agent run completed. Leaving browser open for 10 seconds for observation...")
    await asyncio.sleep(10)

def main():
    parser = argparse.ArgumentParser(description="LiteSight Web Agent")
    parser.add_argument("--url", type=str, required=True, help="Target URL to navigate to")
    parser.add_argument("--goal", type=str, default=None, help="Initial goal override (skips slow planner)")
    args = parser.parse_args()
    
    asyncio.run(run_agent(args.url, args.goal))

if __name__ == "__main__":
    main()
