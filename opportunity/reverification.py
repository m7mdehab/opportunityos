from typing import Dict, Any, Optional
from datetime import datetime, timezone
import urllib.request
import urllib.error
from opportunity.models import Opportunity

class StaleOpportunityReverifier:
    @staticmethod
    def reverify_url(url: str, timeout_seconds: int = 5) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpportunityOS-Reverifier/0.2 (Verification Diagnostic)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                status_code = response.getcode()
                return {
                    "is_stale": status_code in (404, 410),
                    "status_code": status_code,
                    "reverified_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "URL is active and reachable" if status_code == 200 else f"HTTP {status_code}",
                }
        except urllib.error.HTTPError as e:
            return {
                "is_stale": e.code in (404, 410),
                "status_code": e.code,
                "reverified_at": datetime.now(timezone.utc).isoformat(),
                "reason": f"HTTP error {e.code}",
            }
        except urllib.error.URLError as e:
            return {
                "is_stale": False,
                "status_code": None,
                "reverified_at": datetime.now(timezone.utc).isoformat(),
                "reason": f"Transient network failure: {e.reason}",
            }
