"""Customer-owned PRWitness DIY red-team substitute.

The package intentionally implements only a small, documented adapter around
the public Free Action artifact surface.  It does not contain browser proof
execution, GitHub App code, hosted storage, or Pro implementation code.
"""

from .core import Decision, State, validate_result

__all__ = ["Decision", "State", "validate_result"]
