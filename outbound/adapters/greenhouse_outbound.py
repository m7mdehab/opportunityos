"""Greenhouse Outbound Job Application Adapter."""
from __future__ import annotations

from .base import BaseOutboundAdapter
from ..models import AdapterLifecycleState


class GreenhouseOutboundAdapter(BaseOutboundAdapter):
    def __init__(self, lifecycle_state: AdapterLifecycleState = AdapterLifecycleState.SUBMIT_ELIGIBLE) -> None:
        super().__init__(name="greenhouse", version="1.0.0", lifecycle_state=lifecycle_state)
