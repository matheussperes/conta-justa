"""Decorator-based plugin registry.

Output channels are extensions ("Plugin-Based Execution" principle): the
core never imports a concrete channel. Plugins self-register at import
time via ``@register_plugin`` and the orchestrator resolves them by
channel/name or by the content format they are able to execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from src.core.base_module import BaseMarketingModule
from src.core.state import ContentFormat


@dataclass(frozen=True)
class PluginRecord:
    channel: str
    name: str
    module_cls: Type[BaseMarketingModule]
    formats: Tuple[ContentFormat, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class PluginRegistry:
    """In-memory catalog of channel plugins, keyed by (channel, name)."""

    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str], PluginRecord] = {}

    def register(
        self,
        module_cls: Type[BaseMarketingModule],
        *,
        channel: str,
        name: str,
        formats: Tuple[ContentFormat, ...] = (),
        **metadata: Any,
    ) -> None:
        if not (isinstance(module_cls, type) and issubclass(module_cls, BaseMarketingModule)):
            raise TypeError(
                f"Plugin '{channel}/{name}' must subclass BaseMarketingModule."
            )
        key = (channel, name)
        if key in self._records:
            raise ValueError(f"Plugin '{channel}/{name}' is already registered.")
        self._records[key] = PluginRecord(
            channel=channel,
            name=name,
            module_cls=module_cls,
            formats=tuple(formats),
            metadata=dict(metadata),
        )

    def get(self, channel: str, name: str) -> Type[BaseMarketingModule]:
        try:
            return self._records[(channel, name)].module_cls
        except KeyError:
            raise KeyError(f"No plugin registered as '{channel}/{name}'.") from None

    def resolve_by_format(
        self, channel: str, content_format: ContentFormat
    ) -> Type[BaseMarketingModule]:
        """Route execution to the specialist that handles the given format."""
        for record in self._records.values():
            if record.channel == channel and content_format in record.formats:
                return record.module_cls
        raise KeyError(
            f"No '{channel}' specialist registered for format '{content_format.value}'."
        )

    def list(self, channel: Optional[str] = None) -> List[PluginRecord]:
        return [
            record
            for record in self._records.values()
            if channel is None or record.channel == channel
        ]

    def clear(self) -> None:
        """Test helper: wipe all registrations."""
        self._records.clear()


#: Process-wide registry used by the ``@register_plugin`` decorator.
registry = PluginRegistry()


def register_plugin(
    *,
    channel: str,
    name: str,
    formats: Tuple[ContentFormat, ...] = (),
    **metadata: Any,
):
    """Class decorator that registers a ``BaseMarketingModule`` as a plugin."""

    def decorator(cls: Type[BaseMarketingModule]) -> Type[BaseMarketingModule]:
        registry.register(cls, channel=channel, name=name, formats=formats, **metadata)
        return cls

    return decorator
