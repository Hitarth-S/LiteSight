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
    def __init__(self, bus: LocalMessageBus):
        self.bus = bus
        self.bus.subscribe("action.resolve_fast_path", self.resolve_action)

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

        subgoal_lower = subgoal.lower()
        extracted_text = None
        match = re.search(r"'([^']+)'", subgoal)
        if match:
            extracted_text = match.group(1)

        is_type = any(kw in subgoal_lower for kw in ["type", "enter", "fill", "input", "write", "search for"])
        is_click = any(kw in subgoal_lower for kw in ["click", "press", "locate", "select", "open", "hit", "dismiss"])

        stop_words = {"the", "a", "an", "into", "and", "or", "in", "to", "for", "with", "main", "bar"}
        words = [w for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', subgoal_lower) if w not in stop_words]

        best_score = -1
        best_candidate = None

        for el in elements:
            if not el.get("is_visible"):
                continue

            score = 0
            tag = el.get("tag", "").lower()
            role = el.get("role", "").lower()
            label = el.get("label", "").lower()
            val = el.get("value", "").lower()
            combined_text = f"{tag} {role} {label} {val}"

            if is_type and role in ["textbox", "combobox", "input"]:
                score += 3
            if is_click and role in ["button", "link", "combobox"]:
                score += 2

            for w in words:
                if w in combined_text:
                    score += 2

            if score > best_score and score >= 2:
                best_score = score
                best_candidate = el

        if best_candidate:
            target_idx = best_candidate["index"]
            return {
                "operation": "TYPE_TEXT" if is_type else "CLICK",
                "target_index": target_idx,
                "text_value": extracted_text or ("LiteSight Agent" if is_type else None),
                "reasoning_summary": f"SpeculativeActionAgent matched [{target_idx}] '{best_candidate.get('label')}'"
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
