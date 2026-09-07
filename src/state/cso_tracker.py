# src/state/cso_tracker.py
import json

class CSOTracker:
    """
    Implements Context State Objects (CSO) from SIH research.
    Instead of maintaining a massive log of all raw HTML/DOM changes and conversations,
    this distills the history into a dense, append-only Key-Value checklist.
    This prevents O(n) KV cache explosion in the LLM.
    """
    def __init__(self):
        self.cso_log = []
        
    def append_state(self, user_goal: str, completed_steps: list, current_blocker: str = None):
        """Appends a highly compressed state representation."""
        entry = {
            "user_goal": user_goal,
            "completed_steps": completed_steps
        }
        if current_blocker:
            entry["blocker"] = current_blocker
            
        self.cso_log.append(entry)
        
    def get_compressed_context(self) -> str:
        """Returns the compressed Context State Object as a string."""
        if not self.cso_log:
            return "CSO: [Start of Interaction]"
            
        # Only return the most recent state and a highly compressed history
        latest = self.cso_log[-1]
        history_summary = f"Completed {sum(len(e['completed_steps']) for e in self.cso_log)} previous steps."
        
        return f"CSO: {history_summary} | Current Goal: {latest['user_goal']} | Blocker: {latest.get('blocker', 'None')}"
