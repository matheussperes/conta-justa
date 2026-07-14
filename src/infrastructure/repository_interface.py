"""Abstract read/write contract for the persistence layer.

Two data planes exist and must never blend:

* **Tenant plane** — raw client data, always addressed by ``tenant_id``
  and confined to that tenant's sandbox (logical firewall).
* **Global plane** — abstract, anonymized engine knowledge. Implementations
  must refuse any global payload that carries raw tenant identifiers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


#: Collections every tenant sandbox exposes in V1.
TENANT_COLLECTIONS = (
    "brand_context",
    "decision_ledger",
    "post_history",
    "local_insights",
)


class MarketingRepository(ABC):
    """Contract for tenant-scoped and global persistence."""

    # -- tenant plane --------------------------------------------------------

    @abstractmethod
    def read(self, tenant_id: str, collection: str, default: Any = None) -> Any:
        """Read a collection from the tenant sandbox; ``default`` when absent."""

    @abstractmethod
    def write(self, tenant_id: str, collection: str, payload: Any) -> None:
        """Overwrite a collection inside the tenant sandbox (deterministic output)."""

    @abstractmethod
    def append(self, tenant_id: str, collection: str, record: Dict[str, Any]) -> None:
        """Append a record to a list-shaped collection inside the tenant sandbox."""

    # -- global plane ---------------------------------------------------------

    @abstractmethod
    def read_global(self, collection: str, default: Any = None) -> Any:
        """Read from the global engine knowledge base."""

    @abstractmethod
    def append_global(self, collection: str, record: Dict[str, Any]) -> None:
        """Append an **anonymized** record to the global engine knowledge base.

        Implementations MUST raise ``TenantIsolationError`` if the record
        carries raw tenant identifiers at any nesting depth.
        """
