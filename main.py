"""Marketing OS — central orchestrator / pipeline simulation CLI.

Runs a full decision cycle for a simulated tenant through the five layers
(Knowledge → Intelligence → Execution → Observation → Learning) and prints
the Execution Timeline reconstructed from the Event Sourcing ledger.

Usage (from ``marketing-os-core/``)::

    python main.py
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from src.core.base_module import BaseMarketingModule, ModuleExecutionError
from src.core.engine import BrandContextLoader, LearningEngine, ObservationEngine
from src.core.registry import registry
from src.core.state import (
    Experiment,
    InsightScope,
    MarketingState,
    Opportunity,
    OpportunityType,
    StateEvent,
)
from src.infrastructure.json_repository import JsonRepository

# Importing the channel package registers its plugins in the registry.
import src.plugins.instagram  # noqa: F401

CHANNEL = "instagram"
TENANT_ID = "tenant_template"
DATA_PATH = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# Simulation inputs (mocked market signals and retrospective A/B data)
# ---------------------------------------------------------------------------

def build_initial_state() -> MarketingState:
    opportunities = (
        Opportunity(
            tenant_id=TENANT_ID,
            taxonomy=OpportunityType.TREND,
            title="Viral audio about productivity myths",
            description="Rising trend detected in the niche over the last 48h.",
            source="mock_trend_scanner",
        ),
        Opportunity(
            tenant_id=TENANT_ID,
            taxonomy=OpportunityType.SEASONAL,
            title="Mid-year planning season",
            description="Audience historically searches for planning content in July.",
            source="mock_seasonal_calendar",
        ),
        Opportunity(
            tenant_id=TENANT_ID,
            taxonomy=OpportunityType.COMMUNITY,
            title="Recurring DM question about pricing strategy",
            description="Same question appeared 14 times in DMs this week.",
            source="mock_community_listener",
        ),
    )
    # Retrospective A/B data: saves-per-reach of past posts without (A) and
    # with (B) an explicit "save this" CTA. Evaluated by the LearningEngine.
    experiment = Experiment(
        tenant_id=TENANT_ID,
        hypothesis="Posts with an explicit save CTA generate more saves per reach.",
        independent_variable="explicit_save_cta",
        dependent_variable="saves_per_reach",
        group_a=[0.031, 0.028, 0.035, 0.030, 0.027],
        group_b=[0.042, 0.047, 0.039, 0.044, 0.048],
    )
    return MarketingState(
        tenant_id=TENANT_ID,
        opportunities=opportunities,
        experiments=(experiment,),
    )


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(state: MarketingState, repository: JsonRepository) -> MarketingState:
    # Layers 1-2: knowledge + intelligence.
    modules: List[BaseMarketingModule] = [
        BrandContextLoader(repository),
        registry.get(CHANNEL, "priorizer")(),
        registry.get(CHANNEL, "decision_maker")(),
    ]
    for module in modules:
        state = module.execute(state)

    # Layer 3: route to the format specialist chosen by the Decision.
    decision = state.last_decision
    assert decision is not None
    specialist_cls = registry.resolve_by_format(CHANNEL, decision.content_format)
    state = specialist_cls().execute(state)

    # Layers 4-5: observation + learning.
    state = ObservationEngine().execute(state)
    state = LearningEngine(repository).execute(state)
    return state


def persist_cycle(state: MarketingState, repository: JsonRepository) -> None:
    """Materialize the cycle results into the tenant sandbox (audit trail)."""
    for decision in state.decisions:
        repository.append(TENANT_ID, "decision_ledger", decision.model_dump(mode="json"))
    for artifact in state.artifacts:
        repository.append(TENANT_ID, "post_history", artifact.model_dump(mode="json"))
    for insight in state.insights:
        if insight.scope is InsightScope.LOCAL:
            repository.append(TENANT_ID, "local_insights", insight.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_timeline(events: tuple[StateEvent, ...]) -> None:
    print()
    print("=" * 96)
    print("EXECUTION TIMELINE (Event Sourcing Ledger)")
    print("=" * 96)
    header = f"{'#':>2}  {'MODULE':<20} {'ACTION':<26} {'ENTITY':<18} {'STATUS':<8} {'TIME':>10}"
    print(header)
    print("-" * 96)
    for index, event in enumerate(events, start=1):
        telemetry = event.telemetry
        print(
            f"{index:>2}  {event.module:<20} {event.action:<26} "
            f"{event.entity:<18} {telemetry.status.value:<8} "
            f"{telemetry.execution_time_ms:>7.2f} ms"
        )
    total_ms = sum(event.telemetry.execution_time_ms for event in events)
    print("-" * 96)
    print(f"{len(events)} events recorded — cumulative module time: {total_ms:.2f} ms")


def print_summary(state: MarketingState) -> None:
    decision = state.last_decision
    artifact = state.last_artifact
    if decision:
        print()
        print("DECISION LEDGER ENTRY")
        print(f"  Objective ......... {decision.primary_objective}")
        print(f"  Format / slot ..... {decision.content_format.value} @ {decision.slot}")
        print(f"  Framework ......... {decision.framework}")
        print(
            f"  Scores ............ expected_performance={decision.expected_performance_score:.2f} "
            f"| strategic_capital={decision.strategic_capital_score:.2f}"
        )
        print(f"  Alternatives ...... {len(decision.alternatives)} evaluated")
        print(f"  Rationale ......... {decision.rationale}")
    if artifact:
        print()
        print("CONTENT ARTIFACT")
        if artifact.reel_script:
            print(f"  Hook (3s) ......... {artifact.reel_script.hook_3s}")
            for line in artifact.reel_script.lines:
                print(f"    - {line}")
            print(f"  CTA ............... {artifact.reel_script.cta}")
        if artifact.slides:
            for slide in artifact.slides:
                print(f"  Slide {slide.index}: {slide.title} — {slide.body}")
    if state.insights:
        print()
        print("INSIGHTS")
        for insight in state.insights:
            print(f"  [{insight.scope.value}] {insight.statement} (confidence={insight.confidence:.4f})")
    print()


def main() -> None:
    repository = JsonRepository(DATA_PATH)
    state = build_initial_state()
    print(f"Marketing OS — simulating pipeline for tenant '{TENANT_ID}' on '{CHANNEL}'")
    try:
        state = run_pipeline(state, repository)
    except ModuleExecutionError as error:
        print(f"\nPipeline aborted: {error}")
        print_timeline(error.state.events)
        raise SystemExit(1)
    persist_cycle(state, repository)
    print_timeline(state.events)
    print_summary(state)


if __name__ == "__main__":
    main()
