# src/federation/client.py
"""
Federated Learning Edge Client for LiteSight.
Transforms verified local action trajectories into differentially private weight updates.
Enforces zero user data egress: no raw URLs, tokens, or credentials leave the edge.
Language: STE (Simplified Technical English).
"""

import time
import hashlib
from typing import Dict, Any, List, Optional
import numpy as np
from .differential_privacy import DifferentialPrivacyEngine


class FederatedWeightPayload:
    """
    Immutable transport payload for differentially private federated weight updates.
    """
    def __init__(
        self,
        client_id: str,
        layer_name: str,
        privatized_delta: np.ndarray,
        sample_count: int,
        privacy_budget: Dict[str, float]
    ):
        self.client_id = client_id
        self.layer_name = layer_name
        self.privatized_delta = privatized_delta
        self.sample_count = sample_count
        self.privacy_budget = privacy_budget
        self.timestamp = int(time.time() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the payload into a dictionary for transmission."""
        return {
            "client_id": self.client_id,
            "layer_name": self.layer_name,
            "privatized_delta": self.privatized_delta.tolist(),
            "sample_count": self.sample_count,
            "privacy_budget": self.privacy_budget,
            "timestamp": self.timestamp
        }


class FederatedClient:
    """
    Local edge client for decentralized learning.
    Extracts policy adjustments from daily trajectories, computes parameter deltas,
    applies differential privacy, and creates egress packages.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        epsilon: float = 1.0,
        delta: float = 1e-5,
        clip_norm: float = 1.0,
        weight_dimension: int = 128
    ):
        if client_id is None:
            # Deterministic anonymous client identifier
            random_seed = f"litesight_edge_{time.time()}"
            self.client_id = hashlib.sha256(random_seed.encode("utf-8")).hexdigest()[:16]
        else:
            self.client_id = client_id

        self.dp_engine = DifferentialPrivacyEngine(
            epsilon=epsilon,
            delta=delta,
            clip_norm=clip_norm
        )
        self.weight_dimension = weight_dimension
        self.local_weights = np.zeros(self.weight_dimension, dtype=np.float32)

    def compute_trajectory_delta(self, trajectories: List[Dict[str, Any]]) -> np.ndarray:
        """
        Computes synthetic parameter delta from successful trajectories.
        Transforms action sequences into parameter adjustments without storing personal data.
        """
        if not trajectories:
            return np.zeros(self.weight_dimension, dtype=np.float32)

        delta = np.zeros(self.weight_dimension, dtype=np.float32)
        for traj in trajectories:
            # Hash goal string into deterministic parameter adjustments
            goal = str(traj.get("goal", ""))
            hashed_goal = hashlib.sha256(goal.encode("utf-8")).digest()
            pseudo_gradient = np.frombuffer(hashed_goal * 4, dtype=np.int8)[:self.weight_dimension].astype(np.float32) / 128.0
            delta += pseudo_gradient

        # Average across trajectories
        delta /= max(1, len(trajectories))
        return delta

    def generate_privatized_update(
        self,
        trajectories: List[Dict[str, Any]],
        layer_name: str = "lora_edge_policy"
    ) -> FederatedWeightPayload:
        """
        Processes local trajectories and generates a differentially private payload.
        """
        raw_delta = self.compute_trajectory_delta(trajectories)
        dp_result = self.dp_engine.privatize_weights(raw_delta)

        # Update local model weights with privatized gradient
        self.local_weights += dp_result["privatized_weights"]

        payload = FederatedWeightPayload(
            client_id=self.client_id,
            layer_name=layer_name,
            privatized_delta=dp_result["privatized_weights"],
            sample_count=len(trajectories),
            privacy_budget=self.dp_engine.get_budget_status()
        )
        return payload

    def apply_aggregated_update(self, global_delta: np.ndarray):
        """
        Applies federated server aggregate delta back to edge model.
        """
        if global_delta.shape != self.local_weights.shape:
            raise ValueError(f"Shape mismatch: {global_delta.shape} vs {self.local_weights.shape}")
        self.local_weights += global_delta
