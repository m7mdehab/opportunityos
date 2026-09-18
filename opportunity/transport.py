"""Read-Only Acquisition and Transport Layer for OpportunityOS.

Enforces source authorization, exact host/path binding, pacing/rate limits, and network safety.
Provides injectable MockTransport and injectable Clock for offline CI determinism.
"""
from __future__ import annotations

import abc
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .registry import SourceRegistry


@dataclass(frozen=True, slots=True)
class DiscoveryRequest:
    source_id: str
    url: str
    method: str = "GET"
    body: dict[str, Any] | None = None
    headers: tuple[tuple[str, str], ...] = ()
    timeout_s: float = 10.0


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

    @property
    def is_nonempty(self) -> bool:
        return bool(self.body and self.body.strip())


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    source_id: str
    url: str
    method: str
    response: TransportResponse
    feed_checksum: str
    authorized: bool
    refusal_reason: str | None = None


class RateLimiter:
    """Deterministic, injectable per-source rate limiter / pacer."""

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        default_min_interval_s: float = 1.0,
    ) -> None:
        self.clock = clock or time.monotonic
        self.default_min_interval_s = default_min_interval_s
        self._last_request_time: dict[str, float] = {}

    def acquire(self, source_id: str, min_interval_s: float | None = None) -> float:
        """Calculate wait time needed to respect pacing limit."""
        interval = min_interval_s if min_interval_s is not None else self.default_min_interval_s
        now = self.clock()
        last = self._last_request_time.get(source_id, 0.0)
        elapsed = now - last
        wait_needed = max(0.0, interval - elapsed)
        self._last_request_time[source_id] = now + wait_needed
        return wait_needed


class BaseTransport(abc.ABC):
    @abc.abstractmethod
    def fetch(
        self,
        request: DiscoveryRequest,
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
        request: DiscoveryRequest,
    ) -> TransportResponse:
        # Match by source_id first, then url
        if request.source_id in self._responses:
            return self._responses[request.source_id]
        if request.url in self._responses:
            return self._responses[request.url]

        return TransportResponse(
            status_code=404,
            body="",
            latency_ms=0,
            error_message=f"MockTransport: No configured response for '{request.source_id}' ({request.url})",
        )


class HttpTransport(BaseTransport):
    """Standard library urllib transport with strict read-only semantics."""

    def __init__(self, user_agent: str = "OpportunityOS-Recon/1.0 (+https://github.com/m7mdehab/opportunityos)") -> None:
        self.user_agent = user_agent

    def fetch(
        self,
        request: DiscoveryRequest,
    ) -> TransportResponse:
        method_upper = request.method.upper()
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
        if request.headers:
            req_headers.update(dict(request.headers))

        data_bytes: bytes | None = None
        if request.body is not None and method_upper == "POST":
            data_bytes = json.dumps(request.body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url=request.url,
            data=data_bytes,
            headers=req_headers,
            method=method_upper,
        )

        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=request.timeout_s) as resp:
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
            err_headers = tuple((k, str(v)) for k, v in e.headers.items()) if e.headers else ()
            return TransportResponse(
                status_code=e.code,
                body=err_body,
                latency_ms=latency_ms,
                headers=err_headers,
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
    """Central acquisition service that validates registry authority and enforces pacing before execution."""

    def __init__(
        self,
        registry: SourceRegistry | None = None,
        transport: BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.registry = registry or SourceRegistry()
        self.transport = transport or MockTransport()
        self.rate_limiter = rate_limiter or RateLimiter()

    def acquire(
        self,
        source_id: str,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 10.0,
    ) -> AcquisitionResult:
        # 1. Pre-flight authorization check binding SOURCE_ID + METHOD + EXACT HOST + ALLOWED PATH
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

        # 2. Rate limiting pacing check -- keyed by HOST, not source_id.
        # Council review 4, finding 9: docs/SOURCE_REGISTRY.yaml's generated Greenhouse/
        # Lever board entries declare `rate_limits.documented: shared_per_ats_host`, but
        # a limiter keyed by source_id never shares pacing across boards on the same
        # host. Keying by `urlparse(url).netloc` makes every board on
        # `boards-api.greenhouse.io` (or `api.lever.co`) share one pacing bucket, while
        # every other (already one-source-per-host) source is unaffected.
        host = urllib.parse.urlparse(url).netloc.lower()
        wait_needed = self.rate_limiter.acquire(host)
        if wait_needed > 0 and isinstance(self.transport, HttpTransport):
            time.sleep(wait_needed)

        # 3. Construct explicit request
        headers_tuple = tuple(headers.items()) if headers else ()
        req = DiscoveryRequest(
            source_id=source_id,
            url=url,
            method=method,
            body=body,
            headers=headers_tuple,
            timeout_s=timeout_s,
        )

        # 4. Execute transport
        response = self.transport.fetch(req)

        feed_checksum = hashlib.sha256(response.body.encode("utf-8")).hexdigest() if response.body else ""

        return AcquisitionResult(
            source_id=source_id,
            url=url,
            method=method,
            response=response,
            feed_checksum=feed_checksum,
            authorized=True,
        )
