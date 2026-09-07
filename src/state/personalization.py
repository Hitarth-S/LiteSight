# src/state/personalization.py
import json
import os

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
            except Exception:
                return []
        # Seed with some dummy personalizations
        return [
            {"domain": "github.com", "preference": "Always prefer Dark Mode."},
            {"domain": "any", "preference": "Automatically accept essential cookies only."}
        ]
        
    def retrieve_preferences(self, current_url: str) -> list:
        """Retrieves preferences relevant to the current context."""
        relevant = []
        for pref in self.preferences:
            if pref["domain"] == "any" or pref["domain"] in current_url:
                relevant.append(pref["preference"])
        return relevant
        
    def learn_preference(self, domain: str, preference: str):
        """Called by the Nightly LoRA scheduler to add new verified preferences."""
        self.preferences.append({"domain": domain, "preference": preference})
        with open(self.db_path, "w") as f:
            json.dump(self.preferences, f)
