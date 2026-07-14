"""Abstract contract every pipeline module must honor.

``BaseMarketingModule`` implements the template method :meth:`execute`,
which wraps the pure :meth:`process` with native telemetry (wall time,
status, error capture) and a tenant-firewall guard. Modules never talk to
each other directly — they only transform the shared ``MarketingState``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any, ClassVar, Dict, Optional

from src.core.state import (
    EventStatus,
    EventTelemetry,
    MarketingState,
    StateEvent,
)


class TenantIsolationError(RuntimeError):
    """Raised when an operation would cross the logical tenant firewall."""


class ModuleExecutionError(RuntimeError):
    """Raised when a module fails. Carries the state with the FAILED event appended."""

    def __init__(self, module: str, original: Exception, state: MarketingState):
        super().__init__(f"Module '{module}' failed: {original}")
        self.module = module
        self.original = original
        self.state = state


class BaseMarketingModule(ABC):
    """Base class for every layer of the engine and every channel plugin."""

    #: Override to customize the name recorded in the event ledger.
    module_name: ClassVar[Optional[str]] = None

    def __init__(self) -> None:
        self._started_at: Optional[float] = None

    @property
    def name(self) -> str:
        return self.module_name or type(self).__name__

    # -- contract ----------------------------------------------------------

    @abstractmethod
    def process(self, state: MarketingState) -> MarketingState:
        """Pure transformation: receive a state, return a derived state.

        Implementations must not mutate ``state`` (it is frozen) and must
        use :meth:`emit` to record every relevant mutation as an event.
        """

    # -- telemetry-aware execution ------------------------------------------

    def execute(self, state: MarketingState) -> MarketingState:
        """Run :meth:`process` with timing, failure capture and tenant guard."""
        self._started_at = perf_counter()
        events_before = len(state.events)
        try:
            new_state = self.process(state)
        except Exception as exc:  # audit trail first, then propagate
            failed_state = self.emit(
                state,
                action="MODULE_FAILED",
                entity="MarketingState",
                entity_id=state.pipeline_id,
                status=EventStatus.FAILED,
                error_message=str(exc) or type(exc).__name__,
            )
            raise ModuleExecutionError(self.name, exc, failed_state) from exc

        if not isinstance(new_state, MarketingState):
            raise TypeError(
                f"Module '{self.name}' must return a MarketingState, "
                f"got {type(new_state).__name__}."
            )
        if new_state.tenant_id != state.tenant_id:
            raise TenantIsolationError(
                f"Module '{self.name}' attempted to re-scope the state from "
                f"tenant '{state.tenant_id}' to '{new_state.tenant_id}'."
            )
        if len(new_state.events) == events_before:
            # Every executed module leaves at least one auditable footprint.
            new_state = self.emit(
                new_state,
                action="MODULE_EXECUTED",
                entity="MarketingState",
                entity_id=state.pipeline_id,
            )
        return new_state

    def emit(
        self,
        state: MarketingState,
        *,
        action: str,
        entity: str,
        entity_id: str,
        changes: Optional[Dict[str, Any]] = None,
        status: EventStatus = EventStatus.SUCCESS,
        tokens_used: Optional[int] = None,
        error_message: Optional[str] = None,
        **updates: Any,
    ) -> MarketingState:
        """Record a ledger event (with telemetry) and apply state updates."""
        event = StateEvent(
            module=self.name,
            action=action,
            entity=entity,
            entity_id=entity_id,
            changes=changes or {},
            telemetry=EventTelemetry(
                execution_time_ms=self._elapsed_ms(),
                status=status,
                tokens_used=tokens_used,
                error_message=error_message,
            ),
        )
        return state.apply(event, **updates)

    def _elapsed_ms(self) -> float:
        if self._started_at is None:
            return 0.0
        return (perf_counter() - self._started_at) * 1000.0
