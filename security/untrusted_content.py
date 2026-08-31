import re
from typing import Dict, Any, List

SUSPICIOUS_INSTRUCTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(?:all\s+)?previous\s+instructions"),
    re.compile(r"(?i)system\s*:\s*you\s+are\s+now"),
    re.compile(r"(?i)you\s+must\s+output\s+the\s+(?:api\s+key|password|secret|env)"),
    re.compile(r"(?i)grant\s+(?:all\s+)?permissions"),
    re.compile(r"(?i)bypass\s+(?:kill\s+switch|safety\s+filter|guard)"),
    re.compile(r"(?i)set\s+execution_mode\s*=\s*CONTROLLED_SUBMIT"),
]

class UntrustedContentSanitizer:
    @staticmethod
    def contains_adversarial_instructions(text: str) -> bool:
        for pattern in SUSPICIOUS_INSTRUCTION_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @staticmethod
    def sanitize_untrusted_data(text: str) -> str:
        # Enforce that untrusted data is strictly treated as passive string content
        return str(text)
