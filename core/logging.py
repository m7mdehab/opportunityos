import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

REDACTION_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]{15,}"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(authorization:\s*)[^\s,;]+"), r"\1[REDACTED_AUTH]"),
    (re.compile(r"(?i)(api[_-]?key[\s:=]+)[a-zA-Z0-9_\-]{16,}"), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(token[\s:=]+)[a-zA-Z0-9_\-]{16,}"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(password[\s:=]+)[^\s,;]+"), r"\1[REDACTED_PASSWORD]"),
    (re.compile(r"(?i)(secret[\s:=]+)[^\s,;]+"), r"\1[REDACTED_SECRET]"),
    (re.compile(r"(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?:\b|\+)[1-9]\d{6,14}\b"), "[REDACTED_PHONE]"),
]


def redact_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_data(data: Any) -> Any:
    if isinstance(data, str):
        return redact_text(data)
    elif isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(sensitive in k.lower() for sensitive in ("password", "token", "secret", "cv_body", "email_body", "raw_body")):
                redacted[k] = "[REDACTED_SENSITIVE_CONTENT]"
            else:
                redacted[k] = redact_data(v)
        return redacted
    elif isinstance(data, (list, tuple)):
        return [redact_data(item) for item in data]
    return data


class StructuredLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        if hasattr(record, "run_id") and record.run_id:
            log_entry["run_id"] = record.run_id
        if hasattr(record, "component") and record.component:
            log_entry["component"] = record.component
        if hasattr(record, "extra_data") and record.extra_data:
            log_entry["data"] = redact_data(record.extra_data)
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def get_logger(name: str = "opportunityos") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
