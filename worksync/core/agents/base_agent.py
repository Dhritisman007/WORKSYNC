"""The contract every agent implements.

Agents are pure functions of an Envelope: they never call each other
directly, hold no shared mutable state, and never branch on `vertical`.
Only the orchestrator decides which agent runs next.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from worksync.core.schemas.models import AgentName, Envelope


class BaseAgent(ABC):
    name: AgentName

    @abstractmethod
    def handle(self, envelope: Envelope) -> Envelope:
        """Consume one Envelope and produce the next one in the pipeline."""
        raise NotImplementedError
