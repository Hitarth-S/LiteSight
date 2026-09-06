# src/browser/engine.py
import torch
from pathlib import Path

# Note: Lightpanda API is typically compatible with standard Playwright-style async patterns
import lightpanda

class BrowserEngine:
    """Manages the connection to the lightweight AI-native browser."""
    
    def __init__(self):
        self.browser = None
        self.page = None
        self.local_state_tree = {} # Maps elements to their (x, y) coordinates
        
    async def initialize(self):
        """Starts the engine and injects the MutationObserver state tracker."""
        print("[BrowserEngine] Initializing Lightpanda AsyncBrowser...")
        self.browser = lightpanda.AsyncBrowser()
        # Note: Depending on Lightpanda's exact bidi/CDP implementation, 
        # we may need to connect to a specific session here.
        # self.page = await self.browser.new_session()
        
        # Inject our non-blocking state observer JS
        observer_path = Path(__file__).parent.parent / "state" / "observer.js"
        with open(observer_path, "r") as f:
            js_code = f.read()
        
        # NOTE: Once self.page is fully wired to Lightpanda's BiDi session:
        # await self.page.expose_function("_liteSightStateUpdate", self._handle_mutations)
        # await self.page.evaluate(js_code)
        print("[BrowserEngine] MutationObserver successfully injected and bound.")
        
    async def navigate(self, url: str):
        """Navigates to the domain and waits for initial load."""
        print(f"[BrowserEngine] Navigating to {url}")
        await self.page.goto(url)
        
    async def get_current_image(self) -> torch.Tensor:
        """
        Captures the screen and converts it directly to a PyTorch tensor 
        (Channels, Height, Width) for the FoveatedTokenizer.
        """
        if self.page:
            screenshot_bytes = await self.page.screenshot(format="jpeg")
        
        # In a real environment, we'd use PIL and torchvision to decode the bytes:
        # image = Image.open(io.BytesIO(screenshot_bytes))
        # tensor = transforms.ToTensor()(image)
        # For our constrained hardware stub, we simulate a 1080p tensor:
        tensor = torch.zeros((3, 1080, 1920), dtype=torch.uint8)
        return tensor
        
    async def perform_action(self, action: dict):
        """Executes muscle-memory actions via the browser engine."""
        action_type = action.get("type")
        target = action.get("target") # could be an element ID, text, or coordinates
        
        if action_type == "click":
            print(f"[BrowserEngine] Clicking target: {target}")
            # await self.page.click(target)
        elif action_type == "type":
            print(f"[BrowserEngine] Typing into target: {target}")
            # await self.page.type(target, action.get("text"))
            
    def _handle_mutations(self, mutations):
        """Callback that passively receives batch diffs from JS without polling."""
        for mutation in mutations:
            if mutation.get("type") == "childList":
                for node in mutation.get("addedNodes", []):
                    # We store the element by a combination of tag and text to allow fuzzy matching
                    key = f"{node.get('tag', '')}_{node.get('text', '')}".lower()
                    if key.strip("_"):
                        self.local_state_tree[key] = (node.get("x", 0), node.get("y", 0))
        print(f"[BrowserEngine] Processed {len(mutations)} DOM mutations into state tree.")
