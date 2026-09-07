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


def get_all_standard_adapters(registry: Any = None) -> list[BaseAdapter]:
    """Return all active, permitted standard adapters across employment and procurement tracks.

    Derives Greenhouse and Lever adapters dynamically from the read-allowed entries in
    SourceRegistry (Council #4, finding 12; BRIEF-FR-006 next-prerequisites) while preserving
    the standard baseline adapters.
    """
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
    seen_sources = {a.source_id for a in adapters}

    try:
        from opportunity.registry import SourceRegistry
        reg = registry if isinstance(registry, SourceRegistry) else SourceRegistry()
        for source_id, policy in reg._sources.items():
            if not policy.read_allowed:
                continue
            if source_id.startswith("greenhouse:") and source_id not in seen_sources:
                company = source_id.partition(":")[2]
                adapters.append(GreenhouseAdapter(company))
                seen_sources.add(source_id)
            elif source_id.startswith("lever:") and source_id not in seen_sources:
                company = source_id.partition(":")[2]
                adapters.append(LeverAdapter(company))
                seen_sources.add(source_id)
    except Exception:
        for company in STANDARD_GREENHOUSE_COMPANIES:
            sid = f"greenhouse:{company}"
            if sid not in seen_sources:
                adapters.append(GreenhouseAdapter(company))
                seen_sources.add(sid)
        for company in STANDARD_LEVER_COMPANIES:
            sid = f"lever:{company}"
            if sid not in seen_sources:
                adapters.append(LeverAdapter(company))
                seen_sources.add(sid)

    for company in STANDARD_GREENHOUSE_COMPANIES:
        sid = f"greenhouse:{company}"
        if sid not in seen_sources:
            adapters.append(GreenhouseAdapter(company))
            seen_sources.add(sid)
    for company in STANDARD_LEVER_COMPANIES:
        sid = f"lever:{company}"
        if sid not in seen_sources:
            adapters.append(LeverAdapter(company))
            seen_sources.add(sid)

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
