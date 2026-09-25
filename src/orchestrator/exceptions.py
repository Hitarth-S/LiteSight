# src/orchestrator/exceptions.py
"""
Required Exceptions & Error Handling Class Hierarchy for LiteSight.
Defined strictly according to ARCHITECTURE.md Section 7.C.
"""

class LiteSightBaseException(Exception):
    """Base exception for all LiteSight runtime errors."""
    pass

class StaleNodeException(LiteSightBaseException):
    """Raised when target_index is no longer present in current DOM tree."""
    pass

class ElementObscuredError(LiteSightBaseException):
    """Raised when target element is covered by overlay/modal or zero-width."""
    pass

class CanvasFallbackTrigger(LiteSightBaseException):
    """Raised when action target resides within non-indexed <canvas> or WebGL context."""
    pass

class PIIRedactionFailure(LiteSightBaseException):
    """Raised if WebGPU privacy kernel fails frame sanitization prior to egress."""
    pass
