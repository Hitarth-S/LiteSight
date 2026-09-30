# src/state/sanitizer.py
import re
from typing import Dict, Tuple, Any, Optional, Set, Union


class StateSanitizer:
    """
    Privacy Layer: Scrubs PII (Personally Identifiable Information) from DOM text 
    before sending state to the cloud-based Slow Planner.
    Supports configurable sensitivity levels ('relaxed', 'balanced', 'strict')
    and category-specific filters (credit cards, passwords, emails, names, phone numbers, government IDs).
    """

    ALL_CATEGORIES = {
        "credit_cards",
        "passwords",
        "emails",
        "names",
        "phone_numbers",
        "government_ids"
    }

    def __init__(self, sensitivity: str = "balanced", categories: Optional[Dict[str, bool]] = None):
        self.sensitivity = sensitivity.lower() if sensitivity in ["relaxed", "balanced", "strict"] else "balanced"
        self.categories: Dict[str, bool] = {cat: True for cat in self.ALL_CATEGORIES}
        if categories:
            self.categories.update(categories)
        self._compile_patterns()

    def _compile_patterns(self):
        """Compiles active regex patterns based on sensitivity and enabled categories."""
        self.patterns = {}

        # 1. Credit Cards & Financials
        if self.categories.get("credit_cards", True):
            self.patterns["credit_card"] = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

        # 2. Passwords, Tokens & Auth Secrets
        if self.categories.get("passwords", True):
            self.patterns["password"] = re.compile(
                r"(?i)(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)"
            )

        # 3. Email Addresses
        if self.categories.get("emails", True) and (self.sensitivity != "relaxed" or self.categories.get("emails")):
            self.patterns["email"] = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")

        # 4. Phone Numbers
        if self.categories.get("phone_numbers", True) and (self.sensitivity != "relaxed" or self.categories.get("phone_numbers")):
            self.patterns["phone"] = re.compile(r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

        # 5. Government IDs / SSN
        if self.categories.get("government_ids", True) and (self.sensitivity != "relaxed" or self.categories.get("government_ids")):
            self.patterns["government_id"] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

        # 6. Personal Names
        if self.categories.get("names", True) and self.sensitivity in ["balanced", "strict"]:
            if self.sensitivity == "strict":
                # Stricter name matching: capitalized doublets/triplets in prose
                self.patterns["name"] = re.compile(
                    r"(?i)\b(?:name|customer|user|cardholder|account holder)\s*[:=]\s*([A-Za-z]+(?:\s+[A-Za-z]+)+)|\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"
                )
            else:
                # Balanced: explicit labeled name fields
                self.patterns["name"] = re.compile(
                    r"(?i)\b(?:name|customer|user|cardholder|account holder)\s*[:=]\s*([A-Za-z]+(?:\s+[A-Za-z]+)+)"
                )

        # 7. Strict mode high-entropy / long numeric IDs
        if self.sensitivity == "strict":
            self.patterns["long_numeric"] = re.compile(r"\b\d{6,}\b")

    def set_config(self, sensitivity: Optional[str] = None, categories: Optional[Dict[str, bool]] = None):
        """Updates sensitivity level and/or category toggles."""
        if sensitivity and sensitivity.lower() in ["relaxed", "balanced", "strict"]:
            self.sensitivity = sensitivity.lower()
        if categories and isinstance(categories, dict):
            for k, v in categories.items():
                if k in self.ALL_CATEGORIES:
                    self.categories[k] = bool(v)
        self._compile_patterns()

    def get_config(self) -> Dict[str, Any]:
        """Returns the current sensitivity and category settings."""
        return {
            "sensitivity": self.sensitivity,
            "categories": dict(self.categories),
            "active_patterns": list(self.patterns.keys())
        }

    def sanitize_state(self, state_tree: Dict[str, Union[Tuple[int, int], str]]) -> Dict[str, Union[Tuple[int, int], str]]:
        """Takes the raw local_state_tree and returns a safely redacted copy."""
        sanitized_tree = {}
        for key, value in state_tree.items():
            safe_key = key
            for pii_type, pattern in self.patterns.items():
                safe_key = pattern.sub(f"[REDACTED_{pii_type.upper()}]", safe_key)

            if isinstance(value, str):
                safe_value = value
                for pii_type, pattern in self.patterns.items():
                    safe_value = pattern.sub(f"[REDACTED_{pii_type.upper()}]", safe_value)
                sanitized_tree[safe_key] = safe_value
            else:
                sanitized_tree[safe_key] = value

        return sanitized_tree

    def sanitize_text(self, text: str) -> str:
        """Sanitizes a single text string by scrubbing all active PII patterns."""
        if not text or not isinstance(text, str):
            return text
        safe_text = text
        for pii_type, pattern in self.patterns.items():
            safe_text = pattern.sub(f"[REDACTED_{pii_type.upper()}]", safe_text)
        return safe_text
