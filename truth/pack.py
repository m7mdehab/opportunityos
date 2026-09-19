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

import base64
import gzip
import hashlib
import json
import logging
import ipaddress
import os
import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import unquote_to_bytes, urlsplit
from urllib.request import Request, urlopen

from .graph import TruthGraph
from .ingest import IngestionError, load_document, load_path
from .models import CapabilityProfile, CareerProfile

logger = logging.getLogger(__name__)

#: Default location of the founder's truth pack. Never read at import time;
#: only used as the default argument to `load_founder_pack`.
DEFAULT_TRUTH_PACK_PATH = Path("private/truth_pack.yaml")
CANONICAL_REPO_TRUTH_PACK = Path("founder/truth_pack.yaml.gz.b64")
CANONICAL_REPO_TRUTH_PACK_RAW_SHA256 = "7c5de5ad8f7f43af505aed79d7e081b6dca0bd820edcecfe4393971fb15d9869"

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

    def __init__(self, message: str, findings: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.findings = findings


class TruthPackVerificationError(TruthPackInvalid):
    """Raised when a truth pack's SHA-256 digest does not match the expected hash."""


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


def _redact_url(url: str) -> str:
    """Redact query parameters, fragments, and credentials from a URL.

    Prevents leaking SAS tokens, presigned signatures, or API keys in error
    messages, findings, or logs.
    """
    if not url:
        return ""
    try:
        parsed = urlsplit(str(url))
        if parsed.scheme in ("http", "https", "s3"):
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return f"{parsed.scheme}://{netloc}{parsed.path}"
        elif parsed.scheme == "data":
            meta, _, _ = url[5:].partition(",")
            return f"data:{meta},[redacted]"
        return str(url)
    except Exception:
        return "[redacted-uri]"




def _is_loopback_remote_host(hostname: str | None) -> bool:
    if not hostname:
        return True
    lowered = hostname.lower()
    if lowered in {"localhost", "host.docker.internal"} or lowered.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def _is_supabase_storage_uri(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return host.endswith("supabase.co") or "/storage/v1/object/" in path

def _is_cloud_mode(env: Mapping[str, str] | None = None) -> bool:
    """Return True if running in cloud / production mode."""
    target_env = os.environ if env is None else env
    mode = target_env.get("OPPORTUNITYOS_ENVIRONMENT", "").lower()
    return (
        mode in {"production", "prod", "cloud"}
        or target_env.get("MODE", "").lower() == "cloud"
        or target_env.get("ENVIRONMENT", "").lower() in {"production", "prod", "cloud"}
    )


def _fetch_remote_bytes(
    url: str,
    auth_token: str | None = None,
    api_key: str | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[bytes, str]:
    """Fetch raw bytes and determine format (yaml or json) from an HTTP(S) URL."""
    redacted = _redact_url(url)
    headers = {"User-Agent": "OpportunityOS-TruthPack/1.0"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if api_key:
        headers["apikey"] = api_key

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            raw_bytes = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except HTTPError as err:
        if err.code == 404:
            raise TruthPackMissing(f"truth pack not found at {redacted} (HTTP 404)") from err
        if err.code in (401, 403):
            raise TruthPackInvalid(f"access denied to truth pack at {redacted} (HTTP {err.code})", (f"HTTP {err.code}",)) from err
        raise TruthPackInvalid(f"failed to fetch truth pack from {redacted}: HTTP {err.code}", (f"HTTP {err.code}",)) from err
    except URLError as err:
        # Never surface provider/transport exception text: third-party error
        # strings can echo Authorization headers or query credentials.
        raise TruthPackInvalid(
            f"network error fetching truth pack from {redacted}",
            ("remote Truth Pack network failure",),
        ) from err
    except Exception as err:
        raise TruthPackInvalid(
            f"unexpected error fetching truth pack from {redacted}",
            ("remote Truth Pack transport failure",),
        ) from err

    path_part = urlsplit(url).path.lower()
    if path_part.endswith(".json") or "application/json" in content_type:
        doc_format = "json"
    else:
        doc_format = "yaml"

    return raw_bytes, doc_format


def _fetch_s3_bytes(url: str) -> tuple[bytes, str]:
    """S3 storage is deferred for FR-007; HTTPS object store is the canonical remote mechanism."""
    redacted = _redact_url(url)
    raise TruthPackInvalid(
        f"s3:// storage is deferred for FR-007 ({redacted}); HTTPS object store is the supported remote storage mechanism",
        ("deferred s3 storage",),
    )


def _decode_data_uri(uri: str) -> tuple[bytes, str]:
    """Decode an RFC 2397 data: URI."""
    if not uri.startswith("data:"):
        raise TruthPackInvalid("invalid data URI", ("invalid data URI",))
    meta, _, payload = uri[5:].partition(",")
    is_base64 = meta.endswith(";base64")
    mime = meta[:-7] if is_base64 else meta
    doc_format = "json" if "json" in mime else "yaml"

    if is_base64:
        try:
            raw_bytes = base64.b64decode(payload)
        except Exception as err:
            raise TruthPackInvalid(f"invalid base64 payload in data URI: {err}", (str(err),)) from err
    else:
        raw_bytes = unquote_to_bytes(payload)

    return raw_bytes, doc_format


def load_truth_pack(
    target: str | Path | None = None,
    *,
    expected_hash: str | None = None,
    auth_token: str | None = None,
    api_key: str | None = None,
    timeout_seconds: float = 30.0,
    allow_local_path: bool | None = None,
    allow_data_uri: bool | None = None,
    cloud_mode: bool | None = None,
) -> LoadedPack:
    """Load, verify, hash, and report on a founder truth pack from a local path,
    remote HTTP(S) URL, S3 URI, or data URI.

    Fail-closed on missing pack, invalid schema, network errors, or SHA-256
    integrity hash mismatch.
    """
    if cloud_mode is None:
        cloud_mode = _is_cloud_mode()

    if target is None:
        target = (
            os.environ.get("OPPORTUNITYOS_TRUTH_PACK_URI")
            or os.environ.get("OPPORTUNITYOS_TRUTH_PACK_PATH")
        )
        if not target:
            # Founder decision 2026-09-19: the canonical career Truth Pack is
            # non-sensitive product truth. Hosted/runtime execution therefore
            # uses the repository-managed, hash-bound snapshot by default,
            # while local development keeps the historical private/ path.
            target = CANONICAL_REPO_TRUTH_PACK if cloud_mode else DEFAULT_TRUTH_PACK_PATH

    if expected_hash is None:
        expected_hash = (
            os.environ.get("OPPORTUNITYOS_TRUTH_PACK_HASH")
            or os.environ.get("OPPORTUNITYOS_TRUTH_PACK_SHA256")
        )
        if expected_hash is None and str(target).strip() == CANONICAL_REPO_TRUTH_PACK.as_posix():
            expected_hash = CANONICAL_REPO_TRUTH_PACK_RAW_SHA256

    if auth_token is None:
        auth_token = os.environ.get("OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN")
    if api_key is None:
        api_key = os.environ.get("OPPORTUNITYOS_TRUTH_PACK_API_KEY")

    target_str = str(target).strip()
    if not target_str:
        raise TruthPackMissing("empty truth pack target specified")

    redacted_target = _redact_url(target_str)

    # Cloud mode transport & security constraints (Items B, D, E)
    if cloud_mode:
        repo_snapshot_target = target_str == CANONICAL_REPO_TRUTH_PACK.as_posix()
        if expected_hash is None and not repo_snapshot_target:
            raise TruthPackInvalid(
                f"expected_hash is required in cloud mode for integrity verification ({redacted_target})",
                ("missing expected_hash in cloud mode",),
            )
        if target_str.startswith("http://"):
            raise TruthPackInvalid(
                f"plain http:// is forbidden in cloud mode; HTTPS required ({redacted_target})",
                ("insecure http transport in cloud mode",),
            )
        if target_str.startswith("https://"):
            parsed = urlsplit(target_str)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise TruthPackInvalid(
                    f"Truth Pack URI must not contain credentials, query, or fragment in cloud mode ({redacted_target})",
                    ("credential-bearing or signed URL forbidden in cloud mode",),
                )
            if _is_loopback_remote_host(parsed.hostname):
                raise TruthPackInvalid(
                    f"localhost/loopback Truth Pack endpoint is forbidden in cloud mode ({redacted_target})",
                    ("loopback remote endpoint forbidden",),
                )
            is_supabase = _is_supabase_storage_uri(target_str)
            if "/object/public/" in parsed.path.lower():
                raise TruthPackInvalid(
                    f"public Supabase Storage object endpoint is forbidden in cloud mode ({redacted_target})",
                    ("public object endpoint forbidden",),
                )
            if is_supabase and (not auth_token or not api_key):
                raise TruthPackInvalid(
                    "Supabase Storage Truth Pack access requires both auth token and API key",
                    ("missing Supabase private storage credentials",),
                )
            if not auth_token:
                raise TruthPackInvalid(
                    "private HTTPS Truth Pack access requires OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN",
                    ("missing private Truth Pack auth token",),
                )
        if target_str.startswith("data:") and not allow_data_uri:
            raise TruthPackInvalid(
                "data: URI is development/test fixture only and not accepted as production remote storage in cloud mode",
                ("data URI forbidden in cloud mode",),
            )

    if target_str.startswith("http://") or target_str.startswith("https://"):
        raw_bytes, doc_format = _fetch_remote_bytes(
            target_str, auth_token=auth_token, api_key=api_key, timeout_seconds=timeout_seconds
        )
    elif target_str.startswith("s3://"):
        raw_bytes, doc_format = _fetch_s3_bytes(target_str)
    elif target_str.startswith("data:"):
        raw_bytes, doc_format = _decode_data_uri(target_str)
    else:
        # Local path check. Arbitrary cloud-local paths stay forbidden; the
        # one repository-managed canonical snapshot is explicitly allowed.
        local_allowed = allow_local_path if allow_local_path is not None else (not cloud_mode)
        file_path = Path(target_str)
        # Founder decision 2026-09-19: the canonical career Truth Pack is
        # non-sensitive product truth and is allowed to ship with the
        # repository. Cloud mode may read exactly this repository-managed
        # snapshot; arbitrary local-path fallback remains forbidden.
        repo_snapshot = file_path.as_posix() == CANONICAL_REPO_TRUTH_PACK.as_posix()
        if cloud_mode and repo_snapshot:
            local_allowed = True
        if not local_allowed:
            raise TruthPackInvalid(
                f"local filesystem paths not allowed for truth pack in cloud mode: {redacted_target}",
                ("forbidden local path in cloud mode",),
            )
        if not file_path.exists():
            raise TruthPackMissing(f"truth pack not found at {file_path}")
        try:
            raw_bytes = file_path.read_bytes()
        except OSError as err:
            raise TruthPackInvalid(f"failed reading truth pack at {file_path}: {err}", (str(err),)) from err
        if file_path.name.endswith(".yaml.gz.b64"):
            try:
                raw_bytes = gzip.decompress(base64.b64decode(raw_bytes, validate=True))
            except Exception as err:
                raise TruthPackInvalid(
                    f"canonical truth pack snapshot could not be decoded: {file_path}",
                    ("invalid gzip/base64 truth pack snapshot",),
                ) from err
            doc_format = "yaml"
        else:
            doc_format = "json" if file_path.suffix.lower() == ".json" else "yaml"

    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as err:
        raise TruthPackInvalid(f"truth pack is not valid UTF-8: {err}", (str(err),)) from err

    try:
        graph = load_document(raw_text, doc_format)
    except (IngestionError, ValueError) as error:
        message = str(error)
        raise TruthPackInvalid(f"truth pack failed to load: {message}", (message,)) from error

    canonical_hash = compute_truth_pack_hash(graph)

    # Integrity verification against expected_hash (accepts raw content SHA256 or canonical graph hash)
    if expected_hash:
        clean_expected = expected_hash.strip().lower()
        if clean_expected not in (raw_sha256.lower(), canonical_hash.lower()):
            raise TruthPackVerificationError(
                f"truth pack integrity verification failed: expected hash {expected_hash}, "
                f"got raw SHA-256 {raw_sha256} / graph canonical hash {canonical_hash}",
                (f"expected {expected_hash}, got raw {raw_sha256} or graph {canonical_hash}",),
            )

    report = _build_report(graph)

    logger.info(
        "truth pack loaded: sections=%s, canonical_hash=%s",
        sorted(name for name, count in report.section_counts if count > 0),
        canonical_hash,
    )

    return LoadedPack(graph=graph, report=report, truth_pack_hash=canonical_hash)


def load_founder_pack(path: str | Path | None = None) -> LoadedPack:
    """Load, hash, and report on a founder truth pack.

    Local mode defaults to private/truth_pack.yaml for backward compatibility.
    Cloud mode defaults to the Founder-approved, repository-managed canonical
    snapshot because the Founder explicitly classifies the career Truth Pack as
    non-sensitive product truth. Arbitrary cloud-local paths still fail closed.
    Never logs pack contents -- only counts and section names.
    """
    return load_truth_pack(target=path)
