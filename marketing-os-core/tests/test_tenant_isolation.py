"""Architecture tests: the logical tenant firewall must never leak raw data."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.base_module import (
    BaseMarketingModule,
    TenantIsolationError,
)
from src.core.state import Insight, InsightScope, MarketingState
from src.infrastructure.json_repository import JsonRepository


@pytest.fixture
def repo(tmp_path) -> JsonRepository:
    return JsonRepository(tmp_path)


class TestRepositoryFirewall:
    def test_tenant_data_stays_in_its_sandbox(self, repo, tmp_path):
        repo.write("tenant_a", "brand_context", {"tenant_id": "tenant_a"})
        assert (tmp_path / "tenants" / "tenant_a" / "brand_context.json").exists()
        # Another tenant sees nothing.
        assert repo.read("tenant_b", "brand_context") is None
        assert repo.read("tenant_b", "brand_context", default={}) == {}

    @pytest.mark.parametrize(
        "malicious_id",
        ["../tenant_b", "..", "tenant_a/..", "a/b", "/etc", "tenant a", "", "a\\b"],
    )
    def test_path_traversal_is_blocked(self, repo, malicious_id):
        with pytest.raises(TenantIsolationError):
            repo.read(malicious_id, "brand_context")
        with pytest.raises(TenantIsolationError):
            repo.write(malicious_id, "brand_context", {})

    def test_malicious_collection_name_is_blocked(self, repo):
        with pytest.raises(TenantIsolationError):
            repo.read("tenant_a", "../../global_engine_knowledge/global_insights")

    def test_global_write_rejects_raw_tenant_identifiers(self, repo):
        with pytest.raises(TenantIsolationError):
            repo.append_global("global_insights", {"rule": "x", "tenant_id": "tenant_a"})

    def test_global_write_rejects_nested_tenant_identifiers(self, repo):
        record = {"rule": "x", "evidence": [{"payload": {"tenant_id": "tenant_a"}}]}
        with pytest.raises(TenantIsolationError):
            repo.append_global("global_insights", record)

    def test_global_write_accepts_anonymized_payload(self, repo):
        record = {"variable": "explicit_save_cta", "lift": 0.45, "p_value": 0.001}
        repo.append_global("global_insights", record)
        assert repo.read_global("global_insights") == [record]


class RescopingModule(BaseMarketingModule):
    """Malicious/buggy module trying to move the state to another tenant."""

    def process(self, state: MarketingState) -> MarketingState:
        return state.model_copy(update={"tenant_id": "tenant_b"})


class TestPipelineFirewall:
    def test_module_cannot_rescope_state_to_another_tenant(self):
        state = MarketingState(tenant_id="tenant_a")
        with pytest.raises(TenantIsolationError):
            RescopingModule().execute(state)


class TestInsightFirewall:
    def test_global_insight_must_be_anonymized(self):
        with pytest.raises(ValidationError):
            Insight(
                scope=InsightScope.GLOBAL,
                tenant_id="tenant_a",
                statement="leaky rule",
                confidence=0.9,
            )

    def test_local_insight_requires_a_tenant(self):
        with pytest.raises(ValidationError):
            Insight(scope=InsightScope.LOCAL, statement="orphan rule", confidence=0.9)

    def test_valid_scopes_pass(self):
        Insight(scope=InsightScope.GLOBAL, statement="abstract rule", confidence=0.9)
        Insight(
            scope=InsightScope.LOCAL,
            tenant_id="tenant_a",
            statement="tenant rule",
            confidence=0.9,
        )
