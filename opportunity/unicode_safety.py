"""Unicode normalization helpers for untrusted source payloads."""
from __future__ import annotations

from typing import Any


def normalize_unicode(value: Any) -> Any:
    """Replace unpaired UTF-16 surrogate code points in source values.

    Valid Unicode scalar values, including non-ASCII text and emoji, are left
    unchanged. Lone surrogates are malformed UTF-8 input and are converted to
    U+FFFD so hashing, serialization, and database writes remain well-defined.
    Containers are copied recursively; other value types are returned as-is.
    """
    if isinstance(value, str):
        normalized: list[str] = []
        index = 0
        while index < len(value):
            codepoint = ord(value[index])
            if 0xD800 <= codepoint <= 0xDBFF and index + 1 < len(value):
                low = ord(value[index + 1])
                if 0xDC00 <= low <= 0xDFFF:
                    scalar = 0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00)
                    normalized.append(chr(scalar))
                    index += 2
                    continue
            normalized.append("\ufffd" if 0xD800 <= codepoint <= 0xDFFF else value[index])
            index += 1
        return "".join(normalized)
    if isinstance(value, list):
        return [normalize_unicode(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_unicode(item) for item in value)
    if isinstance(value, dict):
        return {
            normalize_unicode(key): normalize_unicode(item)
            for key, item in value.items()
        }
    return value
