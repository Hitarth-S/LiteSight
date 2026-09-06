# src/state/sanitizer.py
import re
from typing import Dict, Tuple

class StateSanitizer:
    """
    Privacy Layer: Scrubs PII (Personally Identifiable Information) from DOM text 
    before sending state to the cloud-based Slow Planner.
    """
    def __init__(self):
        # Basic regex patterns for common PII
        self.patterns = {
            "email": re.compile(r"[\w\.-]+@[\w\.-]+\.\w+"),
            "phone": re.compile(r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
            # Matches potential passwords or long alpha-numeric hashes if needed
            "long_numeric": re.compile(r"\b\d{6,}\b") 
        }

    def sanitize_state(self, state_tree: Dict[str, Tuple[int, int]]) -> Dict[str, Tuple[int, int]]:
        """
        Takes the raw local_state_tree and returns a safely redacted copy.
        """
        sanitized_tree = {}
        for key, coords in state_tree.items():
            safe_key = key
            # Scrub against all known PII patterns
            for pii_type, pattern in self.patterns.items():
                safe_key = pattern.sub(f"[REDACTED_{pii_type.upper()}]", safe_key)
            
            sanitized_tree[safe_key] = coords
            
        return sanitized_tree
