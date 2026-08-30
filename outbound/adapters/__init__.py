"""Outbound Action Adapters for ATS and Procurement Platforms."""
from __future__ import annotations

from .base import BaseOutboundAdapter
from .greenhouse_outbound import GreenhouseOutboundAdapter
from .lever_outbound import LeverOutboundAdapter
from .ashby_outbound import AshbyOutboundAdapter
from .generic_form import GenericFormOutboundAdapter
from .procurement_package import ProcurementPackageAdapter
from .freelance_proposal import FreelanceProposalAdapter

__all__ = [
    "BaseOutboundAdapter",
    "GreenhouseOutboundAdapter",
    "LeverOutboundAdapter",
    "AshbyOutboundAdapter",
    "GenericFormOutboundAdapter",
    "ProcurementPackageAdapter",
    "FreelanceProposalAdapter",
]
