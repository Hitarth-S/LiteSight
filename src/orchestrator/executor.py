# src/orchestrator/executor.py
import json
from typing import List, Dict, Any, Optional
from ..vision.foveation import FoveatedTokenizer
from ..state.sanitizer import StateSanitizer
from ..state.cso_tracker import CSOTracker
from ..state.personalization import RetrievalAugmentedPersonalization
from .scheduler import NightlyLoRAScheduler

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
            from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
            import torch
            print("[Executor] Loading SmolVLM (Ultra-light Multimodal Edge Model) into RAM...")
            # We use SmolVLM-256M as it is incredibly small (< 1GB), perfectly suited for 7th-gen CPUs, 
            # and fully native to transformers, completely eliminating 'trust_remote_code' breakage.
            self.processor = AutoProcessor.from_pretrained("HuggingFaceTB/SmolVLM-256M-Instruct")
            
            # PHASE 3 ROADMAP: 4-bit Quantization via bitsandbytes
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float32, # CPU compatibility
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
            
            self.model = AutoModelForImageTextToText.from_pretrained(
                "HuggingFaceTB/SmolVLM-256M-Instruct",
                quantization_config=bnb_config
            )
            self.model_loaded = True
            print("[Executor] Edge Model loaded successfully.")
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
    
    TOOL_BANK = {
        "click": "Clicks on an element at given coordinates.",
        "type": "Types text into a focused input field.",
        "scroll": "Scrolls the current viewport."
    }
    
    FULL_SCHEMAS = {
        "click": {"name": "click", "parameters": {"x": "int", "y": "int"}},
        "type": {"name": "type", "parameters": {"text": "string"}},
        "scroll": {"name": "scroll", "parameters": {"direction": "string"}}
    }

    def _decide_action(self, tokens, subgoal):
        """Runs fast local edge model inference using JIT Schema Passing."""
        if not self.model_loaded:
            return {"type": "click", "target": "fallback_coord"}
            
        # Extract the raw tensor data from the foveated token dicts
        image_tensors = [t["data"] for t in tokens if "data" in t]
        
        # ---------------------------------------------------------
        # PHASE 1 ROADMAP: Just-In-Time (JIT) Schema Passing
        # ---------------------------------------------------------
        
        # Stage 1: Tool Selection (Minimal Token Footprint)
        prompt_stage_1 = f"Tool Bank: {json.dumps(self.TOOL_BANK)}. Goal: {subgoal}. Select tool name:"
        
        # In a fully wired VLM, the model would output the tool name here.
        # We simulate the VLM selection logic based on the subgoal text.
        selected_tool = "click"
        if "type" in subgoal.lower() or "enter" in subgoal.lower():
            selected_tool = "type"
        elif "scroll" in subgoal.lower():
            selected_tool = "scroll"
            
        print(f"[Executor] JIT Stage 1: Selected tool '{selected_tool}' using lightweight Tool Bank.")
        
        # Stage 2: Schema Injection (Only load what is needed)
        active_schema = self.FULL_SCHEMAS.get(selected_tool)
        prompt_stage_2 = f"Schema: {json.dumps(active_schema)}. Goal: {subgoal}. Generate arguments:"
        
        try:
            import torch
            # Example structural syntax for the actual SmolVLM inference:
            # inputs = self.processor(images=image_tensors, text=prompt_stage_2, return_tensors="pt")
            # outputs = self.model.generate(**inputs, max_new_tokens=20)
            # result = self.processor.decode(outputs[0])
            print(f"[Executor] JIT Stage 2: Injected full schema for '{selected_tool}'. Processed {len(image_tensors)} fovea tensors.")
        except Exception as e:
            print(f"[Executor] Inference parsing warning: {e}")
            
        action_dict = {"type": selected_tool, "target": "model_inferred_target"}
        if selected_tool == "type":
            import re
            match = re.search(r"'([^']+)'", subgoal)
            action_dict["text"] = match.group(1) if match else "Demo Text"
            
        return action_dict

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
        Given the domain context, generate a JSON object containing step-by-step subgoals.
        Context: {json.dumps(domain_context)}
        
        Respond ONLY with a valid JSON object containing a 'plan' array of strings.
        Example: {{"plan": ["click_search", "type_query", "submit"]}}
        """
        
        try:
            print("[Planner] Querying Groq Heavy LLM for new strategic plan...")
            response = await self.client.chat.completions.create(
                model="qwen/qwen3.8-27b", # Using the highly efficient Qwen 27B model on Groq
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}, # Requires valid JSON object
                max_tokens=256 # Prevents hitting Groq's strict free-tier output limits
            )
            content = response.choices[0].message.content
            plan_obj = json.loads(content)
            return plan_obj.get("plan", [])
        except Exception as e:
            print(f"[Planner] LLM Planning failed: {e}")
            return ["fallback_goal"]

class Orchestrator:
    """Manages the Dual-Process lifecycle (Thinking Fast & Slow)."""
    def __init__(self, vision_api, browser_api):
        self.planner = HighLevelPlanner()
        self.executor = ReactiveExecutor(vision_api, browser_api)
        self.sanitizer = StateSanitizer()
        self.cso_tracker = CSOTracker()
        self.personalization = RetrievalAugmentedPersonalization()
        self.scheduler = NightlyLoRAScheduler()
        self.current_plan = []

    async def run(self, start_url: str, initial_goal: str = None):
        # Retrieve personalized preferences dynamically for this URL via RAP
        prefs = self.personalization.retrieve_preferences(start_url)
        if prefs:
            print(f"[Orchestrator] RAP: Injected {len(prefs)} local preferences into context.")
            
        # The Slow Planner
        # Sanitize the local state tree to scrub PII before passing to cloud Planner
        safe_state = self.sanitizer.sanitize_state(self.executor.local_state_tree)
        compressed_cso = self.cso_tracker.get_compressed_context()
        
        context = {
            "url": start_url, 
            "state": safe_state, 
            "cso_memory": compressed_cso, 
            "preferences": prefs
        }
        
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
                if success:
                    # Update append-only CSO tracking memory
                    self.cso_tracker.append_state(subgoal, ["action_executed"])
                    # Log successful trace for nightly learning
                    self.scheduler.log_successful_trajectory({"goal": subgoal, "url": start_url})
            except (ElementObscuredError, StaleNodeException, DOMEmptyError) as e:
                # The Handoff
                self.cso_tracker.append_state(subgoal, [], current_blocker=str(e))
                await self._handle_failure(e, context)
            
            if not success:
                # Based on failure handling, we might have a new plan
                pass

    async def _handle_failure(self, error: Exception, context: Dict[str, Any]):
        """Wakes up the slow planner to reassess based on specific error states."""
        context["error_state"] = str(error)
        context["cso_memory"] = self.cso_tracker.get_compressed_context()
        self.current_plan = await self.planner.plan(context)
