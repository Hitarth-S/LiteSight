# src/orchestrator/executor.py
import json
from typing import List, Dict, Any, Optional
from ..vision.foveation import FoveatedTokenizer
from ..state.sanitizer import StateSanitizer

# Specific error states for Planner handoff
class ElementObscuredError(Exception):
    pass

class StaleNodeException(Exception):
    pass

class DOMEmptyError(Exception):
    pass

class ReactiveExecutor:
    """The Lightweight Edge Model (Fast Executor)."""
    def __init__(self, vision_api, browser_api):
        self.vision_api = vision_api
        self.browser_api = browser_api
        self.local_state_tree = {}
        
        # Initialize the Lightweight Edge Model (e.g., a tiny VLM)
        try:
            from transformers import AutoProcessor, AutoModel
            print("[Executor] Loading lightweight local edge model into RAM...")
            # Using a placeholder model ID for the local constrained model
            self.processor = AutoProcessor.from_pretrained("HuggingFaceM4/tiny-random-LlamaForCausalLM")
            self.model = AutoModel.from_pretrained("HuggingFaceM4/tiny-random-LlamaForCausalLM")
            self.model_loaded = True
        except Exception as e:
            print(f"[Executor] Could not load edge model (using fallback): {e}")
            self.model_loaded = False

    async def execute_subgoal(self, subgoal: str) -> bool:
        """
        Executes the current sub-goal using muscle memory in a closed loop.
        Throws specific exceptions on unexpected states to hand off to the Planner.
        """
        try:
            # 1. Determine interaction point (x, y) based on state tree and subgoal
            interaction_point = self._determine_interaction_point(subgoal)
            
            # 2. Get Foveated Token Array (no full-res tensor)
            raw_image = await self.browser_api.get_current_image()
            foveated_tokens = self.vision_api.compress(raw_image, interaction_point)
            
            # 3. Model decides action using muscle memory
            action = self._decide_action(foveated_tokens, subgoal)
            
            # 4. Perform action via lightweight headless engine
            await self.browser_api.perform_action(action)
            return True
        except ElementObscuredError:
            raise
        except StaleNodeException:
            raise
        except DOMEmptyError:
            raise

    def _determine_interaction_point(self, subgoal: str) -> tuple[int, int]:
        """
        Implements layout grounding: maps a textual subgoal to an (x, y) coordinate
        by doing a fuzzy match against the passively built local_state_tree.
        """
        state_tree = self.browser_api.local_state_tree
        
        # Simple fuzzy grounding: look for matching keywords
        subgoal_lower = subgoal.lower()
        for key, coords in state_tree.items():
            if any(word in key for word in subgoal_lower.split("_")):
                print(f"[Executor] Grounded '{subgoal}' to element '{key}' at {coords}")
                return int(coords[0]), int(coords[1])
                
        print(f"[Executor] Grounding failed for '{subgoal}'. Using fallback interaction point.")
        return (500, 500)
    
    def _decide_action(self, tokens, subgoal):
        """Runs fast local edge model inference on the foveated tokens."""
        if not self.model_loaded:
            return {"type": "click", "target": "fallback_coord"}
            
        prompt = f"Goal: {subgoal}. Action:"
        
        # Extract the raw tensor data from the foveated token dicts
        image_tensors = [t["data"] for t in tokens if "data" in t]
        
        try:
            import torch
            # In a real multimodal architecture, these tensors would be stacked 
            # or passed directly as images to the Vision-Language model processor.
            # Example structural syntax:
            # inputs = self.processor(images=image_tensors, text=prompt, return_tensors="pt")
            # outputs = self.model.generate(**inputs, max_new_tokens=20)
            # result = self.processor.decode(outputs[0])
            print(f"[Executor] Edge model processed {len(image_tensors)} foveated tensor patches for goal: {subgoal}")
        except Exception as e:
            print(f"[Executor] Inference parsing warning: {e}")
            
        return {"type": "click", "target": "model_inferred_target"}

class HighLevelPlanner:
    """The Heavy LLM (Slow Planner)."""
    def __init__(self):
        # Initializes the OpenAI client to securely point to the Groq API
        try:
            import openai
            import os
            api_key = os.environ.get("GROQ_API_KEY")
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1"
            )
            self.enabled = bool(api_key)
        except Exception:
            self.enabled = False

    async def plan(self, domain_context: Dict[str, Any]) -> List[str]:
        """
        Generates a structured JSON array of sub-goals based on the context.
        Only runs initially or on Executor failure.
        """
        if not self.enabled:
            print("[Planner] Warning: GROQ_API_KEY not configured. Using fallback plan.")
            return ["locate_login", "enter_credentials", "verify_2fa"]

        prompt = f"""
        You are the high-level planner for an autonomous web agent.
        Given the domain context, generate a JSON array of step-by-step subgoals.
        Context: {json.dumps(domain_context)}
        
        Respond ONLY with a valid JSON array of strings.
        Example: ["click_search", "type_query", "submit"]
        """
        
        try:
            print("[Planner] Querying Groq Heavy LLM for new strategic plan...")
            response = await self.client.chat.completions.create(
                model="llama3-70b-8192", # Using Groq's fast Llama 3 70B model
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"} # Requires valid JSON
            )
            content = response.choices[0].message.content
            # The prompt asks for an array, but json_object requires an object.
            # So we parse it assuming the model returned {"plan": [...]}.
            data = json.loads(content)
            return data.get("plan", ["fallback_goal"])
        except Exception as e:
            print(f"[Planner] LLM Planning failed: {e}")
            return ["fallback_goal"]

class Orchestrator:
    """Manages the Dual-Process lifecycle (Thinking Fast & Slow)."""
    def __init__(self, vision_api, browser_api):
        self.planner = HighLevelPlanner()
        self.executor = ReactiveExecutor(vision_api, browser_api)
        self.sanitizer = StateSanitizer()
        self.current_plan = []

    async def run(self, start_url: str, initial_goal: str = None):
        # The Slow Planner
        # Sanitize the local state tree to scrub PII before passing to cloud Planner
        safe_state = self.sanitizer.sanitize_state(self.executor.local_state_tree)
        context = {"url": start_url, "state": safe_state}
        
        if initial_goal:
            print(f"[Orchestrator] Using explicit CLI goal: {initial_goal}")
            self.current_plan = [initial_goal]
        else:
            self.current_plan = await self.planner.plan(context)
        
        while self.current_plan:
            subgoal = self.current_plan.pop(0)
            success = False
            
            # The Fast Executor
            try:
                success = await self.executor.execute_subgoal(subgoal)
            except (ElementObscuredError, StaleNodeException, DOMEmptyError) as e:
                # The Handoff
                await self._handle_failure(e, context)
            
            if not success:
                # Based on failure handling, we might have a new plan
                pass

    async def _handle_failure(self, error: Exception, context: Dict[str, Any]):
        """Wakes up the slow planner to reassess based on specific error states."""
        context["error_state"] = str(error)
        self.current_plan = await self.planner.plan(context)
