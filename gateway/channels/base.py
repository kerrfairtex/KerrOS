"""
gateway/channels/base.py
========================
Channel adapter protocol for KerrOS gateway (ADR-066).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class InboundMessage:
    channel: str
    sender: str
    text: str
    chat_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    channel: str
    chat_id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(Protocol):
    name: str

    def status(self) -> dict[str, Any]: ...
    def start(self) -> dict[str, Any]: ...
    def stop(self) -> dict[str, Any]: ...
    def poll(self) -> list[InboundMessage]: ...
    def send(self, msg: OutboundMessage) -> dict[str, Any]: ...
