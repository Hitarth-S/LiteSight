# src/agents/__init__.py
"""
Local Multi-Agent Swarms for LiteSight.
Deconstructs monolithic orchestrator into specialized edge micro-agents.
Language: STE (Simplified Technical English).
"""

from .swarm import (
    DOMSensorAgent,
    PrivacySentinelAgent,
    SpeculativeActionAgent,
    VisualGroundingAgent,
    SwarmCoordinator
)

__all__ = [
    "DOMSensorAgent",
    "PrivacySentinelAgent",
    "SpeculativeActionAgent",
    "VisualGroundingAgent",
    "SwarmCoordinator"
]
