"""OpportunityOS Feed Adapters Registry."""
from __future__ import annotations

from typing import Iterable

from opportunity.adapters.base import BaseAdapter
from opportunity.adapters.eu_ted import EUTEDAdapter
from opportunity.adapters.greenhouse import GreenhouseAdapter
from opportunity.adapters.hacker_news import HackerNewsWhoIsHiringAdapter
from opportunity.adapters.himalayas import HimalayasAdapter
from opportunity.adapters.lever import LeverAdapter
from opportunity.adapters.remote_ok import RemoteOKAdapter
from opportunity.adapters.remotive import RemotiveAdapter
from opportunity.adapters.ungm import UNGMAdapter
from opportunity.adapters.we_work_remotely import WeWorkRemotelyAdapter
from opportunity.adapters.world_bank import WorldBankAdapter

# Standard employment ATS watchlists
STANDARD_GREENHOUSE_COMPANIES = (
    "cloudflare",
    "datadog",
    "duolingo",
    "figma",
    "flexport",
    "coinbase",
    "stripe",
    "twilio",
    "airbnb",
    "affirm",
)

STANDARD_LEVER_COMPANIES = (
    "shyftlabs",
    "ryz_labs",
)


def get_all_standard_adapters() -> list[BaseAdapter]:
    """Return all active, permitted standard adapters across employment and procurement tracks."""
    adapters: list[BaseAdapter] = [
        HimalayasAdapter(),
        RemotiveAdapter(),
        RemoteOKAdapter(),
        WeWorkRemotelyAdapter(),
        UNGMAdapter(),
        WorldBankAdapter(),
        EUTEDAdapter(),
        HackerNewsWhoIsHiringAdapter(),
    ]
    for company in STANDARD_GREENHOUSE_COMPANIES:
        adapters.append(GreenhouseAdapter(company))
    for company in STANDARD_LEVER_COMPANIES:
        adapters.append(LeverAdapter(company))
    return adapters


__all__ = [
    "BaseAdapter",
    "GreenhouseAdapter",
    "LeverAdapter",
    "HackerNewsWhoIsHiringAdapter",
    "HimalayasAdapter",
    "RemotiveAdapter",
    "RemoteOKAdapter",
    "WeWorkRemotelyAdapter",
    "UNGMAdapter",
    "WorldBankAdapter",
    "EUTEDAdapter",
    "get_all_standard_adapters",
]
