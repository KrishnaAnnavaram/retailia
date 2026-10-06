"""Input and output guardrails.

These are defence in depth. The real boundary is structural: tools are
customer-scoped and read-only, so even an injected instruction can only read
the signed-in customer's own data. The guardrails add:

* a fixed refusal for requests that explicitly target other customers or bulk
  personal data (so the model is not even asked);
* a detector for common prompt-injection phrasing, used for logging/metrics;
* an output filter that removes any email address other than the customer's own.
"""

from __future__ import annotations

import re

CROSS_ACCOUNT_REFUSAL = ("I can only help with your own account. I can't look up or share other customers' "
                         "orders, carts or personal details.")

_CROSS_ACCOUNT = re.compile(
    r"\b(?:all|every|other|another|someone else'?s?|each)\s+(?:customers?|users?|accounts?|people)\b"
    r"|\b(?:customer|user|account)(?:\s*(?:id|number|no\.?|#)\s*[:=#]?\s*|\s+)\d+\b"
    r"|\b(?:list|dump|export|show)\b[^.?!]{0,40}\b(?:emails|addresses|passwords|password hashes|customers|users)\b"
    r"|\bcustomers?\s+table\b",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"ignore (?:all |any |the )?(?:previous|prior|above) (?:instructions|rules)|system prompt|you are now|"
    r"developer mode|act as (?:an? )?(?:admin|administrator|dba)|disregard (?:your|the) rules|"
    r"\b(?:drop|delete|update|insert|alter)\s+(?:table|from|into)\b|;\s*--",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def targets_other_accounts(text: str) -> bool:
    return bool(_CROSS_ACCOUNT.search(text))


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def redact_foreign_emails(text: str, allowed: set[str]) -> str:
    """Replace every email address that is not explicitly allowed (store addresses, the owner's own)."""
    allowed_lower = {a.lower() for a in allowed}
    return _EMAIL.sub(lambda m: m.group(0) if m.group(0).lower() in allowed_lower else "[redacted email]", text)
