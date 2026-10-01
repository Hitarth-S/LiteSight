"""
LiteSight JEV Element Table & DOM Summarizer
Inspired by browser-use/jev-ultrafast: dynamic indexed action space and typed element table.
"""

from typing import List, Dict, Any, Tuple, Optional
import re


class JevElementTable:
    """
    Summarizes and formats raw extracted DOM elements into a structured,
    compact indexed table for fast heuristic matching or SLM/LLM typed decisions.
    """

    @staticmethod
    def classify_element(el: Dict[str, Any]) -> str:
        """
        Classifies an element into one of three strict physical action heads:
        - 'input': Editable text input or textarea
        - 'select': Native or custom dropdown selector
        - 'clickable': Actionable click target (button, link, checkbox, radio, tab)
        - 'other': Informational or non-interactive
        """
        tag = (el.get("tag") or "").lower()
        role = (el.get("role") or "").lower()
        input_type = (el.get("type") or "").lower()

        if tag == "select" or role in ["combobox", "listbox"]:
            # Distinguish combobox that is actually an editable input
            if tag in ["input", "textarea"] and input_type not in ["button", "submit", "checkbox", "radio"]:
                return "input"
            return "select"

        if tag in ["input", "textarea"] or role in ["textbox", "searchbox"]:
            if input_type in ["submit", "button", "reset", "image"]:
                return "clickable"
            if input_type in ["checkbox", "radio"]:
                return "clickable"
            if input_type == "hidden":
                return "other"
            return "input"

        if tag in ["a", "button", "summary"] or role in ["button", "link", "checkbox", "radio", "tab", "menuitem", "option"]:
            return "clickable"

        if el.get("onclick"):
            return "clickable"

        return "clickable" if el.get("label") else "other"

    @classmethod
    def filter_and_summarize(
        cls,
        elements: List[Dict[str, Any]],
        viewport_only: bool = False,
        max_elements: int = 60
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        """
        Prunes DOM noise, removes empty duplicates, and partitions elements into typed sets.
        Returns:
            pruned_elements: List of active candidates with category tag
            partitions: Dict mapping 'input', 'select', 'clickable' to element lists
        """
        partitions: Dict[str, List[Dict[str, Any]]] = {
            "input": [],
            "select": [],
            "clickable": [],
            "other": []
        }

        pruned: List[Dict[str, Any]] = []
        seen_signatures = set()

        for el in elements:
            if not el.get("is_visible", True):
                continue

            box = el.get("bounding_box", {})
            if box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                continue

            if box.get("x", 0) < -500:
                continue

            if viewport_only and el.get("in_viewport") is False:
                continue

            category = cls.classify_element(el)
            if category == "other":
                continue

            label = (el.get("label") or "").strip()
            val = (el.get("value") or "").strip()
            tag = (el.get("tag") or "").lower()
            role = (el.get("role") or "").lower()

            if not label and not val and tag != "input":
                continue

            # Deduplication key to prevent repeated identical footer links
            sig = (category, tag, role, label[:40], round(box.get("x", 0) / 50), round(box.get("y", 0) / 50))
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)

            el_copy = dict(el)
            el_copy["category"] = category
            pruned.append(el_copy)
            partitions[category].append(el_copy)

            if len(pruned) >= max_elements:
                break

        return pruned, partitions

    @classmethod
    def format_element_table_text(cls, elements: List[Dict[str, Any]]) -> str:
        """
        Formats elements into a human-readable and LLM-friendly indexed table,
        identical in structure to JEV's dynamic indexed action space.
        Example:
            [1] input     Search Amazon.in · empty
            [2] select    Department · All Departments
            [3] clickable Cart · 0 items
        """
        lines = []
        for el in elements:
            idx = el.get("index", el.get("id", "?"))
            cat = el.get("category") or cls.classify_element(el)
            label = (el.get("label") or "").replace("\n", " ").strip()
            if len(label) > 70:
                label = label[:67] + "..."
            val = (el.get("value") or "").replace("\n", " ").strip()
            val_str = f" · {val}" if val and val != "[REDACTED_PII]" else ""
            lines.append(f"[{idx:>3}] {cat:<9} {label}{val_str}")

        return "\n".join(lines)
