# src/state/sanitizer.py
import re
from typing import Dict, Tuple, Any, Optional, Set, Union



_V_D = [
    [0,1,2,3,4,5,6,7,8,9],
    [1,2,3,4,0,6,7,8,9,5],
    [2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],
    [4,0,1,2,3,9,5,6,7,8],
    [5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],
    [7,6,5,9,8,2,1,0,4,3],
    [8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0]
]

_V_P = [
    [0,1,2,3,4,5,6,7,8,9],
    [1,5,7,6,2,8,3,0,9,4],
    [5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],
    [9,4,5,3,1,2,6,8,7,0],
    [4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],
    [7,0,4,6,9,1,3,2,5,8]
]


def verhoeff_valid(num_str: str) -> bool:
    """
    Validates 12-digit Indian Aadhaar number using the mathematical
    Verhoeff Dihedral Group (D5) check-digit algorithm.
    """
    clean = re.sub(r"[\s-]", "", num_str)
    if not clean.isdigit() or len(clean) != 12:
        return False
    digits = [int(d) for d in reversed(clean)]
    c = 0
    for i, d in enumerate(digits):
        c = _V_D[c][_V_P[i % 8][d]]
    return c == 0


class StateSanitizer:
    """
    Privacy Layer: Scrubs PII (Personally Identifiable Information) from DOM text 
    before sending state to the cloud-based Slow Planner.
    Supports configurable sensitivity levels ('relaxed', 'balanced', 'strict')
    and category-specific filters (credit cards, passwords, emails, names, phone numbers, government IDs).
    Includes mathematical Verhoeff check-digit validation for Indian Aadhaar and PAN patterns.
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

        # 4. Phone Numbers (US standard & Indian +91 formats)
        if self.categories.get("phone_numbers", True) and (self.sensitivity != "relaxed" or self.categories.get("phone_numbers")):
            self.patterns["phone_in"] = re.compile(r"\+91[\s-]?\d{5}[\s-]?\d{5}\b")
            self.patterns["phone"] = re.compile(r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

        # 5. Government IDs (US SSN, Indian PAN, and Aadhaar)
        if self.categories.get("government_ids", True) and (self.sensitivity != "relaxed" or self.categories.get("government_ids")):
            self.patterns["government_id"] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
            self.patterns["pan"] = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
            self.patterns["aadhaar"] = re.compile(r"\b(\d{4}[\s-]\d{4}[\s-]\d{4}|\d{12})\b")

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

    def _apply_pattern(self, text: str, pii_type: str, pattern: re.Pattern) -> str:
        if pii_type == "aadhaar":
            def _sub_aadhaar(match):
                val = match.group(0)
                if verhoeff_valid(val):
                    return "[REDACTED_AADHAAR]"
                return val
            return pattern.sub(_sub_aadhaar, text)
        elif pii_type == "phone_in":
            return pattern.sub("[REDACTED_PHONE]", text)
        else:
            return pattern.sub(f"[REDACTED_{pii_type.upper()}]", text)

    def sanitize_state(self, state_tree: Dict[str, Union[Tuple[int, int], str]]) -> Dict[str, Union[Tuple[int, int], str]]:
        """Takes the raw local_state_tree and returns a safely redacted copy."""
        sanitized_tree = {}
        for key, value in state_tree.items():
            safe_key = key
            for pii_type, pattern in self.patterns.items():
                safe_key = self._apply_pattern(safe_key, pii_type, pattern)

            if isinstance(value, str):
                safe_value = value
                for pii_type, pattern in self.patterns.items():
                    safe_value = self._apply_pattern(safe_value, pii_type, pattern)
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
            safe_text = self._apply_pattern(safe_text, pii_type, pattern)
        return safe_text
