"""ReelsSpecialist: turns a Decision into a Reel artifact (3s hook + lines).

V1 generates deterministic templated content — the LLM call will replace
``_draft_script`` behind the same interface later.
"""

from __future__ import annotations

from src.core.base_module import BaseMarketingModule
from src.core.registry import register_plugin
from src.core.state import (
    ContentArtifact,
    ContentFormat,
    MarketingState,
    ReelScript,
)


@register_plugin(
    channel="instagram",
    name="reels_specialist",
    formats=(ContentFormat.REEL,),
    layer="execution",
)
class ReelsSpecialist(BaseMarketingModule):
    module_name = "ReelsSpecialist"

    def process(self, state: MarketingState) -> MarketingState:
        decision = state.last_decision
        if decision is None or decision.content_format is not ContentFormat.REEL:
            raise ValueError("ReelsSpecialist requires a pending REEL decision.")

        tone = state.brand_context.tone_of_voice if state.brand_context else "neutral"
        script = ReelScript(
            hook_3s=(
                "Stop scrolling: this is the mistake keeping your results stuck."
            ),
            lines=[
                f"[0-3s] Hook on screen — delivery: {tone}",
                "[3-10s] Name the pain the audience recognizes immediately.",
                "[10-20s] Show the counterintuitive insight behind the decision.",
                "[20-28s] Give one actionable step the viewer can apply today.",
            ],
            cta="Save this reel and follow for the next experiment result.",
        )
        artifact = ContentArtifact(
            tenant_id=state.tenant_id,
            decision_id=decision.decision_id,
            format=ContentFormat.REEL,
            caption=(
                f"Executed under framework '{decision.framework}' — "
                f"objective: {decision.primary_objective}."
            ),
            reel_script=script,
        )
        return self.emit(
            state,
            action="CONTENT_GENERATED",
            entity="ContentArtifact",
            entity_id=artifact.artifact_id,
            changes={
                "format": ContentFormat.REEL.value,
                "decision_id": decision.decision_id,
                "hook_3s": script.hook_3s,
                "lines": len(script.lines),
            },
            tokens_used=512,  # mock telemetry for the future LLM call
            artifacts=state.artifacts + (artifact,),
        )
