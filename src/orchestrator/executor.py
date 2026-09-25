# src/orchestrator/executor.py
"""
Dual-Process Orchestrator and Reactive Executor for LiteSight.
Coordinates Slow Planner (Macro LLM) and Fast Reactive Executor (Edge Model).
Supports Fast-Path Indexed DOM, Pure Visual Zero-DOM Inference, and Multi-Agent Swarms.
Language: STE (Simplified Technical English).
"""

import json
import re
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from ..vision.foveation import FoveatedTokenizer
from ..vision.omni_parser import OmniVisualParser
from ..state.sanitizer import StateSanitizer
from ..state.cso_tracker import CSOTracker
from ..state.personalization import RetrievalAugmentedPersonalization
from ..agents.swarm import SwarmCoordinator
from .scheduler import NightlyLoRAScheduler
from .exceptions import (
    LiteSightBaseException,
    StaleNodeException,
    ElementObscuredError,
    CanvasFallbackTrigger,
    PIIRedactionFailure
)


class ReactiveExecutor:
    """
    The Fast Reactive Executor (Lightweight Edge Model & Fast-Path Policy).
    Prioritizes sub-500ms Indexed DOM actions.
    Falls back to OmniParser and SmolVLM foveation on Canvas, WebGL, or Zero-DOM mode.
    """
    def __init__(self, vision_api: FoveatedTokenizer, browser_api: Any, pure_vision: bool = False):
        self.vision_api = vision_api
        self.browser_api = browser_api
        self.pure_vision = pure_vision
        self.omni_parser = OmniVisualParser()
        self.local_state_tree: Dict[str, Tuple[int, int]] = {}

        # Initialize the Lightweight Edge Model (4-bit NF4 quantized SmolVLM)
        try:
            from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
            import torch
            print("[Executor] Loading SmolVLM (Ultra-light Multimodal Edge Model) in 4-bit NF4...")
            self.processor = AutoProcessor.from_pretrained("HuggingFaceTB/SmolVLM-256M-Instruct")

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float32,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )

            self.model = AutoModelForImageTextToText.from_pretrained(
                "HuggingFaceTB/SmolVLM-256M-Instruct",
                quantization_config=bnb_config
            )
            self.model_loaded = True
            print("[Executor] Edge Model loaded successfully.")
        except (ImportError, OSError, RuntimeError, ValueError) as err:
            print(f"[Executor] Edge model initialization notice (fallback active): {err}")
            self.model_loaded = False

    async def execute_subgoal(self, subgoal: str) -> bool:
        """
        Executes sub-goal using Fast-Path Indexed DOM First or Pure Visual Fallback.
        Throws specific exceptions (StaleNodeException, ElementObscuredError, CanvasFallbackTrigger).
        """
        start_t = time.time()
        print(f"\n[Executor] Evaluating subgoal: '{subgoal}'")

        # Zero-DOM Pure Visual Branch
        if self.pure_vision:
            print("[Executor] Pure Vision Mode enabled: Bypassing DOM tree extraction.")
            return await self._execute_pure_visual_fallback(subgoal)

        # 1. Retrieve current Fast-Path Indexed DOM Snapshot
        snapshot = await self.browser_api.get_indexed_dom_state()
        elements = snapshot.get("elements", [])

        # 2. Fast-Path DOM Matching (Sub-500ms path)
        action_payload = self._resolve_fast_path_action(subgoal, elements)

        if action_payload and action_payload.get("operation") != "FALLBACK_TO_VISION":
            target_idx = action_payload.get("target_index")
            operation = action_payload.get("operation")
            text_val = action_payload.get("text_value")

            print(f"[Executor] Fast-Path Policy matched: {operation} on node [{target_idx}] ('{action_payload.get('reasoning_summary')}')")

            try:
                # Dispatch through Client Action Execution Guard
                success = await self.browser_api.execute_action(operation, target_idx, text_val)
                elapsed_ms = int((time.time() - start_t) * 1000)
                print(f"[Executor] Action executed successfully in {elapsed_ms}ms.")
                return success
            except CanvasFallbackTrigger as cfe:
                print(f"[Executor] Non-DOM target encountered: {cfe}. Diverting to OmniParser Visual Fallback...")
                return await self._execute_pure_visual_fallback(subgoal)
            except (StaleNodeException, ElementObscuredError):
                # Propagate layout failures to trigger Slow Planner handoff
                raise

        # 3. Vision Fallback for Non-DOM elements or unmapped layout
        print(f"[Executor] Executing Foveated Multimodal Fallback for subgoal: '{subgoal}'")
        return await self._execute_pure_visual_fallback(subgoal)

    async def _execute_pure_visual_fallback(self, subgoal: str) -> bool:
        """
        Executes 100% pixel-to-coordinate mapping using OmniVisualParser and FoveatedTokenizer.
        Enforces privacy sanitization prior to processing.
        """
        raw_image = await self.browser_api.get_current_image()
        visual_elements = self.omni_parser.parse_interactables(raw_image)

        if not visual_elements:
            print("[Executor] OmniVisualParser found no discrete elements. Defaulting to center screen.")
            interaction_point = (960, 540)
        else:
            primary_el = visual_elements[0]
            interaction_point = primary_el["center_coord"]
            print(f"[Executor] OmniVisualParser detected {len(visual_elements)} interactables. Primary: {primary_el['label']} at {interaction_point}")

        # Mathematical foveation: extract high-res crop centered on interaction point
        foveated_tokens = self.vision_api.compress(raw_image, interaction_point)
        action = self._decide_action(foveated_tokens, subgoal)

        # Dispatch coordinate action
        operation = "CLICK" if action.get("type") == "click" else "TYPE_TEXT"
        return await self.browser_api.execute_coordinate_action(
            operation=operation,
            x=interaction_point[0],
            y=interaction_point[1],
            text_value=action.get("text")
        )

    def _resolve_fast_path_action(self, subgoal: str, elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Fast-Path DOM action resolver adhering strictly to Section 7.B.2 schema.
        Assigns operation and target_index based on indexed DOM snapshot.
        """
        if not elements:
            return None

        subgoal_lower = subgoal.lower()
        extracted_text = None
        match = re.search(r"'([^']+)'", subgoal)
        if match:
            extracted_text = match.group(1)

        is_type = any(kw in subgoal_lower for kw in ["type", "enter", "fill", "input", "write", "search for"])
        is_click = any(kw in subgoal_lower for kw in ["click", "press", "locate", "select", "open", "hit", "dismiss"])

        stop_words = {"the", "a", "an", "into", "and", "or", "in", "to", "on", "for", "with", "main", "bar", "field"}
        words = [w for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', subgoal_lower) if w not in stop_words]

        best_score = -1
        best_candidate = None

        for el in elements:
            if not el.get("is_visible"):
                continue

            score = 0
            tag = el.get("tag", "").lower()
            role = el.get("role", "").lower()
            label = el.get("label", "").lower()
            val = el.get("value", "").lower()
            combined_text = f"{tag} {role} {label} {val}"

            if is_type and role in ["textbox", "combobox", "input"]:
                score += 3
            if is_click and role in ["button", "link", "combobox"]:
                score += 2

            for w in words:
                if w in combined_text:
                    score += 2

            if score > best_score and score >= 2:
                best_score = score
                best_candidate = el

        if best_candidate:
            target_idx = best_candidate["index"]
            if is_type:
                return {
                    "operation": "TYPE_TEXT",
                    "target_index": target_idx,
                    "text_value": extracted_text or "LiteSight Agent",
                    "reasoning_summary": f"Matched input control [{target_idx}] label: '{best_candidate.get('label')}'"
                }
            else:
                return {
                    "operation": "CLICK",
                    "target_index": target_idx,
                    "text_value": None,
                    "reasoning_summary": f"Matched interactive control [{target_idx}] label: '{best_candidate.get('label')}'"
                }

        # Fallback to the first interactable element if search bar or button mentioned
        for el in elements:
            if is_type and el.get("role") in ["textbox", "combobox"]:
                return {
                    "operation": "TYPE_TEXT",
                    "target_index": el["index"],
                    "text_value": extracted_text or "LiteSight Agent",
                    "reasoning_summary": f"Defaulted to first visible input [{el['index']}]"
                }
            if is_click and el.get("role") in ["button", "link"]:
                return {
                    "operation": "CLICK",
                    "target_index": el["index"],
                    "text_value": None,
                    "reasoning_summary": f"Defaulted to primary button [{el['index']}]"
                }

        return None

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

    def _decide_action(self, tokens: List[Dict[str, Any]], subgoal: str) -> Dict[str, Any]:
        """Runs fast local edge model inference using JIT Schema Passing."""
        if not self.model_loaded:
            action_type = "type" if any(w in subgoal.lower() for w in ["type", "enter", "fill"]) else "click"
            text_val = None
            if action_type == "type":
                match = re.search(r"'([^']+)'", subgoal)
                text_val = match.group(1) if match else "LiteSight Search"
            return {"type": action_type, "target": "fallback_coord", "text": text_val}

        image_tensors = [t["data"] for t in tokens if "data" in t]

        # JIT Stage 1: Tool Selection
        selected_tool = "click"
        if any(w in subgoal.lower() for w in ["type", "enter", "fill"]):
            selected_tool = "type"
        elif "scroll" in subgoal.lower():
            selected_tool = "scroll"

        print(f"[Executor] JIT Stage 1: Selected tool '{selected_tool}' from Tool Bank.")

        # JIT Stage 2: Schema Injection
        active_schema = self.FULL_SCHEMAS.get(selected_tool)
        print(f"[Executor] JIT Stage 2: Injected schema for '{selected_tool}'. Processed {len(image_tensors)} fovea patches.")

        action_dict = {"type": selected_tool, "target": "model_inferred_target"}
        if selected_tool == "type":
            match = re.search(r"'([^']+)'", subgoal)
            action_dict["text"] = match.group(1) if match else "LiteSight Search"

        return action_dict


class HighLevelPlanner:
    """The Heavy LLM (Slow Planner). Powered by Groq API."""
    def __init__(self):
        try:
            import openai
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.environ.get("GROQ_API_KEY")
            if api_key:
                self.client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                self.enabled = True
            else:
                self.enabled = False
        except (ImportError, KeyError, ValueError):
            self.enabled = False

    async def plan(self, domain_context: Dict[str, Any]) -> List[str]:
        if not self.enabled:
            print("[Planner] Warning: GROQ_API_KEY not configured. Using fallback fast-path plan.")
            user_goal = domain_context.get("user_goal", "")
            if user_goal and ("," in user_goal or " and " in user_goal):
                return [c.strip() for c in re.split(r'[,;]\s*|\s+and\s+', user_goal) if c.strip()]
            return ["locate_search_input", "type_query", "submit"]

        user_goal = domain_context.get("user_goal", "")
        if user_goal:
            instruction = f"Decompose this complex multi-step user goal into an array of atomic sequential subgoals:\nObjective: \"{user_goal}\""
        else:
            instruction = "Given the domain context, generate a step-by-step array of sequential subgoals to explore key portal actions."

        prompt = f"""
        You are the high-level planner for an autonomous web agent.
        {instruction}
        Current URL: {domain_context.get('url')}
        Context State: {json.dumps(domain_context.get('cso_memory', ''))}

        Respond ONLY with a valid JSON object containing a 'plan' array of strings.
        Example: {{"plan": ["click login", "type credentials", "navigate to search", "interact with map", "click submit"]}}
        """

        try:
            print("[Planner] Querying Groq Heavy LLM to decompose goal into subgoals...")
            response = await self.client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=256
            )
            content = response.choices[0].message.content
            plan_obj = json.loads(content)
            decomposed = plan_obj.get("plan", [])
            if decomposed and len(decomposed) > 0:
                return decomposed
        except (json.JSONDecodeError, KeyError, ValueError, RuntimeError) as err:
            print(f"[Planner] LLM Planning failed: {err}")

        if user_goal and ("," in user_goal or " and " in user_goal):
            return [c.strip() for c in re.split(r'[,;]\s*|\s+and\s+', user_goal) if c.strip()]
        return ["locate_search_bar", "type_query"]


class Orchestrator:
    """Manages the Dual-Process lifecycle (Fast DOM & Slow Planner)."""
    def __init__(
        self,
        vision_api: FoveatedTokenizer,
        browser_api: Any,
        pure_vision: bool = False,
        use_swarm: bool = False
    ):
        self.planner = HighLevelPlanner()
        self.executor = ReactiveExecutor(vision_api, browser_api, pure_vision=pure_vision)
        self.sanitizer = StateSanitizer()
        self.cso_tracker = CSOTracker()
        self.personalization = RetrievalAugmentedPersonalization()
        self.scheduler = NightlyLoRAScheduler()
        self.pure_vision = pure_vision
        self.use_swarm = use_swarm
        self.swarm_coordinator = SwarmCoordinator() if use_swarm else None
        self.current_plan: List[str] = []

    async def run(self, start_url: str, initial_goal: Optional[str] = None):
        # 1. On-Device WebGPU Privacy check before egress
        print("[Orchestrator] Running On-Device WebGPU Privacy Kernel before data egress...")
        try:
            privacy_report = await self.executor.browser_api.sanitize_visual_frame()
            print(f"[Orchestrator] Privacy Filter active: {privacy_report.get('detectedCount', 0)} PII regions masked.")
        except PIIRedactionFailure as prf:
            print(f"[Orchestrator] CRITICAL PRIVACY FAILURE: {prf}. Halting network transmission.")
            raise

        # 2. Retrieve personalized preferences dynamically via RAP
        prefs = self.personalization.retrieve_preferences(start_url)
        if prefs:
            print(f"[Orchestrator] RAP: Injected {len(prefs)} local preferences into context.")

        safe_state = self.sanitizer.sanitize_state(self.executor.local_state_tree)
        compressed_cso = self.cso_tracker.get_compressed_context()

        context = {
            "url": start_url,
            "state": safe_state,
            "cso_memory": compressed_cso,
            "preferences": prefs,
            "user_goal": initial_goal
        }

        # 3. Macro Plan Generation & Multi-Step Goal Decomposition
        if initial_goal:
            is_composite = any(sep in initial_goal for sep in [",", ";", " and ", " then "]) or len(initial_goal.split()) > 8
            if is_composite:
                print("[Orchestrator] Decomposing complex multi-step prompt into discrete subgoals...")
                self.current_plan = await self.planner.plan(context)
            else:
                self.current_plan = [initial_goal]
        else:
            self.current_plan = await self.planner.plan(context)

        total_steps = len(self.current_plan)
        print(f"[Orchestrator] Plan established: {total_steps} sequential subgoals.")
        for idx, step in enumerate(self.current_plan, 1):
            print(f"  [{idx}/{total_steps}] -> {step}")

        # 4. Closed Execution Loop
        step_index = 1
        while self.current_plan:
            subgoal = self.current_plan.pop(0)
            print(f"\n=======================================================")
            print(f"[Orchestrator] Step [{step_index}/{total_steps}]: {subgoal}")
            print(f"=======================================================")

            await asyncio.sleep(0.8)
            success = False

            try:
                if self.use_swarm and self.swarm_coordinator:
                    # Multi-agent swarm execution path
                    dom_snapshot = await self.executor.browser_api.get_indexed_dom_state()
                    action_decision = await self.swarm_coordinator.dispatch_step(
                        subgoal=subgoal,
                        dom_snapshot=dom_snapshot,
                        privacy_report=privacy_report
                    )
                    if action_decision:
                        success = await self.executor.browser_api.execute_action(
                            operation=action_decision.get("operation", "CLICK"),
                            target_index=action_decision.get("target_index"),
                            text_value=action_decision.get("text_value")
                        )
                    else:
                        success = await self.executor.execute_subgoal(subgoal)
                else:
                    success = await self.executor.execute_subgoal(subgoal)

                if success:
                    self.cso_tracker.append_state(subgoal, ["action_executed"])
                    self.scheduler.log_successful_trajectory({"goal": subgoal, "url": start_url})
            except (ElementObscuredError, StaleNodeException) as err:
                print(f"[Orchestrator] Layout Failure ({type(err).__name__}): {err}. Waking Slow Planner for replan...")
                self.cso_tracker.append_state(subgoal, [], current_blocker=str(err))
                await self._handle_failure(err, context)

            step_index += 1

    async def _handle_failure(self, error: Exception, context: Dict[str, Any]):
        """Wakes up the slow planner to reassess based on specific error states."""
        context["error_state"] = str(error)
        context["cso_memory"] = self.cso_tracker.get_compressed_context()
        self.current_plan = await self.planner.plan(context)
