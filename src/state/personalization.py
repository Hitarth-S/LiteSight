# src/state/personalization.py
import json
import os
from urllib.parse import urlparse

class RetrievalAugmentedPersonalization:
    """
    Implements RAP from SIH research.
    Maintains a local lightweight database (JSON for now, FAISS/Chroma in future)
    to store user preferences and browser habits without cloud reliance.
    """
    def __init__(self, db_path="local_prefs.json"):
        self.db_path = db_path
        self.preferences = self._load_db()
        
    def _load_db(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return []
        # Seed with some dummy personalizations
        return [
            {"domain": "github.com", "preference": "Always prefer Dark Mode."},
            {"domain": "any", "preference": "Automatically accept essential cookies only."}
        ]
        
    def retrieve_preferences(self, current_url: str) -> list:
        """Retrieves preferences relevant to the current context."""
        relevant = []
        try:
            current_domain = urlparse(current_url).netloc.lower()
        except (ValueError, AttributeError):
            current_domain = ""
        for pref in self.preferences:
            if pref["domain"] == "any" or current_domain.endswith(pref["domain"].lower()):
                relevant.append(pref["preference"])
        return relevant
        
    def learn_preference(self, domain: str, preference: str):
        """Called by the Nightly LoRA scheduler to add new verified preferences."""
        if not any(p.get("domain") == domain and p.get("preference") == preference for p in self.preferences):
            self.preferences.append({"domain": domain, "preference": preference})
            try:
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(self.preferences, f, indent=2)
            except OSError:
                pass
