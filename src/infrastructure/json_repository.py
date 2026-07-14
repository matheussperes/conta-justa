"""Local, deterministic JSON-file persistence with a hard tenant firewall.

Layout (relative to ``base_path``)::

    tenants/<tenant_id>/<collection>.json     # tenant plane (raw data)
    global_engine_knowledge/<collection>.json # global plane (anonymized)

Isolation guarantees:

* ``tenant_id`` and ``collection`` are validated against a strict slug
  pattern (blocks path traversal and cross-sandbox addressing).
* Resolved paths are double-checked to stay inside their sandbox.
* Global writes are rejected if the payload contains raw tenant
  identifiers at any nesting depth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from src.core.base_module import TenantIsolationError
from src.infrastructure.repository_interface import MarketingRepository

_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

#: Keys that would leak raw tenant identity into the global plane.
FORBIDDEN_GLOBAL_KEYS = frozenset(
    {"tenant_id", "tenant", "brand_name", "account_id", "handle", "username"}
)


class JsonRepository(MarketingRepository):
    TENANTS_DIR = "tenants"
    GLOBAL_DIR = "global_engine_knowledge"

    def __init__(self, base_path: Path | str) -> None:
        self._base = Path(base_path).resolve()

    # -- tenant plane --------------------------------------------------------

    def read(self, tenant_id: str, collection: str, default: Any = None) -> Any:
        path = self._tenant_file(tenant_id, collection)
        return self._load(path, default)

    def write(self, tenant_id: str, collection: str, payload: Any) -> None:
        path = self._tenant_file(tenant_id, collection)
        self._dump(path, payload)

    def append(self, tenant_id: str, collection: str, record: Dict[str, Any]) -> None:
        data = self.read(tenant_id, collection, default=[])
        if not isinstance(data, list):
            raise TypeError(
                f"Collection '{collection}' of tenant '{tenant_id}' is not appendable."
            )
        data.append(record)
        self.write(tenant_id, collection, data)

    # -- global plane ---------------------------------------------------------

    def read_global(self, collection: str, default: Any = None) -> Any:
        return self._load(self._global_file(collection), default)

    def append_global(self, collection: str, record: Dict[str, Any]) -> None:
        self._assert_anonymized(record)
        path = self._global_file(collection)
        data = self._load(path, default=[])
        if not isinstance(data, list):
            raise TypeError(f"Global collection '{collection}' is not appendable.")
        data.append(record)
        self._dump(path, data)

    # -- firewall helpers -----------------------------------------------------

    def _tenant_file(self, tenant_id: str, collection: str) -> Path:
        self._validate_slug(tenant_id, "tenant_id")
        self._validate_slug(collection, "collection")
        sandbox_root = (self._base / self.TENANTS_DIR).resolve()
        sandbox = (sandbox_root / tenant_id).resolve()
        if sandbox.parent != sandbox_root:
            raise TenantIsolationError(
                f"Tenant '{tenant_id}' resolves outside the tenants sandbox."
            )
        return sandbox / f"{collection}.json"

    def _global_file(self, collection: str) -> Path:
        self._validate_slug(collection, "collection")
        return self._base / self.GLOBAL_DIR / f"{collection}.json"

    @staticmethod
    def _validate_slug(value: str, label: str) -> None:
        if not isinstance(value, str) or not _SLUG_PATTERN.match(value):
            raise TenantIsolationError(
                f"Invalid {label} {value!r}: only [A-Za-z0-9_-] is allowed "
                "(logical firewall violation)."
            )

    @classmethod
    def _assert_anonymized(cls, value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_GLOBAL_KEYS:
                    raise TenantIsolationError(
                        f"Global knowledge payload carries raw tenant field "
                        f"'{key}' at {path} — anonymize before ascending."
                    )
                cls._assert_anonymized(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                cls._assert_anonymized(item, f"{path}[{i}]")

    # -- deterministic file IO --------------------------------------------------

    @staticmethod
    def _load(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _dump(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
