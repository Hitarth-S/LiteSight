"""
LiteSight JEV Typed Policy Engine
Inspired by browser-use/jev-ultrafast:
- Dynamic indexed action space
- Strictly partitioned candidate heads (inputs, selects, clickables)
- Eliminates cross-type mismatch bugs (e.g. typing into a department dropdown)
- Fast local SLM inference (Ollama / Groq / ONNX) with deterministic typed fallback
"""

import re
import os
import json
import time
from typing import List, Dict, Any, Optional
from .element_table import JevElementTable


class JevTypedPolicy:
    """
    Decides the next browser action using strict typed candidate partitioning
    and dynamic indexed element matching.
    """

    STOP_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "over", "after",
        "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "can", "could", "shall", "should", "will",
        "would", "may", "might", "must", "then", "also", "just", "now", "so",
        "than", "that", "this", "these", "those", "it", "its", "as"
    }

    def __init__(self, slm_client: Optional[Any] = None, slm_model: Optional[str] = None):
        self.slm_client = slm_client
        self.slm_model = slm_model or os.environ.get("LITESIGHT_SLM_MODEL", "llama-3.3-70b-versatile")
        self.last_search_query = None

    def decide_action(
        self,
        subgoal: str,
        elements: List[Dict[str, Any]],
        use_slm: bool = False
    ) -> Dict[str, Any]:
        """
        Main entry point for action planning.
        Evaluates the subgoal and partitioned element table.
        """
        pruned_elements, partitions = JevElementTable.filter_and_summarize(elements)

        # 1. Check for pure observation / wait / scroll / extract commands
        subgoal_lower = subgoal.lower().strip()

        if any(kw in subgoal_lower for kw in ["scroll down", "scroll page down", "page down"]):
            return {
                "operation": "SCROLL_DOWN",
                "target_index": None,
                "target_label": None,
                "text_value": None,
                "reasoning_summary": "Scrolled page down to reveal more content"
            }

        if any(kw in subgoal_lower for kw in ["scroll up", "scroll page up", "page up"]):
            return {
                "operation": "SCROLL_UP",
                "target_index": None,
                "target_label": None,
                "text_value": None,
                "reasoning_summary": "Scrolled page up"
            }

        if any(kw in subgoal_lower for kw in ["wait for", "sleep", "pause"]):
            return {
                "operation": "WAIT",
                "target_index": None,
                "target_label": None,
                "text_value": None,
                "reasoning_summary": "Waited for page or network to settle"
            }

        # 2. Extract text value if this is a typing or search intent
        extracted_text = self._extract_text_value(subgoal)

        # 3. Detect primary intent category
        is_type = (
            any(kw in subgoal_lower for kw in ["search for", "type ", "fill ", "enter ", "input "])
            or (extracted_text is not None and not any(kw in subgoal_lower for kw in ["click", "select", "choose", "pick", "filter"]))
        )

        is_select = (
            any(kw in subgoal_lower for kw in ["select", "choose", "pick", "dropdown", "set role"])
            and not any(prod in subgoal_lower for prod in ["product", "result", "item", "listing", "first", "top", "cart"])
        )

        # 4. Strict Typed Head Routing
        if is_type:
            return self._resolve_type_head(subgoal, extracted_text, partitions["input"], elements)

        if is_select:
            return self._resolve_select_head(subgoal, extracted_text, partitions["select"], elements)

        # Default to Clickable Head
        return self._resolve_click_head(subgoal, partitions["clickable"], elements)

    def _extract_text_value(self, subgoal: str) -> Optional[str]:
        """Extracts target string literal from user goal (e.g. search for 'mechanical keyboard')."""
        match = re.search(r"['\"]([^'\"]+)['\"]", subgoal)
        if match:
            return match.group(1).strip()

        subgoal_lower = subgoal.lower().strip()
        if "search for " in subgoal_lower:
            cand = subgoal_lower.split("search for ", 1)[1].strip()
            cand = re.split(r'\s+and\s+|\s+then\s+|[,;]', cand)[0].strip().strip("'\"")
            if cand:
                return cand

        match_kw = re.search(r'(?:type|fill|enter)\s+([a-zA-Z0-9_@.+ -]+?)\s+(?:into|in|for)\s+', subgoal, re.IGNORECASE)
        if match_kw:
            return match_kw.group(1).strip()

        return None

    def _resolve_type_head(
        self,
        subgoal: str,
        text_value: Optional[str],
        input_candidates: List[Dict[str, Any]],
        all_elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Strict typing head: ONLY evaluates genuine text inputs.
        Dropdowns (<select>), buttons, and links are physically excluded.
        """
        if not text_value:
            text_value = self._extract_text_value(subgoal) or "search"

        self.last_search_query = text_value
        subgoal_lower = subgoal.lower()

        # If no input candidates found in pruned table, scan full DOM for any text input
        candidates = input_candidates
        if not candidates:
            candidates = [el for el in all_elements if JevElementTable.classify_element(el) == "input"]

        if not candidates:
            return {
                "operation": "WAIT",
                "target_index": None,
                "target_label": None,
                "text_value": text_value,
                "reasoning_summary": f"No text input field available to enter '{text_value}'"
            }

        # Score candidate inputs
        best_cand = None
        best_score = -100

        is_search_intent = any(sw in subgoal_lower for sw in ["search", "query", "find", "lookup"])

        for el in candidates:
            score = 0
            label = (el.get("label") or "").lower()
            role = (el.get("role") or "").lower()
            tag = (el.get("tag") or "").lower()

            if is_search_intent:
                if role == "searchbox" or "search" in label or "query" in label or "find" in label:
                    score += 20
                if any(kw in label for kw in ["search amazon", "search google", "search store", "search bar", "nav-search"]):
                    score += 25
            else:
                # Authentication / general field matching
                for word in subgoal_lower.split():
                    if word not in self.STOP_WORDS and word in label:
                        score += 8

            # Spatial boost: Top navbar inputs are primary search bars
            box = el.get("bounding_box", {})
            if box.get("y", 0) < 180 and is_search_intent:
                score += 10

            if score > best_score:
                best_score = score
                best_cand = el

        target_idx = best_cand.get("index", best_cand.get("id"))
        target_label = best_cand.get("label", "")

        is_search_subgoal = is_search_intent or best_cand.get("role") == "searchbox" or "search" in target_label.lower()
        operation = "TYPE_AND_SUBMIT" if is_search_subgoal else "TYPE_TEXT"

        return {
            "operation": operation,
            "target_index": target_idx,
            "target_label": target_label,
            "text_value": text_value,
            "reasoning_summary": f"Matched input control [{target_idx}] label: '{target_label}'"
        }

    def _resolve_select_head(
        self,
        subgoal: str,
        value: Optional[str],
        select_candidates: List[Dict[str, Any]],
        all_elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Strict selection head: ONLY evaluates dropdown and select widgets.
        """
        candidates = select_candidates
        if not candidates:
            candidates = [el for el in all_elements if JevElementTable.classify_element(el) == "select"]

        if not candidates:
            return {
                "operation": "WAIT",
                "target_index": None,
                "target_label": None,
                "text_value": value,
                "reasoning_summary": "No select dropdown elements found"
            }

        subgoal_lower = subgoal.lower()
        words = [w for w in subgoal_lower.split() if w not in self.STOP_WORDS and w not in ["select", "choose", "pick", "dropdown"]]

        best_cand = candidates[0]
        best_score = -1

        for el in candidates:
            score = 0
            label = (el.get("label") or "").lower()
            for w in words:
                if w in label:
                    score += 5
            if score > best_score:
                best_score = score
                best_cand = el

        target_idx = best_cand.get("index", best_cand.get("id"))
        target_label = best_cand.get("label", "")

        return {
            "operation": "SELECT",
            "target_index": target_idx,
            "target_label": target_label,
            "text_value": value or "",
            "reasoning_summary": f"Selected option on dropdown [{target_idx}] label: '{target_label}'"
        }

    def _resolve_click_head(
        self,
        subgoal: str,
        clickable_candidates: List[Dict[str, Any]],
        all_elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Strict clickable head: Evaluates buttons, links, filter checkboxes, and product cards.
        """
        subgoal_lower = subgoal.lower()
        words = [w for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', subgoal_lower) if w not in self.STOP_WORDS and len(w) > 1]

        candidates = clickable_candidates
        if not candidates:
            candidates = [el for el in all_elements if JevElementTable.classify_element(el) == "clickable"]

        # 1. Rating filter handler
        is_rating_filter = any(rf in subgoal_lower for rf in ["star", "rating", "review", "4 star", "4 & up", "4 stars"])
        if is_rating_filter:
            for el in candidates:
                label = (el.get("label") or "").lower()
                if any(rf in label for rf in ["4 star and above", "4 star & above", "4 stars and above", "4 stars & above", "4 star or above", "4 & up", "4★"]):
                    idx = el.get("index", el.get("id"))
                    return {
                        "operation": "CLICK",
                        "target_index": idx,
                        "target_label": el.get("label"),
                        "text_value": None,
                        "reasoning_summary": f"Matched 4-star filter [{idx}] '{el.get('label')}'"
                    }
                if "4 star" in label or "4 stars" in label:
                    idx = el.get("index", el.get("id"))
                    return {
                        "operation": "CLICK",
                        "target_index": idx,
                        "target_label": el.get("label"),
                        "text_value": None,
                        "reasoning_summary": f"Matched rating filter [{idx}] '{el.get('label')}'"
                    }

            # If rating filter not found in current candidates, scroll down to reveal it
            return {
                "operation": "SCROLL_DOWN",
                "target_index": None,
                "target_label": None,
                "text_value": None,
                "reasoning_summary": "Rating filter not visible in current viewport; scrolling down to reveal filters"
            }

        # 2. Add to cart handler
        is_adding_cart = any(ac in subgoal_lower for ac in ["add to cart", "add to basket", "add the top result", "add result to cart", "add product to cart"])
        if is_adding_cart:
            for el in candidates:
                label = (el.get("label") or "").lower()
                box = el.get("bounding_box", {})
                if any(cw in label for cw in ["add to cart", "add to basket"]):
                    idx = el.get("index", el.get("id"))
                    return {
                        "operation": "CLICK",
                        "target_index": idx,
                        "target_label": el.get("label"),
                        "text_value": None,
                        "reasoning_summary": f"Matched Add to Cart button [{idx}] '{el.get('label')}'"
                    }

        # 3. View / Proceed to Cart handler
        is_viewing_cart = any(vw in subgoal_lower for vw in ["view cart", "go to cart", "cart icon", "to view", "open cart", "proceed to cart"]) and "add" not in subgoal_lower
        if is_viewing_cart:
            for el in candidates:
                label = (el.get("label") or "").lower()
                if "add to cart" in label:
                    continue
                if any(cw in label for cw in ["view cart", "proceed to cart", "go to cart", "proceed to checkout", "items in cart", "cart"]):
                    idx = el.get("index", el.get("id"))
                    return {
                        "operation": "CLICK",
                        "target_index": idx,
                        "target_label": el.get("label"),
                        "text_value": None,
                        "reasoning_summary": f"Matched Cart navigation [{idx}] '{el.get('label')}'"
                    }

        # 4. General word scoring across clickable candidates
        best_cand = None
        best_score = -1

        for el in candidates:
            score = 0
            label = (el.get("label") or "").lower()
            box = el.get("bounding_box", {})

            for w in words:
                if w in label:
                    score += 4

            if self.last_search_query:
                for qw in self.last_search_query.lower().split():
                    if qw not in self.STOP_WORDS and qw in label:
                        score += 5

            # Spatial bonus: elements below header navbar
            if box.get("y", 0) > 150:
                score += 1

            if score > best_score and score >= 3:
                best_score = score
                best_cand = el

        if best_cand:
            idx = best_cand.get("index", best_cand.get("id"))
            return {
                "operation": "CLICK",
                "target_index": idx,
                "target_label": best_cand.get("label"),
                "text_value": None,
                "reasoning_summary": f"Matched interactive control [{idx}] label: '{best_cand.get('label')}'"
            }

        # Fallback wait
        return {
            "operation": "WAIT",
            "target_index": None,
            "target_label": None,
            "text_value": None,
            "reasoning_summary": "No matching clickable element found in current viewport"
        }
