"""Read-Only Acquisition and Transport Layer for OpportunityOS.

Enforces source authorization, policy constraints, rate limits, and network safety.
Provides injectable MockTransport for offline CI determinism.
"""
from __future__ import annotations

import abc
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from .registry import SourceRegistry


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    body: str
    latency_ms: int
    headers: tuple[tuple[str, str], ...] = ()
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    source_id: str
    url: str
    method: str
    response: TransportResponse
    feed_checksum: str
    authorized: bool
    refusal_reason: str | None = None


class BaseTransport(abc.ABC):
    @abc.abstractmethod
    def fetch(
        self,
        source_id: str,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 10.0,
    ) -> TransportResponse:
        raise NotImplementedError


class MockTransport(BaseTransport):
    """Deterministic, offline injectable transport for testing and CI."""

    def __init__(self, responses: Mapping[str, TransportResponse | str] | None = None) -> None:
        self._responses: dict[str, TransportResponse] = {}
        if responses:
            for key, val in responses.items():
                if isinstance(val, str):
                    self._responses[key] = TransportResponse(
                        status_code=200,
                        body=val,
                        latency_ms=15,
                    )
                else:
                    self._responses[key] = val

    def set_response(self, source_id_or_url: str, response: TransportResponse | str) -> None:
        if isinstance(response, str):
            self._responses[source_id_or_url] = TransportResponse(
                status_code=200,
                body=response,
                latency_ms=10,
            )
        else:
            self._responses[source_id_or_url] = response

    def fetch(
        self,
        source_id: str,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 10.0,
    ) -> TransportResponse:
        # Match by source_id first, then url
        if source_id in self._responses:
            return self._responses[source_id]
        if url in self._responses:
            return self._responses[url]

        return TransportResponse(
            status_code=404,
            body="",
            latency_ms=0,
            error_message=f"MockTransport: No configured response for '{source_id}' ({url})",
        )


class HttpTransport(BaseTransport):
    """Standard library urllib transport with strict read-only semantics."""

    def __init__(self, user_agent: str = "OpportunityOS-Recon/1.0 (+https://github.com/m7mdehab/opportunityos)") -> None:
        self.user_agent = user_agent

    def fetch(
        self,
        source_id: str,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 10.0,
    ) -> TransportResponse:
        method_upper = method.upper()
        if method_upper in {"PUT", "PATCH", "DELETE"}:
            return TransportResponse(
                status_code=405,
                body="",
                latency_ms=0,
                error_message=f"Forbidden method: {method_upper}",
            )

        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, application/xml, text/xml, text/html, */*",
        }
        if headers:
            req_headers.update(headers)

        data_bytes: bytes | None = None
        if body is not None and method_upper == "POST":
            data_bytes = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url=url,
            data=data_bytes,
            headers=req_headers,
            method=method_upper,
        )

        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw_bytes = resp.read()
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                body_str = raw_bytes.decode("utf-8", errors="replace")
                status = getattr(resp, "status", 200)
                resp_headers = tuple((k, str(v)) for k, v in resp.headers.items())
                return TransportResponse(
                    status_code=status,
                    body=body_str,
                    latency_ms=latency_ms,
                    headers=resp_headers,
                )
        except urllib.error.HTTPError as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            return TransportResponse(
                status_code=e.code,
                body=err_body,
                latency_ms=latency_ms,
                error_message=f"HTTP {e.code}: {e.reason}",
            )
        except urllib.error.URLError as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return TransportResponse(
                status_code=504 if "timeout" in str(e.reason).lower() else 502,
                body="",
                latency_ms=latency_ms,
                error_message=f"Network error: {e.reason}",
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return TransportResponse(
                status_code=500,
                body="",
                latency_ms=latency_ms,
                error_message=f"Transport failure: {str(e)}",
            )


class AcquisitionService:
    """Central acquisition service that validates registry authority before execution."""

    def __init__(
        self,
        registry: SourceRegistry | None = None,
        transport: BaseTransport | None = None,
    ) -> None:
        self.registry = registry or SourceRegistry()
        self.transport = transport or MockTransport()

    def acquire(
        self,
        source_id: str,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 10.0,
    ) -> AcquisitionResult:
        # Pre-flight authorization check
        authorized, reason = self.registry.validate_preflight(source_id, url, method)
        if not authorized:
            return AcquisitionResult(
                source_id=source_id,
                url=url,
                method=method,
                response=TransportResponse(
                    status_code=403,
                    body="",
                    latency_ms=0,
                    error_message=reason,
                ),
                feed_checksum="",
                authorized=False,
                refusal_reason=reason,
            )

        # Execute transport
        response = self.transport.fetch(
            source_id=source_id,
            url=url,
            method=method,
            body=body,
            headers=headers,
            timeout_s=timeout_s,
        )

        feed_checksum = hashlib.sha256(response.body.encode("utf-8")).hexdigest() if response.body else ""

        return AcquisitionResult(
            source_id=source_id,
            url=url,
            method=method,
            response=response,
            feed_checksum=feed_checksum,
            authorized=True,
        )
