"""Channel-agnostic engine layers.

* Layer 1 — Knowledge: ``BrandContextLoader`` loads the tenant's H1 context.
* Layer 4 — Observation: ``ObservationEngine`` injects cold post metrics.
* Layer 5 — Learning: ``LearningEngine`` evaluates experiments with a
  Welch T-Test, derives local insights and dispatches anonymized global
  payloads across the tenant firewall.

Layers 2 (Intelligence) and 3 (Execution) are channel plugins resolved via
the registry — the core stays agnostic.
"""

from __future__ import annotations

from statistics import mean
from typing import Optional, Sequence

from scipy import stats

from src.core.base_module import BaseMarketingModule, TenantIsolationError
from src.core.state import (
    BrandContext,
    Experiment,
    ExperimentStatus,
    Insight,
    InsightScope,
    MarketingState,
    Observation,
    utc_now_iso,
)
from src.infrastructure.repository_interface import MarketingRepository


class BrandContextLoader(BaseMarketingModule):
    """Layer 1: loads the permanent (H1) BrandContext from the tenant sandbox."""

    module_name = "BrandContextLoader"

    def __init__(self, repository: MarketingRepository) -> None:
        super().__init__()
        self._repository = repository

    def process(self, state: MarketingState) -> MarketingState:
        raw = self._repository.read(state.tenant_id, "brand_context")
        if not raw:
            raise ValueError(
                f"BrandContext not found for tenant '{state.tenant_id}'."
            )
        context = BrandContext.model_validate(raw)
        if context.tenant_id != state.tenant_id:
            raise TenantIsolationError(
                f"BrandContext of tenant '{context.tenant_id}' cannot enter a "
                f"pipeline scoped to tenant '{state.tenant_id}'."
            )
        return self.emit(
            state,
            action="BRAND_CONTEXT_LOADED",
            entity="BrandContext",
            entity_id=context.tenant_id,
            changes={
                "positioning": context.positioning,
                "tone_of_voice": context.tone_of_voice,
                "restrictions": len(context.restrictions),
            },
            brand_context=context,
        )


class ObservationEngine(BaseMarketingModule):
    """Layer 4: records cold post-publication metrics for each artifact.

    V1 has no live Instagram API, so metrics come either from an injected
    feed or from a deterministic mock generator.
    """

    module_name = "ObservationEngine"

    def __init__(self, metrics_feed: Optional[Sequence[Observation]] = None) -> None:
        super().__init__()
        self._feed = {obs.artifact_id: obs for obs in (metrics_feed or ())}

    def process(self, state: MarketingState) -> MarketingState:
        current = state
        observed_ids = {obs.artifact_id for obs in state.observations}
        for index, artifact in enumerate(state.artifacts):
            if artifact.artifact_id in observed_ids:
                continue
            observation = self._feed.get(
                artifact.artifact_id
            ) or self._deterministic_mock(current.tenant_id, artifact.artifact_id, index)
            current = self.emit(
                current,
                action="OBSERVATION_RECORDED",
                entity="Observation",
                entity_id=observation.observation_id,
                changes={
                    "artifact_id": observation.artifact_id,
                    "views": observation.views,
                    "saves": observation.saves,
                    "shares": observation.shares,
                    "retention_rate": observation.retention_rate,
                },
                observations=current.observations + (observation,),
            )
        return current

    @staticmethod
    def _deterministic_mock(
        tenant_id: str, artifact_id: str, index: int
    ) -> Observation:
        base = 4200 + index * 850
        return Observation(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            views=base,
            saves=int(base * 0.045),
            shares=int(base * 0.018),
            retention_rate=round(0.38 + index * 0.03, 4),
        )


