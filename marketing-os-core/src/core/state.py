"""MarketingState, domain entities and the Event Sourcing schema.

Every pipeline run is governed by a single transient ``MarketingState``.
The state is immutable per cycle: modules never mutate it in place, they
derive a new copy and append ``StateEvent`` records to the ledger. The
event ledger is the audit trail ("Auditability" principle) and the
development telemetry channel at the same time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp used across the whole event ledger."""
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Taxonomies
# ---------------------------------------------------------------------------

class Horizon(str, Enum):
    """Strategic horizons: H1 = permanent brand DNA, H2 = seasonal, H3 = real time."""

    H1 = "H1"
    H2 = "H2"
    H3 = "H3"


class OpportunityType(str, Enum):
    TREND = "TREND"
    SEASONAL = "SEASONAL"
    COMMUNITY = "COMMUNITY"
    PERFORMANCE = "PERFORMANCE"


class ContentFormat(str, Enum):
    """V1 scope: Instagram only, Reels and Carousels only."""

    REEL = "REEL"
    CAROUSEL = "CAROUSEL"


class InsightScope(str, Enum):
    LOCAL = "LOCAL"
    GLOBAL = "GLOBAL"


class ExperimentStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class EventStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Domain entities
# ---------------------------------------------------------------------------

class Tenant(BaseModel):
    """A client of the platform. All raw data lives inside its logical firewall."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(default_factory=new_id, min_length=1)
    brand_name: str
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Product(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    price: Optional[float] = Field(default=None, ge=0)


class BrandContext(BaseModel):
    """H1 (permanent) knowledge: the brand DNA loaded at the start of every cycle."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1)
    horizon: Literal[Horizon.H1] = Horizon.H1
    brand_dna: str
    target_audience: str
    positioning: str
    products: List[Product] = Field(default_factory=list)
    restrictions: List[str] = Field(default_factory=list)
    tone_of_voice: str


class Opportunity(BaseModel):
    """Market input (trend, seasonality, community signal or performance data)."""

    model_config = ConfigDict(frozen=True)

    opportunity_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    taxonomy: OpportunityType
    title: str
    description: str = ""
    source: str = "mock"
    priority_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    collected_at: str = Field(default_factory=utc_now_iso)


class DecisionAlternative(BaseModel):
    """One option evaluated by the AI CMO before committing to a decision."""

    model_config = ConfigDict(frozen=True)

    option: str
    expected_performance: float = Field(ge=0.0, le=1.0)
    strategic_capital: float = Field(ge=0.0, le=1.0)
    selected: bool = False
    rejection_reason: Optional[str] = None


class Decision(BaseModel):
    """The ledger entry of an AI CMO choice — content is a consequence of this."""

    model_config = ConfigDict(frozen=True)

    decision_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    opportunity_id: Optional[str] = None
    primary_objective: str
    horizons: List[Horizon]
    alternatives: List[DecisionAlternative] = Field(default_factory=list)
    expected_performance_score: float = Field(ge=0.0, le=1.0)
    strategic_capital_score: float = Field(ge=0.0, le=1.0)
    framework: str
    rationale: str
    slot: Optional[str] = None
    content_format: ContentFormat
    created_at: str = Field(default_factory=utc_now_iso)


class CalendarSlot(BaseModel):
    model_config = ConfigDict(frozen=True)

    slot_id: str = Field(default_factory=new_id)
    weekday: str
    time: str
    content_format: ContentFormat
    objective: str = ""
    decision_id: Optional[str] = None


class EditorialCalendar(BaseModel):
    model_config = ConfigDict(frozen=True)

    calendar_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    week: str  # ISO week label, e.g. "2026-W28"
    slots: List[CalendarSlot] = Field(default_factory=list)


class CarouselSlide(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=1)
    title: str
    body: str


class ReelScript(BaseModel):
    model_config = ConfigDict(frozen=True)

    hook_3s: str
    lines: List[str] = Field(default_factory=list)
    cta: Optional[str] = None


