# src/agents/swarm.py
"""
Local Multi-Agent Swarms for LiteSight.
Deconstructs monolithic browser agent into four specialized edge micro-agents:
1. DOMSensorAgent: Listens to MutationObserver diff stream and tracks active UI tree.
2. PrivacySentinelAgent: Enforces WebGPU sanitization and synthetic vector masking before egress.
3. SpeculativeActionAgent: Executes sub-500ms Fast-Path DOM matching.
4. VisualGroundingAgent: Executes zero-DOM OmniParser and foveation fallback.
Language: STE (Simplified Technical English).
"""

import time
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..orchestrator.bus import LocalMessageBus, Message
from ..orchestrator.exceptions import (
    StaleNodeException,
    ElementObscuredError,
    CanvasFallbackTrigger,
    PIIRedactionFailure
)
from ..vision.omni_parser import OmniVisualParser
from ..vision.foveation import FoveatedTokenizer


class DOMSensorAgent:
    """
    Monitors DOM mutations passively via asynchronous MutationObserver events.
    Maintains indexed element cache without polling.
    """
    def __init__(self, bus: LocalMessageBus):
        self.bus = bus
        self.local_state_tree: Dict[str, Any] = {}
        self.latest_snapshot: Optional[Dict[str, Any]] = None
        self.bus.subscribe("dom.mutation_batch", self.handle_mutations)
        self.bus.subscribe("dom.set_snapshot", self.handle_snapshot_update)

    async def handle_mutations(self, message: Message):
        """Processes MutationRecord array asynchronously."""
        mutations = message.payload.get("mutations", [])
        for mut in mutations:
            if mut.get("type") == "childList":
                for node in mut.get("addedNodes", []):
                    key = f"{node.get('tag', '')}_{node.get('text', '')}".lower()
                    if key.strip("_"):
                        self.local_state_tree[key] = (node.get("x", 0), node.get("y", 0))

    async def handle_snapshot_update(self, message: Message):
        """Caches latest integer-indexed DOM snapshot."""
        self.latest_snapshot = message.payload.get("snapshot")


class PrivacySentinelAgent:
    """
    Zero-trust privacy sentinel.
    Validates on-device WebGPU detection and synthetic vector masking before any data egresses.
    """
    def __init__(self, bus: LocalMessageBus):
        self.bus = bus
        self.bus.subscribe("privacy.verify_egress", self.verify_egress)

    async def verify_egress(self, message: Message):
        """
        Verifies payload contains no unmasked PII.
        Raises PIIRedactionFailure if unredacted PII is detected.
        """
        payload = message.payload
        correlation_id = payload.get("correlation_id")
        data = payload.get("data", {})

        pii_report = data.get("privacy_report", {})
        raw_boxes = pii_report.get("unmasked_boxes", [])
        if not raw_boxes and not pii_report.get("is_masked", False):
            # If boxes were detected and not masked, flag them
            raw_boxes = pii_report.get("boxes", [])

        if raw_boxes:
            error = PIIRedactionFailure(f"PrivacySentinel: Detected {len(raw_boxes)} unredacted PII regions.")
            if correlation_id:
                await self.bus.reply(correlation_id, {"status": "REJECTED", "error": str(error)})
            raise error

        masked_count = pii_report.get("detectedCount", 0)
        response = {
            "status": "APPROVED",
            "masked_count": masked_count,
            "timestamp": time.time()
        }
        if correlation_id:
            await self.bus.reply(correlation_id, response)


