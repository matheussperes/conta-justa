"""DecisionMaker: the AI CMO ledger writer.

Picks the winning opportunity, weighs Expected Performance against
Strategic Capital, selects slot/format/framework and records the full
rationale — the content produced downstream is a consequence of this
Decision ("Decision First" principle).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.core.base_module import BaseMarketingModule
from src.core.registry import register_plugin
from src.core.state import (
    CalendarSlot,
    ContentFormat,
    Decision,
    DecisionAlternative,
    EditorialCalendar,
    Horizon,
    MarketingState,
    Opportunity,
    OpportunityType,
)


@register_plugin(channel="instagram", name="decision_maker", layer="intelligence")
class InstagramDecisionMaker(BaseMarketingModule):
    module_name = "DecisionMaker"

    #: Deterministic V1 mock: how much lasting brand equity each taxonomy builds.
    STRATEGIC_CAPITAL = {
        OpportunityType.COMMUNITY: 0.90,
        OpportunityType.SEASONAL: 0.70,
        OpportunityType.PERFORMANCE: 0.60,
        OpportunityType.TREND: 0.40,
    }

    FRAMEWORKS = {
        ContentFormat.REEL: "hook-retention-cta",
        ContentFormat.CAROUSEL: "problem-agitate-solve",
    }

    def process(self, state: MarketingState) -> MarketingState:
        ranked = sorted(
            state.opportunities,
            key=lambda o: o.priority_score or -1.0,
            reverse=True,
        )
        if not ranked or ranked[0].priority_score is None:
            raise ValueError("Opportunities must be prioritized before deciding.")
        winner = ranked[0]

        content_format = self._select_format(winner)
        framework = self.FRAMEWORKS[content_format]
        alternatives = self._build_alternatives(ranked, winner)
        horizons = [Horizon.H1] + (
            [Horizon.H3] if winner.taxonomy is OpportunityType.TREND else [Horizon.H2]
        )
        slot = "thursday-18h"
        decision = Decision(
            tenant_id=state.tenant_id,
            opportunity_id=winner.opportunity_id,
            primary_objective="Maximize saves and qualified reach",
            horizons=horizons,
            alternatives=alternatives,
            expected_performance_score=winner.priority_score,
            strategic_capital_score=self.STRATEGIC_CAPITAL[winner.taxonomy],
            framework=framework,
            rationale=(
                f"Opportunity '{winner.title}' ({winner.taxonomy.value}) holds the "
                f"highest priority score ({winner.priority_score:.2f}). Format "
                f"{content_format.value} fits its consumption pattern, and the "
                f"'{framework}' framework aligns with the primary objective while "
                f"respecting the brand restrictions loaded from H1."
            ),
            slot=slot,
            content_format=content_format,
        )
        state = self.emit(
            state,
            action="CREATE_DECISION",
            entity="Decision",
            entity_id=decision.decision_id,
            changes={
                "primary_objective": decision.primary_objective,
                "content_format": content_format.value,
                "framework": framework,
                "slot": slot,
                "expected_performance_score": decision.expected_performance_score,
                "strategic_capital_score": decision.strategic_capital_score,
            },
            decisions=state.decisions + (decision,),
        )

        week = datetime.now(timezone.utc).strftime("%G-W%V")
        calendar = EditorialCalendar(
            tenant_id=state.tenant_id,
            week=week,
            slots=[
                CalendarSlot(
                    weekday="thursday",
                    time="18:00",
                    content_format=content_format,
                    objective=decision.primary_objective,
                    decision_id=decision.decision_id,
                )
            ],
        )
        return self.emit(
            state,
            action="SCHEDULE_SLOT",
            entity="EditorialCalendar",
            entity_id=calendar.calendar_id,
            changes={"week": week, "slot": slot, "format": content_format.value},
            calendar=calendar,
        )

    @staticmethod
    def _select_format(winner: Opportunity) -> ContentFormat:
        # Deterministic V1 routing rule: fast-consumption signals become Reels,
        # depth-oriented signals become Carousels.
        if winner.taxonomy in (OpportunityType.TREND, OpportunityType.COMMUNITY):
            return ContentFormat.REEL
        return ContentFormat.CAROUSEL

    def _build_alternatives(
        self, ranked: List[Opportunity], winner: Opportunity
    ) -> List[DecisionAlternative]:
        return [
            DecisionAlternative(
                option=f"{opportunity.taxonomy.value}: {opportunity.title}",
                expected_performance=opportunity.priority_score or 0.0,
                strategic_capital=self.STRATEGIC_CAPITAL[opportunity.taxonomy],
                selected=opportunity.opportunity_id == winner.opportunity_id,
                rejection_reason=(
                    None
                    if opportunity.opportunity_id == winner.opportunity_id
                    else "Lower composite score than the selected opportunity."
                ),
            )
            for opportunity in ranked
        ]