class LearningEngine(BaseMarketingModule):
    """Layer 5: evaluates pending experiments (Welch T-Test), derives insights.

    Local insights stay inside the tenant sandbox. Confirmed learnings are
    abstracted into anonymized payloads and dispatched to the global engine
    knowledge base — never carrying raw tenant identifiers.
    """

    module_name = "LearningEngine"
    SIGNIFICANCE_LEVEL = 0.05
    MIN_SAMPLES_PER_GROUP = 2

    def __init__(self, repository: Optional[MarketingRepository] = None) -> None:
        super().__init__()
        self._repository = repository

    def process(self, state: MarketingState) -> MarketingState:
        current = state
        evaluated: list[Experiment] = []
        for experiment in state.experiments:
            if experiment.status is not ExperimentStatus.PENDING:
                evaluated.append(experiment)
                continue
            result = self._evaluate(experiment)
            evaluated.append(result)
            current = self.emit(
                current,
                action="EXPERIMENT_EVALUATED",
                entity="Experiment",
                entity_id=result.experiment_id,
                changes={
                    "lift": result.lift,
                    "p_value": result.p_value,
                    "status": result.status.value,
                },
            )
            if result.status is ExperimentStatus.CONFIRMED:
                current = self._derive_insights(current, result)
        return current.model_copy(update={"experiments": tuple(evaluated)})

    # -- statistics -----------------------------------------------------------

    def _evaluate(self, experiment: Experiment) -> Experiment:
        if (
            len(experiment.group_a) < self.MIN_SAMPLES_PER_GROUP
            or len(experiment.group_b) < self.MIN_SAMPLES_PER_GROUP
        ):
            return experiment.model_copy(
                update={"status": ExperimentStatus.INCONCLUSIVE}
            )
        mean_a = mean(experiment.group_a)
        mean_b = mean(experiment.group_b)
        lift = (mean_b - mean_a) / mean_a if mean_a else 0.0
        _, p_value = stats.ttest_ind(
            experiment.group_b, experiment.group_a, equal_var=False
        )
        p_value = float(p_value)
        if p_value >= self.SIGNIFICANCE_LEVEL:
            status = ExperimentStatus.INCONCLUSIVE
        elif lift > 0:
            status = ExperimentStatus.CONFIRMED
        else:
            status = ExperimentStatus.REJECTED
        return experiment.model_copy(
            update={
                "lift": round(lift, 6),
                "p_value": round(p_value, 8),
                "status": status,
            }
        )

    # -- insight derivation -----------------------------------------------------

    def _derive_insights(
        self, state: MarketingState, experiment: Experiment
    ) -> MarketingState:
        confidence = round(min(1.0 - (experiment.p_value or 0.0), 1.0), 6)
        statement = (
            f"'{experiment.independent_variable}' lifts "
            f"'{experiment.dependent_variable}' by {experiment.lift:+.1%} "
            f"(p={experiment.p_value:.5f})."
        )
        local = Insight(
            scope=InsightScope.LOCAL,
            tenant_id=state.tenant_id,
            statement=statement,
            confidence=confidence,
            source_experiment_id=experiment.experiment_id,
        )
        global_insight = Insight(
            scope=InsightScope.GLOBAL,
            tenant_id=None,  # anonymized: never crosses the firewall
            statement=statement,
            confidence=confidence,
            source_experiment_id=None,
        )
        state = self.emit(
            state,
            action="INSIGHT_GENERATED",
            entity="Insight",
            entity_id=local.insight_id,
            changes={"scope": "LOCAL", "statement": statement},
            insights=state.insights + (local, global_insight),
        )
        if self._repository is not None:
            payload = {
                "insight_id": global_insight.insight_id,
                "channel": "instagram",
                "variable": experiment.independent_variable,
                "metric": experiment.dependent_variable,
                "lift": experiment.lift,
                "p_value": experiment.p_value,
                "confidence": confidence,
                "derived_at": utc_now_iso(),
            }
            self._repository.append_global("global_insights", payload)
            state = self.emit(
                state,
                action="GLOBAL_INSIGHT_DISPATCHED",
                entity="Insight",
                entity_id=global_insight.insight_id,
                changes={"scope": "GLOBAL", "anonymized": True},
            )
        return state
