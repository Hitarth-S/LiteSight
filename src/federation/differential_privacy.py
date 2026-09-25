# src/federation/differential_privacy.py
"""
Differential Privacy Engine for Federated Learning.
Implements Gaussian mechanism with L2 norm clipping.
Guarantees (epsilon, delta)-Differential Privacy for client model weight deltas.
Language: STE (Simplified Technical English).
"""

import math
from typing import Dict, Any, Tuple
import numpy as np


class DifferentialPrivacyEngine:
    """
    Applies Differential Privacy to model parameter tensors.
    Protects user privacy before sending local weights to a federated server.
    """

    def __init__(
        self,
        epsilon: float = 1.0,
        delta: float = 1e-5,
        clip_norm: float = 1.0
    ):
        if epsilon <= 0:
            raise ValueError("Epsilon must be greater than zero.")
        if not (0 < delta < 1.0):
            raise ValueError("Delta must be between 0 and 1.")
        if clip_norm <= 0:
            raise ValueError("Clip norm must be greater than zero.")

        self.epsilon = float(epsilon)
        self.delta = float(delta)
        self.clip_norm = float(clip_norm)
        self.sigma = self._compute_noise_multiplier()
        self.total_epsilon_spent = 0.0
        self.total_delta_spent = 0.0

    def _compute_noise_multiplier(self) -> float:
        """
        Computes Gaussian standard deviation using the analytic Gaussian mechanism.
        Formula: sigma = (clip_norm * sqrt(2 * ln(1.25 / delta))) / epsilon
        """
        factor = math.sqrt(2.0 * math.log(1.25 / self.delta))
        return (self.clip_norm * factor) / self.epsilon

    def clip_vector(self, weights: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Clips vector norm to maximum threshold clip_norm.
        Returns clipped vector and computed L2 norm.
        """
        l2_norm = float(np.linalg.norm(weights))
        if l2_norm > self.clip_norm and l2_norm > 0:
            scaling = self.clip_norm / l2_norm
            return weights * scaling, l2_norm
        return weights.copy(), l2_norm

    def add_noise(self, clipped_weights: np.ndarray) -> np.ndarray:
        """
        Adds zero-mean Gaussian noise calibrated to the privacy budget.
        """
        noise = np.random.normal(0.0, self.sigma, size=clipped_weights.shape)
        return (clipped_weights + noise).astype(clipped_weights.dtype)

    def privatize_weights(self, weights: np.ndarray) -> Dict[str, Any]:
        """
        Executes complete DP pipeline:
        1. Clips L2 norm to threshold.
        2. Adds calibrated Gaussian noise.
        3. Records budget expenditure.
        """
        flat_weights = weights.flatten().astype(np.float64)
        clipped, original_norm = self.clip_vector(flat_weights)
        noisy = self.add_noise(clipped)

        # Track privacy consumption
        self.total_epsilon_spent += self.epsilon
        self.total_delta_spent += self.delta

        sanitized_weights = noisy.reshape(weights.shape)
        return {
            "privatized_weights": sanitized_weights,
            "original_norm": float(original_norm),
            "clipped_norm": float(np.linalg.norm(clipped)),
            "epsilon_spent": self.epsilon,
            "delta_spent": self.delta,
            "sigma": self.sigma
        }

    def get_budget_status(self) -> Dict[str, float]:
        """Returns total privacy budget expended by this edge client."""
        return {
            "total_epsilon_spent": self.total_epsilon_spent,
            "total_delta_spent": self.total_delta_spent,
            "current_epsilon": self.epsilon,
            "current_delta": self.delta,
            "clip_norm": self.clip_norm,
            "sigma": self.sigma
        }
