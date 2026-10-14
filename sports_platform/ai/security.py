"""
AI Security and Prompt Injection Hardening — Milestone 10.
"""
import re
import logging

logger = logging.getLogger(__name__)

FORBIDDEN_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions",
    r"disregard\s+(?:all\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instructions)",
    r"you\s+are\s+now\b",
    r"pretend\s+(?:that\s+)?you\s+are",
    r"act\s+as\s+a\s+different",
    r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
    r"what\s+are\s+your\s+(?:system\s+)?instructions",
    r"bypass\s+(?:all\s+)?rules",
    r"dan\s+mode",
    r"jailbreak",
]

MAX_QUESTION_LENGTH = 500


class PromptInjectionError(ValueError):
    """Raised when an adversarial prompt injection pattern is detected."""
    pass


def sanitize_user_input(text: str) -> str:
    """
    Sanitize and check user input for prompt injection.
    Raises PromptInjectionError if malicious patterns are matched.
    Truncates text to MAX_QUESTION_LENGTH to prevent token stuffing.
    """
    if not text or not text.strip():
        raise ValueError("User question cannot be empty.")

    clean_text = text.strip()
    lower_text = clean_text.lower()

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, lower_text):
            logger.warning(f"Prompt injection pattern detected: '{pattern}' in question: '{clean_text[:60]}...'")
            raise PromptInjectionError("Input contains potentially harmful or restricted adversarial content.")

    # Prevent token stuffing
    if len(clean_text) > MAX_QUESTION_LENGTH:
        clean_text = clean_text[:MAX_QUESTION_LENGTH].strip()

    return clean_text
