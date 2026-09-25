# src/federation/__init__.py
"""
Federated Learning package for LiteSight.
Implements privacy-preserving decentralized LoRA weight sharing with Differential Privacy.
"""

from .differential_privacy import DifferentialPrivacyEngine
from .client import FederatedClient, FederatedWeightPayload

__all__ = ["DifferentialPrivacyEngine", "FederatedClient", "FederatedWeightPayload"]
