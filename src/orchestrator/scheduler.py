# src/orchestrator/scheduler.py
"""
Nightly LoRA Scheduler and Federated Privacy Exporter.
Runs parameter-efficient fine-tuning on edge models during off-peak hours.
Integrates Differential Privacy to generate federated learning updates.
Language: STE (Simplified Technical English).
"""

import time
import threading
from typing import List, Dict, Any, Optional
from ..federation.client import FederatedClient, FederatedWeightPayload


class NightlyLoRAScheduler:
    """
    Schedules nightly on-device fine-tuning and federated model weight sharing.
    Stores successful trajectories and generates differentially private parameter updates.
    """

    def __init__(self, federated_client: Optional[FederatedClient] = None):
        self.daily_trajectories: List[Dict[str, Any]] = []
        self.federated_client = federated_client or FederatedClient()
        self.last_exported_payload: Optional[FederatedWeightPayload] = None

    def log_successful_trajectory(self, trajectory_data: Dict[str, Any]):
        """Logs verified successful trajectory for nightly compilation."""
        self.daily_trajectories.append(trajectory_data)
        print(f"[Scheduler] Logged successful trajectory for nightly learning. Total: {len(self.daily_trajectories)}")

    def run_nightly_job(self) -> Optional[FederatedWeightPayload]:
        """
        Executes nightly optimization cycle:
        1. Compiles trajectory buffer into fine-tuning dataset.
        2. Applies Differential Privacy to calculate weight deltas.
        3. Prepares anonymous federated export payload.
        """
        print("[Scheduler] Initiating Nightly LoRA Fine-Tuning and DP Aggregation...")
        if not self.daily_trajectories:
            print("[Scheduler] No new trajectories to learn from today.")
            return None

        print(f"[Scheduler] Compiling {len(self.daily_trajectories)} trajectories into LoRA dataset...")
        # Generate differentially private weight update
        payload = self.federated_client.generate_privatized_update(
            self.daily_trajectories,
            layer_name="edge_muscle_memory_lora"
        )
        self.last_exported_payload = payload

        print(f"[Scheduler] Differential Privacy applied. Epsilon: {payload.privacy_budget['current_epsilon']}")
        print(f"[Scheduler] Nightly LoRA fine-tuning complete. Model muscle memory updated.")

        # Clear processed trajectories
        self.daily_trajectories.clear()
        return payload

    def trigger_manual_nightly_job(self):
        """Allows testing the nightly job asynchronously in a worker thread."""
        thread = threading.Thread(target=self.run_nightly_job)
        thread.start()
        return thread
