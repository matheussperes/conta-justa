"""Priorizer: assigns abstract priority scores to collected opportunities.

V1 uses a deterministic taxonomy-weight mock — no hidden heuristics, the
score composition is fully visible in the event ledger ("Evidence Over
Opinion" will replace these weights with observed statistics later).
"""

from __future__ import annotations

from src.core.base_module import BaseMarketingModule
from src.core.registry import register_plugin
from src.core.state import MarketingState, OpportunityType


@register_plugin(channel="instagram", name="priorizer", layer="intelligence")
class InstagramPriorizer(BaseMarketingModule):
    module_name = "Priorizer"

    #: Deterministic V1 mock weights per opportunity taxonomy.
    TAXONOMY_WEIGHTS = {
        OpportunityType.TREND: 0.90,
        OpportunityType.PERFORMANCE: 0.80,
        OpportunityType.SEASONAL: 0.70,
        OpportunityType.COMMUNITY: 0.60,
    }

    def process(self, state: MarketingState) -> MarketingState:
        if not state.opportunities:
            raise ValueError("No opportunities available to prioritize.")
        scored = tuple(
            opportunity.model_copy(
                update={"priority_score": self.TAXONOMY_WEIGHTS[opportunity.taxonomy]}
            )
            for opportunity in state.opportunities
        )
        return self.emit(
            state,
            action="OPPORTUNITIES_SCORED",
            entity="Opportunity",
            entity_id=f"batch:{len(scored)}",
            changes={o.opportunity_id: o.priority_score for o in scored},
            opportunities=scored,
        )
