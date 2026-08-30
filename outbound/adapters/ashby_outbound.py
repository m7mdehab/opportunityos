"""Ashby Outbound Job Application Adapter."""
from __future__ import annotations

from .base import BaseOutboundAdapter
from ..models import AdapterLifecycleState


class AshbyOutboundAdapter(BaseOutboundAdapter):
    def __init__(self, lifecycle_state: AdapterLifecycleState = AdapterLifecycleState.ASSISTED_VERIFIED) -> None:
        super().__init__(name="ashby", version="1.0.0", lifecycle_state=lifecycle_state)