class SpeculativeActionAgent:
    """
    Speculatively resolves sub-500ms actions against integer-indexed DOM state.
    Conforms strictly to ARCHITECTURE.md Section 7.B.2 response schema.
    """
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

    def __init__(self, bus: LocalMessageBus):
        self.bus = bus
        self.bus.subscribe("action.resolve_fast_path", self.resolve_action)

        # Load learned UI patterns from knowledge base
        self.ui_patterns = {}
        patterns_path = Path(__file__).parent.parent / "knowledge" / "ui_patterns.json"
        if patterns_path.exists():
            try:
                with open(patterns_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.ui_patterns = data.get("intents", {})
            except (FileNotFoundError, json.JSONDecodeError):
                pass

    async def resolve_action(self, message: Message):
        """Resolves target_index and operation for a given subgoal."""
        payload = message.payload
        correlation_id = payload.get("correlation_id")
        data = payload.get("data", {})

        subgoal = data.get("subgoal", "")
        elements = data.get("elements", [])

        action_payload = self._match_element(subgoal, elements)
        if correlation_id:
            await self.bus.reply(correlation_id, action_payload)

    def _match_element(self, subgoal: str, elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Matches subgoal against elements using integer keys and ARIA labels."""
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
            return {"operation": "SCROLL_DOWN", "target_index": None, "text_value": None, "reasoning_summary": "Scrolled page down"}
        if any(kw in subgoal_lower for kw in ["scroll up", "scroll page up", "page up"]):
            return {"operation": "SCROLL_UP", "target_index": None, "text_value": None, "reasoning_summary": "Scrolled page up"}

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

        ad_or_footer_phrases = self._AD_OR_FOOTER_PHRASES

        best_score = -1
        best_candidate = None

        for el in elements:
            if not el.get("is_visible", True):
                continue
            box = el.get("bounding_box", {})
            if box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                continue
            if box.get("x", 0) < -500:
                continue

            score = 0
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

            if is_select and (role == "combobox" or tag == "select"):
                score += 10
                if extracted_text and extracted_text.lower() in label:
                    score += 6
            elif is_type and (role in ["textbox", "combobox"] or tag in ["input", "textarea"]):
                score += 8
                if any(sw in label for sw in ["search", "query", "find", "lookup"]):
                    score += 4
                if any(aw in subgoal_lower for aw in ["user", "username", "email", "login", "id", "account"]) and any(aw in label for aw in ["user", "username", "email", "login", "id", "account"]):
                    score += 8
                if any(pw in subgoal_lower for pw in ["password", "passcode", "pin", "secret"]) and any(pw in label for pw in ["password", "passcode", "pin", "pass"]):
                    score += 10
            if is_click and role in ["button", "link"]:
                score += 3
                if any(bw in subgoal_lower for bw in ["login", "log in", "sign in", "signin"]) and any(bw in label for bw in ["login", "log in", "sign in", "signin", "submit"]):
                    score += 8
                if any(sw in subgoal_lower for sw in ["signup", "sign up", "register", "create account"]) and any(sw in label for sw in ["signup", "sign up", "register", "create account", "join"]):
                    score += 8
            if is_click and role == "combobox":
                score += 2

            # When clicking or selecting, deprioritize text inputs unless the goal specifically asks to click an input
            if (is_click or is_select) and role in ["textbox", "input"] and not any(inp in subgoal_lower for inp in ["input", "search box", "field"]):
                score -= 6

            # If navigating to cart (view/go to/open cart), penalize 'Add to cart' action buttons
            is_viewing_cart = any(vw in subgoal_lower for vw in ["view cart", "go to cart", "cart icon", "to view", "open cart", "proceed to cart"]) and "add" not in subgoal_lower
            if is_viewing_cart and "add to cart" in label:
                score -= 8

            # Word matching: when clicking, match strictly against label; only use input val when typing
            combined_text = f"{label} {val}" if is_type else label
            keyword_hits = 0
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
                    "text_value": final_val,
                    "target_label": target_label,
                    "reasoning_summary": f"SpeculativeActionAgent selected '{final_val}' on [{target_idx}] '{target_label}'"
                }

            if (is_type or is_assignment) and extracted_text and is_editable:
                target_label_lower = target_label.lower()
                is_auth_field = any(auth in target_label_lower for auth in [
                    "username", "user name", "user", "email", "e-mail", "password", "passcode",
                    "pin", "pass", "login", "sign in", "signup", "sign up", "auth"
                ])
                explicit_submit = any(sub in subgoal_lower for sub in ["and submit", "and hit enter", "and press enter"])
                is_search_field = any(sw in target_label_lower for sw in ["search", "query", "find", "lookup"]) and not is_auth_field
                auto_enter = explicit_submit or is_search_field
                return {
                    "operation": "TYPE_AND_SUBMIT" if auto_enter else "TYPE_TEXT",
                    "target_index": target_idx,
                    "text_value": extracted_text,
                    "target_label": target_label,
                    "reasoning_summary": f"SpeculativeActionAgent matched [{target_idx}] '{target_label}'"
                }
            else:
                return {
                    "operation": "CLICK",
                    "target_index": target_idx,
                    "text_value": None,
                    "target_label": target_label,
                    "reasoning_summary": f"SpeculativeActionAgent matched [{target_idx}] '{target_label}'"
                }

        return None


class VisualGroundingAgent:
    """
    Executes pure visual inference when DOM is unavailable (OmniParser Zero-DOM).
    Downsamples with mathematical foveation to avoid raw 1080p frame egress.
    """
    def __init__(self, bus: LocalMessageBus):
        self.bus = bus
        self.omni_parser = OmniVisualParser()
        self.foveator = FoveatedTokenizer()
        self.bus.subscribe("action.resolve_visual", self.resolve_visual)

    async def resolve_visual(self, message: Message):
        """Resolves screen coordinates directly from visual pixel buffers."""
        payload = message.payload
        correlation_id = payload.get("correlation_id")
        data = payload.get("data", {})

        frame = data.get("frame")
        pii_boxes = data.get("pii_boxes", [])

        # Extract visual interactables
        candidates = self.omni_parser.parse_interactables(frame, pii_boxes=pii_boxes)

        if not candidates:
            res = {"status": "NO_ELEMENTS", "target_coord": (960, 540)}
        else:
            primary = candidates[0]
            # Compress around primary candidate using mathematical foveation
            foveated_tokens = self.foveator.compress(frame, primary["center_coord"])
            res = {
                "status": "SUCCESS",
                "target_coord": primary["center_coord"],
                "visual_index": primary["visual_index"],
                "label": primary["label"],
                "foveated_tokens_count": len(foveated_tokens)
            }

        if correlation_id:
            await self.bus.reply(correlation_id, res)


class SwarmCoordinator:
    """
    Coordinates local edge micro-agents over the in-memory message bus.
    Replaces the monolithic execution bottleneck with decentralized micro-services.
    """
    def __init__(self, bus: Optional[LocalMessageBus] = None):
        self.bus = bus or LocalMessageBus()
        self.sensor_agent = DOMSensorAgent(self.bus)
        self.privacy_agent = PrivacySentinelAgent(self.bus)
        self.action_agent = SpeculativeActionAgent(self.bus)
        self.visual_agent = VisualGroundingAgent(self.bus)

    async def dispatch_step(
        self,
        subgoal: str,
        dom_snapshot: Dict[str, Any],
        privacy_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes a single workflow step across the swarm:
        1. PrivacySentinelAgent checks egress safety.
        2. SpeculativeActionAgent selects fast-path DOM element.
        """
        # Step 1: Enforce privacy verification
        privacy_check = await self.bus.request(
            "privacy.verify_egress",
            {"privacy_report": privacy_report},
            sender="SwarmCoordinator"
        )
        if privacy_check.get("status") != "APPROVED":
            raise PIIRedactionFailure("SwarmCoordinator: Privacy Sentinel rejected step.")

        # Step 2: Resolve action through Speculative Action Agent
        elements = dom_snapshot.get("elements", [])
        action_decision = await self.bus.request(
            "action.resolve_fast_path",
            {"subgoal": subgoal, "elements": elements},
            sender="SwarmCoordinator"
        )
        return action_decision

    async def dispatch_visual_fallback(
        self,
        frame: Any,
        pii_boxes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Dispatches zero-DOM fallback request to VisualGroundingAgent."""
        return await self.bus.request(
            "action.resolve_visual",
            {"frame": frame, "pii_boxes": pii_boxes},
            sender="SwarmCoordinator"
        )
