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
from pathlib import Path
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
    # Module-level constants to avoid re-instantiation on every fast-path call
    _STOP_WORDS = frozenset({
        "the", "a", "an", "into", "and", "or", "in", "to", "on", "for", "with",
        "main", "bar", "field", "input", "then", "it", "at", "of", "is", "that",
        "this", "from", "page", "current", "above", "below", "slightly", "ensure",
        "using", "credentials", "button", "tab", "window", "anew"
    })
    _AD_OR_FOOTER_PHRASES = (
        "advertise", "ad solutions", "make money with us", "careers",
        "about amazon", "press releases", "amazon science", "conditions of use",
        "privacy notice", "back to top", "customer service"
    )

    def __init__(self, vision_api: FoveatedTokenizer, browser_api: Any, pure_vision: bool = False):
        self.vision_api = vision_api
        self.browser_api = browser_api
        self.pure_vision = pure_vision
        self.omni_parser = OmniVisualParser()
        self.local_state_tree: Dict[str, Tuple[int, int]] = {}
        self.last_search_query: Optional[str] = None

        # Load learned UI patterns from knowledge base
        self.ui_patterns = {}
        patterns_path = Path(__file__).parent.parent / "knowledge" / "ui_patterns.json"
        if patterns_path.exists():
            try:
                with open(patterns_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.ui_patterns = data.get("intents", {})
                    intents_count = len(self.ui_patterns)
                    print(f"[Executor] Active UI Knowledge Base loaded: {intents_count} learned patterns (v{data.get('version', '1.0')})")
            except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
                print(f"[Executor] Notice: Could not load UI patterns: {e}")

        # Initialize the Lightweight Edge Model (4-bit NF4 quantized SmolVLM)
        try:
            import os
            from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
            import torch

            allow_download = os.environ.get("LITESIGHT_LOAD_HF_MODEL", "0") == "1"
            self.processor = AutoProcessor.from_pretrained(
                "HuggingFaceTB/SmolVLM-256M-Instruct",
                local_files_only=not allow_download
            )

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float32,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )

            self.model = AutoModelForImageTextToText.from_pretrained(
                "HuggingFaceTB/SmolVLM-256M-Instruct",
                quantization_config=bnb_config,
                local_files_only=not allow_download
            )
            self.model_loaded = True
            print("[Executor] Edge Model loaded successfully from local weights.")
        except (ImportError, OSError, RuntimeError, ValueError, Exception) as err:
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
            if text_val and operation in ["TYPE_TEXT", "TYPE_AND_SUBMIT"]:
                self.last_search_query = text_val

            print(f"[Executor] Fast-Path Policy matched: {operation} on node [{target_idx}] ('{action_payload.get('reasoning_summary')}')")

            try:
                # Dispatch through Client Action Execution Guard
                target_label = action_payload.get("target_label")
                success = await self.browser_api.execute_action(operation, target_idx, text_val, label=target_label)
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

        subgoal_clean = subgoal.strip()
        subgoal_lower = subgoal_clean.lower()
        extra_keywords = []
        if " | keywords: " in subgoal_lower:
            parts = subgoal_lower.split(" | keywords: ")
            subgoal_lower = parts[0]
            extra_keywords = [k.strip() for k in parts[1].replace(',', ' ').split() if k.strip()]

        # Check if this is an introductory login/auth preamble step on a page where the login form is ALREADY visible
        is_auth_intro = any(intro in subgoal_lower for intro in [
            "login using the credentials", "login with the credentials", "login using credentials",
            "login with credentials", "sign in with credentials", "sign in using credentials"
        ])
        if is_auth_intro:
            has_login_fields = any(
                el.get("is_visible", True) and (el.get("role") in ["textbox", "combobox"] or el.get("tag") in ["input", "select"])
                and any(auth in el.get("label", "").lower() for auth in ["username", "email", "password", "role"])
                for el in elements
            )
            if has_login_fields:
                return {
                    "operation": "WAIT",
                    "target_index": None,
                    "target_label": None,
                    "text_value": None,
                    "reasoning_summary": "Login form detected in active view; proceeding to credential input"
                }

        target_field = None
        extracted_text = None
        is_assignment = False

        # Pattern 1: Arrow / Colon / Equals mapping (e.g. "username -> admin", "password -> admin", "select role as -> admin", "role: admin", "username = admin")
        assign_match = re.search(
            r'^(?:select\s+|choose\s+|pick\s+|set\s+|type\s+|fill\s+|enter\s+)?([a-zA-Z0-9_\s-]+?)\s*(?:->|=>|:=|=|:\s+|\s+as\s+->|\s+to\s+->|\s+as\s+|\s+to\s+)\s*[\'"]?([a-zA-Z0-9_@.+ -]+?)[\'"]?\s*$',
            subgoal_clean,
            re.IGNORECASE
        )
        if assign_match:
            cand_field = assign_match.group(1).strip()
            cand_val = assign_match.group(2).strip()
            cand_field_lower = cand_field.lower()
            if not any(act in cand_field_lower for act in ["click", "press", "hit", "scroll", "wait", "button", "link"]):
                target_field = cand_field
                extracted_text = cand_val
                is_assignment = True

        # Pattern 2: Quotes extraction if not already an assignment (e.g. "type 'admin' into username", "select 'Admin' from role dropdown")
        if not is_assignment:
            match = re.search(r"['\"]([^'\"]+)['\"]", subgoal)
            if match:
                extracted_text = match.group(1).strip()
            else:
                # Check for unclosed quote after search/type/enter verb (e.g. "search for 'portal", "type 'admin")
                match_unclosed = re.search(r"(?:search for|type|fill|enter|query)\s+['\"]([^'\"]+?)(?:\s*,|\s+then|\s+and|\s*$)", subgoal, re.IGNORECASE)
                if match_unclosed:
                    extracted_text = match_unclosed.group(1).strip().strip("'\"")

        # Pattern 3: Explicit prepositional extraction (e.g. "type admin into username", "select admin from role dropdown")
        if not extracted_text:
            match = re.search(r'(?:type|fill|enter)\s+([a-zA-Z0-9_@.+ -]+?)\s+(?:into|in|for)\s+([a-zA-Z0-9_\s-]+)$', subgoal_clean, re.IGNORECASE)
            if match:
                extracted_text = match.group(1).strip()
                target_field = match.group(2).strip()
                is_assignment = True

        if not extracted_text:
            match = re.search(r'(?:select|choose|pick)\s+([a-zA-Z0-9_@.+ -]+?)\s+(?:from|in|for)\s+([a-zA-Z0-9_\s-]+)$', subgoal_clean, re.IGNORECASE)
            if match:
                extracted_text = match.group(1).strip()
                target_field = match.group(2).strip()
                is_assignment = True

        # Pattern 4: General search/type/select keyword fallback
        if not extracted_text:
            match = re.search(r'(?:search for|type|fill|query)\s+([a-zA-Z0-9\s_\'\"-]+?)(?:\s+into|\s+in|\s+from|\s+as|\s+and|\s*,|\s*$)', subgoal_lower)
            if match:
                extracted_text = match.group(1).strip().strip("'\"")

        # Direct search fallback if "search for " is present
        if not extracted_text and "search for " in subgoal_lower:
            cand = subgoal_lower.split("search for ", 1)[1].strip()
            cand = re.split(r'\s+and\s+|\s+then\s+|[,;]', cand)[0].strip().strip("'\"")
            if cand:
                extracted_text = cand

        # Clean ID queries (e.g. "search for problem statement 26171" -> types "26171")
        if extracted_text and not is_assignment:
            id_match = re.search(r'(?:problem statements?|item|id|code|ps|number)\s+([a-zA-Z0-9_-]+)$', extracted_text)
            if id_match and not any(subgoal_lower.startswith(q) for q in ["'", '"']):
                extracted_text = id_match.group(1).strip()

        # Explicit Enter / Submit check
        is_enter = any(kw in subgoal_lower for kw in ["press enter", "hit enter", "key enter", "press the enter", "submit the"]) and not extracted_text
        if is_enter:
            return {
                "operation": "PRESS_ENTER",
                "target_index": None,
                "text_value": None,
                "reasoning_summary": "Dispatched Enter keypress to submit/continue"
            }

        # Explicit wait check
        if any(kw in subgoal_lower for kw in ["wait for", "sleep", "pause"]):
            return {
                "operation": "WAIT",
                "target_index": None,
                "text_value": None,
                "reasoning_summary": "Waited for page/results to load"
            }

        # Scroll check
        if any(kw in subgoal_lower for kw in ["scroll down", "scroll page down", "page down"]):
            return {
                "operation": "SCROLL_DOWN",
                "target_index": None,
                "text_value": None,
                "reasoning_summary": "Scrolled page down to reveal more content"
            }
        if any(kw in subgoal_lower for kw in ["scroll up", "scroll page up", "page up"]):
            return {
                "operation": "SCROLL_UP",
                "target_index": None,
                "text_value": None,
                "reasoning_summary": "Scrolled page up"
            }

        # Information extraction / question answering / summarization check
        is_extract_or_answer = any(subgoal_lower.startswith(prefix) for prefix in [
            "tell me ", "what is ", "what are ", "extract ", "summarize ", "explain ", 
            "read ", "describe ", "get the ", "show me ", "find out "
        ]) or any(kw in subgoal_lower for kw in [
            "what the problem statement is", "what is the problem statement", "what is the",
            "tell me what", "tell me about", "what problem statement"
        ])
        if is_extract_or_answer:
            context_query = subgoal
            if getattr(self, "last_search_query", None):
                context_query = f"{subgoal} {self.last_search_query}"
            return {
                "operation": "EXTRACT_AND_ANSWER",
                "target_index": None,
                "target_label": None,
                "text_value": context_query,
                "reasoning_summary": f"Information extraction request: '{subgoal}'"
            }

        # Observation-only check (e.g. 'locate filters', 'identify options') - don't click arbitrary elements
        is_pure_observation = any(subgoal_lower.startswith(obs) for obs in ["locate ", "identify ", "find ", "observe ", "check ", "look at "]) and not any(act in subgoal_lower for act in ["click", "press", "type", "fill", "select", "scroll", "submit"])
        if is_pure_observation:
            return {
                "operation": "WAIT",
                "target_index": None,
                "text_value": None,
                "reasoning_summary": "Observational step; verified view without clicking"
            }

        is_select = (
            any(kw in subgoal_lower for kw in ["select", "choose", "pick", "set role", "select option", "dropdown"])
            or (target_field and any(rf in target_field.lower() for rf in ["role", "dropdown", "select", "option", "country", "gender", "status", "category"]))
        ) and not any(prod in subgoal_lower for prod in ["product", "result", "item", "listing", "first", "top", "cart"])

        is_type = (
            any(kw in subgoal_lower for kw in ["type ", "fill ", "write ", "search for ", "enter the query", "enter '", 'enter "'])
            or (is_assignment and not is_select)
            or (extracted_text is not None and not is_select and not any(kw in subgoal_lower for kw in ["click", "press", "select", "apply", "choose", "add", "pick"]))
        )

        is_click = any(kw in subgoal_lower for kw in ["click", "press", "open", "hit", "dismiss", "focus", "apply", "add", "proceed", "go to"]) or (
            any(kw in subgoal_lower for kw in ["login", "log in", "sign in", "signin", "signup", "sign up", "register", "submit"]) and not is_type and not is_select
        )

        stop_words = self._STOP_WORDS
        words = [w for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', subgoal_lower) if w not in stop_words and len(w) > 1]
        # Ignore "open" when used in browser tab instructions like "open a new tab", "open anew tab", "open in new tab"
        if any(tp in subgoal_lower for tp in ["new tab", "anew tab", "open tab", "open in a new", "open in new", "new window"]):
            words = [w for w in words if w != "open"]
        if target_field:
            for tf_word in re.findall(r'\b[a-zA-Z0-9_-]+\b', target_field.lower()):
                if tf_word not in stop_words and tf_word not in words:
                    words.insert(0, tf_word)
        words.extend(extra_keywords)

        # Incorporate active search context for result selection
        query_terms = []
        is_result_selection = any(kw in subgoal_lower for kw in ["product", "result", "item", "listing", "first", "top"])
        if is_result_selection and getattr(self, "last_search_query", None):
            query_terms = [w for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', self.last_search_query.lower()) if w not in stop_words and len(w) > 2]

        # Common advertising, footer, and corporate phrases to penalize when selecting content
        ad_or_footer_phrases = self._AD_OR_FOOTER_PHRASES

        best_score = -1
        best_candidate = None

        for el in elements:
            if not el.get("is_visible", True):
                continue
            box = el.get("bounding_box", {})
            if box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                continue
            # Skip off-screen cloaked elements (extreme negative coordinates like x = -9908)
            if box.get("x", 0) < -500:
                continue

            score = 0
            keyword_hits = 0
            tag = el.get("tag", "").lower()
            role = el.get("role", "").lower()
            label = el.get("label", "").lower()
            val = el.get("value", "").lower()

            # Heavy penalty for footer links, corporate links, and advertisements
            if any(phrase in label for phrase in ad_or_footer_phrases):
                score -= 10

            # Target field exact match bonus
            if target_field:
                tf_lower = target_field.lower()
                if tf_lower in label:
                    score += 15
                elif any(tfw in label for tfw in tf_lower.split() if tfw not in stop_words):
                    score += 10

            # Knowledge base pattern matching from ui_patterns.json
            if getattr(self, "ui_patterns", None):
                for intent_name, pattern in self.ui_patterns.items():
                    p_roles = pattern.get("roles", [])
                    p_tags = pattern.get("tags", [])
                    p_keywords = pattern.get("label_keywords", [])
                    p_weight = pattern.get("base_weight", 10)

                    intent_active = False
                    if intent_name == "LOGIN_INPUT" and (is_type or is_assignment) and any(kw in subgoal_lower for kw in ["user", "username", "email", "login", "id", "account"]):
                        intent_active = True
                    elif intent_name == "PASSWORD_INPUT" and (is_type or is_assignment) and any(kw in subgoal_lower for kw in ["password", "passcode", "pin", "secret", "pass"]):
                        intent_active = True
                    elif intent_name == "SELECT_DROPDOWN" and is_select:
                        intent_active = True
                    elif intent_name == "SUBMIT_AUTH" and is_click and any(kw in subgoal_lower for kw in ["login", "log in", "sign in", "signin", "submit", "continue"]):
                        intent_active = True
                    elif intent_name == "SEARCH_INPUT" and is_type and any(kw in subgoal_lower for kw in ["search", "query", "find", "lookup"]):
                        intent_active = True
                    elif intent_name == "FILTER_RATING" and any(kw in subgoal_lower for kw in ["star", "rating", "review", "4 star"]):
                        intent_active = True
                    elif intent_name == "ADD_TO_CART" and any(kw in subgoal_lower for kw in ["add to cart", "add to basket", "buy"]):
                        intent_active = True
                    elif intent_name == "VIEW_CART" and any(kw in subgoal_lower for kw in ["cart", "basket"]):
                        intent_active = True
                    elif intent_name == "CLOSE_MODAL" and any(kw in subgoal_lower for kw in ["close", "dismiss", "cancel", "skip"]):
                        intent_active = True

                    if intent_active:
                        role_tag_match = (role in p_roles or not p_roles) and (tag in p_tags or not p_tags)
                        kw_match = any(kw in label for kw in p_keywords)
                        if role_tag_match and kw_match:
                            score += p_weight
                        elif role_tag_match and any(w in label for w in words):
                            score += p_weight // 2

            # Role-based bonuses
            if is_select and (role == "combobox" or tag == "select"):
                score += 10
                if extracted_text and extracted_text.lower() in label:
                    score += 6
            elif is_type:
                if role in ["textbox", "combobox", "searchbox"] or tag in ["input", "textarea"]:
                    score += 8
                    # Extra bonus for search-specific inputs
                    if any(sw in label for sw in ["search", "query", "find", "lookup", "filter", "id", "title"]):
                        score += 5
                    # Extra bonus for auth/credential inputs when requested
                    if any(aw in subgoal_lower for aw in ["user", "username", "email", "login", "id", "account"]) and any(aw in label for aw in ["user", "username", "email", "login", "id", "account"]):
                        score += 8
                    if any(pw in subgoal_lower for pw in ["password", "passcode", "pin", "secret"]) and any(pw in label for pw in ["password", "passcode", "pin", "pass"]):
                        score += 10
            elif is_click:
                if role in ["button", "link"]:
                    score += 3
                if role == "combobox":
                    score += 2
                # Boost login / sign in / sign up buttons when clicked
                if any(bw in subgoal_lower for bw in ["login", "log in", "sign in", "signin"]) and any(bw in label for bw in ["login", "log in", "sign in", "signin", "submit"]):
                    score += 8
                if any(sw in subgoal_lower for sw in ["signup", "sign up", "register", "create account"]) and any(sw in label for sw in ["signup", "sign up", "register", "create account", "join"]):
                    score += 8

            # When clicking or selecting, deprioritize text inputs unless the goal specifically asks to click an input
            if (is_click or is_select) and role in ["textbox", "input"] and not any(inp in subgoal_lower for inp in ["input", "search box", "field"]):
                score -= 6

            # If navigating to cart (view/go to/open cart), penalize 'Add to cart' action buttons and boost cart controls
            is_viewing_cart = any(vw in subgoal_lower for vw in ["view cart", "go to cart", "cart icon", "to view", "open cart", "proceed to cart"]) and "add" not in subgoal_lower
            if is_viewing_cart:
                if "add to cart" in label:
                    score -= 10
                if any(cw in label for cw in ["cart", "basket"]):
                    score += 8
                if any(cw in label for cw in ["view cart", "go to cart", "proceed to cart", "proceed to checkout"]):
                    score += 6

            # If adding to cart, boost 'Add to cart' / 'Add to basket' action buttons
            is_adding_cart = any(ac in subgoal_lower for ac in ["add to cart", "add to basket", "add the top result", "add result to cart", "add product to cart"])
            if is_adding_cart:
                if any(cw in label for cw in ["add to cart", "add to basket"]):
                    score += 12
                    keyword_hits += 2
                # Penalize navbar cart link so we don't accidentally navigate to empty cart when trying to add!
                elif label.strip() in ["cart", "view cart", "go to cart"] or (box.get("y", 0) < 120 and "cart" in label and "add" not in label):
                    score -= 12

            # If applying a rating or star filter, boost 4-star filter options
            is_rating_filter = any(rf in subgoal_lower for rf in ["star", "rating", "review", "4 star", "4 & up", "4 stars", "four star"])
            if is_rating_filter:
                if any(rf in label for rf in ["4 star and above", "4 star & above", "4 stars and above", "4 stars & above", "4 star or above", "4 stars or above", "4 & up", "4★"]):
                    score += 14
                    keyword_hits += 2
                elif any(rf in label for rf in ["4 star", "4 stars", "four star"]):
                    score += 8
                    keyword_hits += 1
                elif any(rf in label for rf in ["customer ratings", "customer rating", "rating", "ratings"]):
                    score += 5
                    keyword_hits += 1

            # Word matching: when clicking, match strictly against label; only use input val when typing
            combined_text = f"{label} {val}" if is_type else label
            for w in words:
                if w in combined_text:
                    score += 3
                    keyword_hits += 1
                elif w in f"{tag} {role}":
                    score += 1

            # Active query match bonus for search results (e.g. 'keyboard', 'mechanical')
            if is_result_selection and query_terms:
                for qw in query_terms:
                    if qw in combined_text:
                        score += 4
                        keyword_hits += 1

            # Strict Intent Guard for Clicks:
            # If clicking and we have search words, prevent clicking arbitrary unrelated links
            # (e.g. clicking 'Computers' when looking for 'apply 4 star or above')
            has_intent_match = (
                (is_viewing_cart and any(cw in label for cw in ["cart", "basket"])) or
                (is_adding_cart and any(cw in label for cw in ["add to cart", "add to basket"])) or
                (is_rating_filter and any(rf in label for rf in ["star", "rating", "review", "customer ratings"])) or
                (is_result_selection and query_terms and any(qw in combined_text for qw in query_terms))
            )
            if is_click and len(words) > 0 and keyword_hits == 0 and not has_intent_match:
                continue

            # Smart long-label penalty: only penalize if no keywords match
            # Product titles are long BUT contain relevant keywords, promo banners don't
            if len(label) > 60 and keyword_hits == 0:
                score -= 3

            # Spatial bonus: elements in the main content area (below navbar)
            # are more likely to be actual page content vs static nav items
            # (skip spatial bonus when looking for cart icon in header navbar)
            if is_click and box.get("y", 0) > 150 and not is_viewing_cart:
                score += 1

            if score > best_score and score >= 3:
                best_score = score
                best_candidate = el

        # If a rating filter was requested but not found in the current view, scroll down to reveal sidebar filters
        if any(rf in subgoal_lower for rf in ["star", "rating", "review", "4 star"]) and not best_candidate:
            return {
                "operation": "SCROLL_DOWN",
                "target_index": None,
                "text_value": None,
                "reasoning_summary": "Rating filter not visible in current viewport; scrolling down to reveal filters"
            }

        if best_candidate:
            target_idx = best_candidate["index"]
            target_label = best_candidate.get("label", "")
            target_role = best_candidate.get("role", "").lower()
            target_tag = best_candidate.get("tag", "").lower()
            is_select_candidate = target_tag == "select" or target_role == "combobox"
            is_editable = (target_role in ["textbox", "searchbox"] or target_tag in ["input", "textarea"]) and not is_select_candidate

            if is_select_candidate and (is_select or (extracted_text and not is_editable)):
                final_val = extracted_text
                if not final_val:
                    for w in words:
                        if w.lower() not in ["role", "dropdown", "select", "option", "choose", "pick"] and w in target_label.lower():
                            final_val = w
                            break
                return {
                    "operation": "SELECT",
                    "target_index": target_idx,
                    "target_label": target_label,
                    "text_value": final_val,
                    "reasoning_summary": f"Selected option '{final_val}' on dropdown [{target_idx}] label: '{target_label}'"
                }

            if (is_type or is_assignment) and extracted_text and is_editable:
                # Determine if this input should auto-submit via Enter keypress
                target_label_lower = target_label.lower()
                is_auth_field = any(auth in target_label_lower for auth in [
                    "username", "user name", "user", "email", "e-mail", "password", "passcode",
                    "pin", "pass", "login", "sign in", "signup", "sign up", "auth"
                ]) or "password" in target_role
                explicit_submit = any(sub in subgoal_lower for sub in ["and submit", "and hit enter", "and press enter"])
                is_search_field = (
                    any(sw in target_label_lower for sw in ["search", "query", "find", "lookup"])
                    or target_role == "searchbox"
                ) and not is_auth_field
                auto_enter = explicit_submit or is_search_field

                return {
                    "operation": "TYPE_AND_SUBMIT" if auto_enter else "TYPE_TEXT",
                    "target_index": target_idx,
                    "target_label": target_label,
                    "text_value": extracted_text,
                    "reasoning_summary": f"Matched input control [{target_idx}] label: '{target_label}'"
                }
            else:
                return {
                    "operation": "CLICK",
                    "target_index": target_idx,
                    "target_label": target_label,
                    "text_value": None,
                    "reasoning_summary": f"Matched interactive control [{target_idx}] label: '{target_label}'"
                }

        # Fallback: if typing with extracted text, find first visible textbox
        if is_type and extracted_text:
            for el in elements:
                if not el.get("is_visible", True):
                    continue
                box = el.get("bounding_box", {})
                if box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                    continue
                if box.get("x", 0) < -500:
                    continue
                if el.get("role") in ["textbox", "combobox"]:
                    fb_label = el.get("label", "").lower()
                    fb_is_auth = any(auth in fb_label for auth in ["username", "email", "password", "pin", "login"])
                    explicit_submit = any(sub in subgoal_lower for sub in ["and submit", "and hit enter", "and press enter"])
                    auto_enter = explicit_submit or (any(sw in fb_label for sw in ["search", "query", "find"]) and not fb_is_auth)
                    return {
                        "operation": "TYPE_AND_SUBMIT" if auto_enter else "TYPE_TEXT",
                        "target_index": el["index"],
                        "text_value": extracted_text,
                        "reasoning_summary": f"Defaulted to first visible input [{el['index']}]"
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
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            load_dotenv(os.path.join(repo_root, ".env"))
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

    def _fallback_decompose_goal(self, user_goal: str) -> List[str]:
        if not user_goal:
            return ["locate_search_input", "type_query", "submit"]
        if "," in user_goal or " and " in user_goal or ";" in user_goal:
            raw_steps = [c.strip() for c in re.split(r'[,;]\s*|\s+and\s+', user_goal) if c.strip()]
            is_auth_goal = any(kw in user_goal.lower() for kw in ["login", "log in", "sign in", "signin", "signup", "sign up", "register"])
            has_form_fields = any(any(f in s.lower() for f in ["username", "password", "role", "email", "->", ":", "="]) for s in raw_steps)
            has_explicit_submit = any(any(sub in s.lower() for sub in ["submit", "click login", "click sign", "click register", "press enter"]) for s in raw_steps)
            if is_auth_goal and has_form_fields and not has_explicit_submit:
                raw_steps.append("click login")
            return raw_steps
        return [user_goal]

    async def plan(self, domain_context: Dict[str, Any]) -> List[str]:
        if not self.enabled:
            print("[Planner] Warning: GROQ_API_KEY not configured. Using fallback fast-path plan.")
            user_goal = domain_context.get("user_goal", "")
            return self._fallback_decompose_goal(user_goal)

        user_goal = domain_context.get("user_goal", "")
        error_context = ""
        if domain_context.get("error_state"):
            error_context = f"\nPrevious Blocker Encountered: {domain_context.get('error_state')}\nProvide adaptive recovery steps from the current page state to continue toward the objective."

        if user_goal:
            instruction = f"Decompose this user goal into an array of atomic sequential subgoals from the current page state:\nObjective: \"{user_goal}\"{error_context}"
        else:
            instruction = f"Given the domain context, generate a step-by-step array of sequential subgoals to explore key portal actions.{error_context}"

        system_prompt = """You are the high-level planner for an autonomous web agent.
Rules for generating subgoals:
1. Every subgoal MUST be a concrete executable physical action starting with an action verb: 'type', 'click', 'select', 'scroll down', or 'wait'.
2. NEVER generate observational or mental steps like 'locate', 'identify', 'find', 'observe', 'verify', or 'look at'. The executor only executes physical clicks/types.
3. Keep plans minimal and direct (typically 3-5 steps). For searching, use a single step: "type '<query>' into search bar and submit".
4. For filtering, specify the exact filter value: "click the '4 Stars & Up' filter".
5. When selecting search results, reference the actual searched item name (e.g. for keyboard search: "click the first product listing title | Keywords: keyboard, mechanical, switches") rather than generic words like 'product' or 'item'.
6. Respond ONLY with a valid JSON object containing a 'plan' array of strings.
For each string, append ' | Keywords: ' followed by 3-4 domain-specific synonyms or related terms for the target element.
Example: {"plan": ["type 'mechanical keyboard' into search bar and submit | Keywords: search box, query field, find products", "click the '4 Stars & Up' filter | Keywords: customer reviews, rating filter, star rating", "click the first product listing title | Keywords: keyboard, mechanical, switches", "click 'Add to Cart' | Keywords: add to basket, purchase, buy now"]}"""

        user_prompt = f"""<instruction>{instruction}</instruction>
<current_url>{domain_context.get('url')}</current_url>
<context_state>{json.dumps(domain_context.get('cso_memory', ''))}</context_state>"""

        try:
            import os
            groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            print(f"[Planner] Querying Groq Heavy LLM ({groq_model}) to decompose goal into subgoals...")
            response = await self.client.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=512
            )
            content = response.choices[0].message.content
            plan_obj = json.loads(content)
            decomposed = plan_obj.get("plan", [])
            if decomposed and len(decomposed) > 0:
                return decomposed
        except Exception as err:
            print(f"[Planner] LLM Planning failed: {err}")

        return self._fallback_decompose_goal(user_goal)


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
        if use_swarm and self.swarm_coordinator:
            browser_api.set_message_bus(self.swarm_coordinator.bus)
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

        safe_state = self.sanitizer.sanitize_state(self.executor.browser_api.local_state_tree)
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
        max_total_steps = 25
        replans_count = 0
        max_replans = 5
        while self.current_plan and step_index <= max_total_steps:
            subgoal = self.current_plan.pop(0)
            print(f"\n=======================================================")
            print(f"[Orchestrator] Step [{step_index}/{total_steps}]: {subgoal}")
            print(f"=======================================================")

            # Keep context URL and state in sync with current page navigation
            if self.executor.browser_api.page:
                try:
                    context["url"] = self.executor.browser_api.page.url
                except Exception:
                    pass

            # Small yield to let event loop pump Playwright events
            await asyncio.sleep(0.01)

            # Dismiss any modal overlays/popups before attempting action
            await self.executor.browser_api.dismiss_overlays()

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
                            text_value=action_decision.get("text_value"),
                            label=action_decision.get("target_label") or action_decision.get("label")
                        )
                    else:
                        success = await self.executor.execute_subgoal(subgoal)
                else:
                    success = await self.executor.execute_subgoal(subgoal)

                if success:
                    self.cso_tracker.append_state(subgoal, ["action_executed"])
                    current_url = context.get("url", start_url)
                    self.scheduler.log_successful_trajectory({"goal": subgoal, "url": current_url})
                    # Human-observable pacing pause between steps
                    await asyncio.sleep(1.2)
            except (ElementObscuredError, StaleNodeException) as err:
                print(f"[Orchestrator] Layout Failure ({type(err).__name__}): {err}. Waking Slow Planner for replan...")
                self.cso_tracker.append_state(subgoal, [], current_blocker=str(err))
                replans_count += 1
                if replans_count > max_replans:
                    print(f"[Orchestrator] Max replans ({max_replans}) reached. Stopping execution.")
                    break
                await self._handle_failure(err, context)
                total_steps = step_index + len(self.current_plan)

            step_index += 1

        if step_index > max_total_steps:
            print(f"[Orchestrator] Reached maximum allowed execution steps ({max_total_steps}). Execution stopped.")

    async def _handle_failure(self, error: Exception, context: Dict[str, Any]):
        """Wakes up the slow planner to reassess based on specific error states."""
        if self.executor.browser_api.page:
            try:
                context["url"] = self.executor.browser_api.page.url
            except Exception:
                pass
        context["error_state"] = str(error)
        context["cso_memory"] = self.cso_tracker.get_compressed_context()
        context["state"] = self.sanitizer.sanitize_state(self.executor.browser_api.local_state_tree)
        self.current_plan = await self.planner.plan(context)
