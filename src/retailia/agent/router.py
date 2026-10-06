"""Deterministic intent router used by the offline model and as a baseline in evaluation.

It returns a :class:`Route` with a label (account / catalog / faq / analytics /
smalltalk / unknown), an account sub-intent, and extracted slots such as an
order number or a price ceiling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from retailia.agent.tools import ORDER_STATUSES

CATEGORIES = ("electronics", "home & kitchen", "clothing", "books", "sports & outdoors", "beauty")
_POLICY = re.compile(r"\b(?:return|refund|exchang|ship|deliver|cancel|pay|paypal|card|size|sizing|warrant|support|"
                     r"contact|hours|open|phone|password|privacy|damaged|broken|wrong item|policy|policies)\w*",
                     re.IGNORECASE)
_SMALLTALK = re.compile(r"^\s*(?:hi|hello|hey|thanks|thank you|good (?:morning|afternoon|evening))\b[\s!.,]*$",
                        re.IGNORECASE)
_ANALYTICS = re.compile(r"\b(?:best[- ]?selling|top[- ]?selling|revenue|sales by|units sold|out of stock products|"
                        r"low stock|highest[- ]rated|lowest[- ]rated|sql\s*:)", re.IGNORECASE)
_CATALOG = re.compile(r"\b(?:do you (?:have|sell|stock)|looking for|show me|recommend|search for|any \w+ under|"
                      r"products?|in stock|cheapest|under \$?\d+|price of|how much (?:is|are|does) (?:the|a|your) )",
                      re.IGNORECASE)


@dataclass(frozen=True)
class Route:
    label: str
    intent: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)


def _order_id(text: str) -> int | None:
    match = re.search(r"\border\s*(?:number|no\.?|#)?\s*#?(\d{1,9})\b|#(\d{1,9})\b", text, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _price(text: str) -> float | None:
    match = re.search(r"(?:under|below|less than|max(?:imum)?|cheaper than)\s*\$?\s*(\d+(?:\.\d{1,2})?)", text,
                      re.IGNORECASE)
    return float(match.group(1)) if match else None


def classify(text: str) -> Route:
    lowered = text.lower()
    if _SMALLTALK.match(text):
        return Route("smalltalk")
    if _ANALYTICS.search(text):
        return Route("analytics")

    order_id = _order_id(text)
    status = next((s for s in ORDER_STATUSES if re.search(rf"\b{s}\b", lowered)), None)
    policy = bool(_POLICY.search(text))
    slots: dict[str, Any] = {"policy": policy}
    if order_id is not None:
        return Route("account", "order", {**slots, "order_id": order_id})
    if re.search(r"\bmy (?:cart|basket)\b|\bin my (?:cart|basket)\b", lowered):
        return Route("account", "cart", slots)
    if re.search(r"\bmy (?:account|email|details|profile|address)\b", lowered):
        return Route("account", "account", slots)
    if re.search(r"\bmy (?:reviews?|ratings?)\b|\bi (?:rated|reviewed)\b", lowered):
        return Route("account", "reviews", slots)
    if re.search(r"\b(?:my|last|latest|recent)(?: [a-z]+)? (?:orders?|package|parcel|purchases?|delivery)\b"
                 r"|\bwhere(?:'s| is) my\b|\btrack my\b", lowered):
        return Route("account", "orders", {**slots, "status": status})
    if re.search(r"\b(?:it|that order|this order|that one|the order)\b", lowered):
        return Route("account", "follow_up", slots)

    if policy and not _CATALOG.search(text):
        return Route("faq", None, slots)  # "warranty on electronics" is a policy question, not a product search
    if _CATALOG.search(text) or any(c in lowered for c in CATEGORIES):
        category = next((c for c in CATEGORIES if c in lowered), None)
        return Route("catalog", None, {"category": category, "max_price": _price(text), "query": _product_words(text)})
    return Route("unknown", None, slots)


_FILLER = set("do you have sell stock looking for show me recommend search any under below less than cheap cheapest "
              "products product in what which some a an the please i want need to buy price of how much is are does "
              "your our with and or can get".split())


def _product_words(text: str) -> str | None:
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in _FILLER and len(w) > 2]
    words = [w for w in words if w not in {c for cat in CATEGORIES for c in cat.split()}]
    return " ".join(words[:4]) or None
