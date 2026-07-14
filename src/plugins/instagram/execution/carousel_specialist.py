"""CarouselSpecialist: turns a Decision into a slide-by-slide Carousel script.

V1 generates deterministic templated content — the LLM call will replace
``_draft_slides`` behind the same interface later.
"""

from __future__ import annotations

from typing import List

from src.core.base_module import BaseMarketingModule
from src.core.registry import register_plugin
from src.core.state import (
    CarouselSlide,
    ContentArtifact,
    ContentFormat,
    Decision,
    MarketingState,
)


@register_plugin(
    channel="instagram",
    name="carousel_specialist",
    formats=(ContentFormat.CAROUSEL,),
    layer="execution",
)
class CarouselSpecialist(BaseMarketingModule):
    module_name = "CarouselSpecialist"

    def process(self, state: MarketingState) -> MarketingState:
        decision = state.last_decision
        if decision is None or decision.content_format is not ContentFormat.CAROUSEL:
            raise ValueError("CarouselSpecialist requires a pending CAROUSEL decision.")

        slides = self._draft_slides(decision)
        artifact = ContentArtifact(
            tenant_id=state.tenant_id,
            decision_id=decision.decision_id,
            format=ContentFormat.CAROUSEL,
            caption=(
                f"Executed under framework '{decision.framework}' — "
                f"objective: {decision.primary_objective}."
            ),
            slides=slides,
        )
        return self.emit(
            state,
            action="CONTENT_GENERATED",
            entity="ContentArtifact",
            entity_id=artifact.artifact_id,
            changes={
                "format": ContentFormat.CAROUSEL.value,
                "decision_id": decision.decision_id,
                "slides": len(slides),
            },
            tokens_used=768,  # mock telemetry for the future LLM call
            artifacts=state.artifacts + (artifact,),
        )

    @staticmethod
    def _draft_slides(decision: Decision) -> List[CarouselSlide]:
        return [
            CarouselSlide(index=1, title="The problem", body="Name the pain in one bold line."),
            CarouselSlide(index=2, title="Why it persists", body="Agitate: the hidden cost of ignoring it."),
            CarouselSlide(index=3, title="The shift", body="Present the evidence-backed reframe."),
            CarouselSlide(index=4, title="How to apply", body="Three concrete steps, one per line."),
            CarouselSlide(index=5, title="Save this", body="CTA aligned with the decision objective."),
        ]
