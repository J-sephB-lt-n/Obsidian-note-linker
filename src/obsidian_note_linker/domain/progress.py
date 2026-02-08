"""Generic progress update for streaming operations.

Provides a simple frozen dataclass used by any service that reports
progress back to the UI via SSE.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressUpdate:
    """A single progress update for a long-running operation.

    Attributes:
        phase: Name of the current processing phase.
        current: Number of items completed so far.
        total: Total number of items in this phase.
        message: Human-readable description of current activity.
    """

    phase: str
    current: int
    total: int
    message: str
