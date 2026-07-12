"""Architecture tests: state immutability and Event Sourcing correctness."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.base_module import (
    BaseMarketingModule,
    ModuleExecutionError,
)
from src.core.state import (
    EventStatus,
    EventTelemetry,
    MarketingState,
    StateEvent,
)

TENANT = "tenant_a"


def make_state() -> MarketingState:
    return MarketingState(tenant_id=TENANT)


def make_event(action: str = "TEST_ACTION") -> StateEvent:
    return StateEvent(
        module="TestModule",
        action=action,
        entity="MarketingState",
        entity_id="x",
        changes={"key_changed_1": "new_value"},
        telemetry=EventTelemetry(execution_time_ms=1.0, status=EventStatus.SUCCESS),
    )


class EchoModule(BaseMarketingModule):
    module_name = "EchoModule"

    def process(self, state: MarketingState) -> MarketingState:
        return self.emit(
            state,
            action="ECHO",
            entity="MarketingState",
            entity_id=state.pipeline_id,
            changes={"ping": "pong"},
        )


class SilentModule(BaseMarketingModule):
    """Returns the state untouched — must still leave an audit footprint."""

    def process(self, state: MarketingState) -> MarketingState:
        return state


class ExplodingModule(BaseMarketingModule):
    def process(self, state: MarketingState) -> MarketingState:
        raise RuntimeError("boom")


class TestStateImmutability:
    def test_direct_mutation_is_rejected(self):
        state = make_state()
        with pytest.raises(ValidationError):
            state.tenant_id = "tenant_b"

    def test_apply_returns_new_instance_and_keeps_original(self):
        state = make_state()
        new_state = state.apply(make_event())
        assert new_state is not state
        assert len(new_state.events) == 1
        assert len(state.events) == 0  # original cycle state untouched

    def test_events_accumulate_in_order(self):
        state = make_state()
        state = state.apply(make_event("FIRST"))
        state = state.apply(make_event("SECOND"))
        assert [e.action for e in state.events] == ["FIRST", "SECOND"]


class TestEventSchema:
    def test_event_matches_spec_contract(self):
        payload = make_event().model_dump()
        assert set(payload) == {
            "event_id",
            "module",
            "timestamp",
            "action",
            "entity",
            "entity_id",
            "changes",
            "telemetry",
        }
        assert set(payload["telemetry"]) == {
            "execution_time_ms",
            "status",
            "tokens_used",
            "error_message",
        }

    def test_event_ids_are_unique(self):
        assert make_event().event_id != make_event().event_id


class TestModuleExecution:
    def test_execute_records_success_telemetry(self):
        state = EchoModule().execute(make_state())
        event = state.events[-1]
        assert event.module == "EchoModule"
        assert event.action == "ECHO"
        assert event.changes == {"ping": "pong"}
        assert event.telemetry.status is EventStatus.SUCCESS
        assert event.telemetry.execution_time_ms >= 0.0
        assert event.telemetry.error_message is None

    def test_silent_module_still_leaves_audit_footprint(self):
        state = SilentModule().execute(make_state())
        assert len(state.events) == 1
        assert state.events[-1].action == "MODULE_EXECUTED"

    def test_failure_appends_failed_event_and_raises(self):
        with pytest.raises(ModuleExecutionError) as excinfo:
            ExplodingModule().execute(make_state())
        failed_state = excinfo.value.state
        event = failed_state.events[-1]
        assert event.action == "MODULE_FAILED"
        assert event.telemetry.status is EventStatus.FAILED
        assert event.telemetry.error_message == "boom"

    def test_sequential_modules_share_one_ledger(self):
        state = make_state()
        state = EchoModule().execute(state)
        state = SilentModule().execute(state)
        assert [e.action for e in state.events] == ["ECHO", "MODULE_EXECUTED"]