class ContentArtifact(BaseModel):
    """Final executable artifact: slide-by-slide script (Carousel) or hook + lines (Reel)."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    decision_id: str
    format: ContentFormat
    caption: Optional[str] = None
    slides: Optional[List[CarouselSlide]] = None
    reel_script: Optional[ReelScript] = None
    created_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def _payload_matches_format(self) -> "ContentArtifact":
        if self.format is ContentFormat.REEL:
            if self.reel_script is None:
                raise ValueError("REEL artifact requires a reel_script.")
            if self.slides:
                raise ValueError("REEL artifact must not carry carousel slides.")
        else:  # CAROUSEL
            if not self.slides:
                raise ValueError("CAROUSEL artifact requires at least one slide.")
            if self.reel_script is not None:
                raise ValueError("CAROUSEL artifact must not carry a reel script.")
        return self


class Observation(BaseModel):
    """Cold post-publication metrics. No interpretation, just facts."""

    model_config = ConfigDict(frozen=True)

    observation_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    artifact_id: str
    views: int = Field(ge=0)
    saves: int = Field(ge=0)
    shares: int = Field(ge=0)
    retention_rate: float = Field(ge=0.0, le=1.0)
    collected_at: str = Field(default_factory=utc_now_iso)


class Experiment(BaseModel):
    """Retrospective A/B statistical test evaluated by the LearningEngine."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    hypothesis: str
    independent_variable: str
    dependent_variable: str
    group_a: List[float] = Field(default_factory=list)
    group_b: List[float] = Field(default_factory=list)
    lift: Optional[float] = None
    p_value: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: ExperimentStatus = ExperimentStatus.PENDING


class Insight(BaseModel):
    """Derived learning. LOCAL belongs to a tenant; GLOBAL must be anonymized."""

    model_config = ConfigDict(frozen=True)

    insight_id: str = Field(default_factory=new_id)
    scope: InsightScope
    tenant_id: Optional[str] = None
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_experiment_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def _enforce_tenant_firewall(self) -> "Insight":
        if self.scope is InsightScope.GLOBAL and self.tenant_id is not None:
            raise ValueError(
                "GLOBAL insights must be anonymized: tenant_id is not allowed "
                "to cross the tenant firewall."
            )
        if self.scope is InsightScope.LOCAL and not self.tenant_id:
            raise ValueError("LOCAL insights must belong to a tenant.")
        return self


# ---------------------------------------------------------------------------
# Event Sourcing schema
# ---------------------------------------------------------------------------

class EventTelemetry(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_time_ms: float = Field(ge=0.0)
    status: EventStatus
    tokens_used: Optional[int] = Field(default=None, ge=0)
    error_message: Optional[str] = None


class StateEvent(BaseModel):
    """One immutable entry of the Event Sourcing ledger (see spec §4)."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=new_id)
    module: str
    timestamp: str = Field(default_factory=utc_now_iso)
    action: str
    entity: str
    entity_id: str
    changes: Dict[str, Any] = Field(default_factory=dict)
    telemetry: EventTelemetry


# ---------------------------------------------------------------------------
# The shared, immutable-per-cycle pipeline state
# ---------------------------------------------------------------------------

class MarketingState(BaseModel):
    """Single source of truth flowing through every layer of the pipeline.

    Modules receive a state and return a *new* state derived via
    :meth:`apply`; direct attribute assignment is rejected (frozen model).
    """

    model_config = ConfigDict(frozen=True)

    pipeline_id: str = Field(default_factory=new_id)
    tenant_id: str = Field(min_length=1)
    started_at: str = Field(default_factory=utc_now_iso)

    brand_context: Optional[BrandContext] = None
    opportunities: Tuple[Opportunity, ...] = ()
    decisions: Tuple[Decision, ...] = ()
    calendar: Optional[EditorialCalendar] = None
    artifacts: Tuple[ContentArtifact, ...] = ()
    observations: Tuple[Observation, ...] = ()
    experiments: Tuple[Experiment, ...] = ()
    insights: Tuple[Insight, ...] = ()

    events: Tuple[StateEvent, ...] = ()

    def apply(self, event: StateEvent, **updates: Any) -> "MarketingState":
        """Derive a new state: apply field updates and append the event atomically."""
        updates["events"] = self.events + (event,)
        return self.model_copy(update=updates)

    @property
    def last_decision(self) -> Optional[Decision]:
        return self.decisions[-1] if self.decisions else None

    @property
    def last_artifact(self) -> Optional[ContentArtifact]:
        return self.artifacts[-1] if self.artifacts else None
