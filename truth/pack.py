"""Loading and pack-level validation reporting for founder truth packs.

This module wraps `truth.ingest.load_path` with:

- a stable content hash (`truth_pack_hash`) over a canonical JSON
  serialisation of the loaded graph, and
- a pack-level validation report describing what the loader actually
  checked while building the graph.

What "pack-level validation" honestly means here
--------------------------------------------------
`truth.validator.ClaimValidator` validates a specific *claim candidate*
against a graph (does this claim text hold up against the evidence graph);
it has no notion of validating a whole document. There is no meaningful
"run ClaimValidator over the pack" operation, so this module does not call
it, and does not claim to.

Loading *is* the validation that applies to a whole pack: `truth.ingest`
and `truth.graph.TruthGraph` perform, inline, as the graph is built:

- schema conformance (required/unknown top-level and nested fields,
  per `truth.ingest._validate_keys`);
- type and enum coercion (dates, enums, numeric bounds);
- evidence-reference integrity -- every `evidence_ids` entry anywhere in
  the document (evidence, assertions, relations, metrics, profile
  entities) must resolve to a known evidence record, or the graph
  constructor raises before returning;
- profile invariants (no duplicate entity ids, red-line regex patterns
  must compile, target/excluded industries must not overlap); and
- evidence-supported field provenance -- most profile field values must be
  textually supported by the evidence records that back them.

A successful `load_path` call is therefore already a pass of every check
above; there is nothing further and honest left for this module to
re-run. `load_founder_pack` treats a successful load as a valid pack and
reports per-section presence/counts for completeness. It performs no
additional, undocumented validation, and it never logs pack contents --
only counts and section names.

Note on assertions/relations/metrics counts: `TruthGraph` automatically
projects each profile's material fields into its internal assertions,
relations, and metrics collections when a profile is added
(`_project_profile_assertions`). The `assertions`/`relations`/`metrics`
section counts in `PackValidationReport` therefore reflect the graph's
full collections -- explicit top-level entries plus everything
auto-projected from `career_profile`/`capability_profile` -- not only
what a founder wrote under those three top-level YAML keys. A pack with
`assertions: []` in its source file can still report a non-zero
`assertions` count.
"""

from __future__ import annotations

import hashlib
import json
import logging
import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .graph import TruthGraph
from .ingest import IngestionError, load_path
from .models import CapabilityProfile, CareerProfile

logger = logging.getLogger(__name__)

#: Default location of the founder's truth pack. Never read at import time;
#: only used as the default argument to `load_founder_pack`.
DEFAULT_TRUTH_PACK_PATH = Path("private/truth_pack.yaml")

_CAREER_LIST_FIELDS = (
    "employment", "education", "certifications", "skills", "languages",
    "work_authorizations", "approved_summaries", "red_lines", "never_claims",
)
_CAPABILITY_LIST_FIELDS = (
    "services", "portfolio", "target_industries", "excluded_industries",
    "delivery_languages", "tools", "red_lines", "never_claims",
)


class TruthPackMissing(FileNotFoundError):
    """Raised when no file exists at the requested truth pack path."""


class TruthPackInvalid(ValueError):
    """Raised when a truth pack fails to load or fails graph construction.

    `findings` carries the validator/ingestion findings that explain the
    failure. Ingestion fails fast on the first problem it encounters, so
    `findings` will typically contain a single message, not an exhaustive
    list of every problem in the document.
    """

    def __init__(self, message: str, findings: tuple[str, ...]) -> None:
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True, slots=True)
class PackValidationReport:
    """An honest, structural pack-level report. See module docstring for
    exactly what is and is not checked."""

    valid: bool
    section_counts: tuple[tuple[str, int], ...]
    findings: tuple[str, ...] = ()

    def empty_sections(self) -> tuple[str, ...]:
        """Section names present in the schema with zero entries."""
        return tuple(name for name, count in self.section_counts if count == 0)


@dataclass(frozen=True, slots=True)
class LoadedPack:
    """The result of successfully loading a founder truth pack."""

    graph: TruthGraph
    report: PackValidationReport
    truth_pack_hash: str


def _profile_of_type(graph: TruthGraph, cls: type) -> Any | None:
    for profile in graph.profiles.values():
        if isinstance(profile, cls):
            return profile
    return None


def _section_counts(graph: TruthGraph) -> dict[str, int]:
    counts: dict[str, int] = {
        "evidence": len(graph.evidence_records),
        "assertions": len(graph.assertions),
        "relations": len(graph.relations),
        "metrics": len(graph.metrics),
    }

    career = _profile_of_type(graph, CareerProfile)
    counts["career_profile"] = 1 if career is not None else 0
    for name in _CAREER_LIST_FIELDS:
        counts[f"career_profile.{name}"] = len(getattr(career, name)) if career is not None else 0

    capability = _profile_of_type(graph, CapabilityProfile)
    counts["capability_profile"] = 1 if capability is not None else 0
    for name in _CAPABILITY_LIST_FIELDS:
        counts[f"capability_profile.{name}"] = len(getattr(capability, name)) if capability is not None else 0
    counts["capability_profile.capacity"] = (
        1 if (capability is not None and capability.capacity is not None) else 0
    )
    return counts


def _build_report(graph: TruthGraph) -> PackValidationReport:
    counts = _section_counts(graph)
    return PackValidationReport(valid=True, section_counts=tuple(sorted(counts.items())), findings=())


def _to_plain(value: Any) -> Any:
    """Recursively convert a (possibly frozen/slotted) dataclass graph node
    into plain, JSON-serialisable Python values, without relying on
    `dataclasses.asdict`/`copy.deepcopy` (which cannot copy the immutable
    `mappingproxy` metadata some records carry)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_plain(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_plain(item) for item in value]
    return value


def _graph_to_canonical_dict(graph: TruthGraph) -> dict[str, Any]:
    return {
        "evidence": [_to_plain(graph.evidence_records[key]) for key in sorted(graph.evidence_records)],
        "assertions": [_to_plain(graph.assertions[key]) for key in sorted(graph.assertions)],
        "relations": [_to_plain(graph.relations[key]) for key in sorted(graph.relations)],
        "metrics": [_to_plain(graph.metrics[key]) for key in sorted(graph.metrics)],
        "profiles": [_to_plain(graph.profiles[key]) for key in sorted(graph.profiles)],
    }


def compute_truth_pack_hash(graph: TruthGraph) -> str:
    """Sha256 of a canonical JSON serialisation of `graph`.

    Stable across dict-key ordering and across repeated loads of the same
    content; changes whenever any substantive graph content changes.
    """
    canonical = _graph_to_canonical_dict(graph)
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_founder_pack(path: str | Path | None = None) -> LoadedPack:
    """Load, hash, and report on a founder truth pack.

    `path` defaults to `DEFAULT_TRUTH_PACK_PATH` (private/truth_pack.yaml).
    Never logs pack contents -- only counts and section names.
    """
    target = Path(path) if path is not None else DEFAULT_TRUTH_PACK_PATH

    if not target.exists():
        raise TruthPackMissing(f"truth pack not found at {target}")

    try:
        graph = load_path(target)
    except (IngestionError, ValueError) as error:
        message = str(error)
        raise TruthPackInvalid(f"truth pack failed to load: {message}", (message,)) from error

    report = _build_report(graph)
    digest = compute_truth_pack_hash(graph)

    logger.info(
        "truth pack loaded: sections=%s",
        sorted(name for name, count in report.section_counts if count > 0),
    )

    return LoadedPack(graph=graph, report=report, truth_pack_hash=digest)
