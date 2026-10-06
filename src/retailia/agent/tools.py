"""Typed, customer-scoped tools exposed to the model.

Boundary rules enforced here:

* The tool list depends on the signed-in role; customers never see the analytics tool,
  and its handler re-checks the role anyway.
* No tool has a customer/user id parameter. Every account tool runs through a
  :class:`CustomerScope` bound to the session's ``customer_id``.
* Arguments are validated against declared rules; unknown keys, wrong types,
  oversized strings and out-of-range numbers are rejected before any query runs.
* Every result is JSON with an explicit ``found`` flag, which is the "no answer"
  signal the assistant uses for fallbacks (instead of matching reply strings).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from retailia.auth.service import Principal
from retailia.data.analytics import AnalyticsDenied, run_analytics_query
from retailia.data.db import StoreDB
from retailia.data.repositories import Catalog, CustomerScope
from retailia.rag.retriever import HybridRetriever

ORDER_STATUSES = ("processing", "shipped", "delivered", "cancelled", "returned")


@dataclass(frozen=True)
class Field:
    kind: str  # "string" | "integer" | "number" | "boolean"
    help: str
    required: bool = False
    choices: tuple[str, ...] = ()
    low: float | None = None
    high: float | None = None
    max_len: int = 200

    def json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": self.kind, "description": self.help}
        if self.choices:
            schema["enum"] = list(self.choices)
        if self.low is not None:
            schema["minimum"] = self.low
        if self.high is not None:
            schema["maximum"] = self.high
        return schema


@dataclass(frozen=True)
class Tool:
    name: str
    purpose: str
    fields: dict[str, Field] = field(default_factory=dict)
    staff_only: bool = False
    route: str = "account"  # account | catalog | faq | analytics (used for routing metrics)

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.purpose,
                "parameters": {"type": "object", "additionalProperties": False,
                               "properties": {k: f.json_schema() for k, f in self.fields.items()},
                               "required": [k for k, f in self.fields.items() if f.required]}}


class BadArguments(ValueError):
    pass


def check_args(tool: Tool, args: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise BadArguments("arguments must be a JSON object")
    extra = set(args) - set(tool.fields)
    if extra:
        raise BadArguments(f"{tool.name} does not accept {sorted(extra)}")
    out: dict[str, Any] = {}
    for name, rule in tool.fields.items():
        value = args.get(name)
        if value is None or value == "":
            if rule.required:
                raise BadArguments(f"{name} is required")
            continue
        if rule.kind == "boolean":
            if not isinstance(value, bool):
                raise BadArguments(f"{name} must be true or false")
        elif rule.kind in ("integer", "number"):
            if isinstance(value, bool):
                raise BadArguments(f"{name} must be a number")
            try:
                value = int(value) if rule.kind == "integer" else float(value)
            except (TypeError, ValueError):
                raise BadArguments(f"{name} must be a number") from None
            if (rule.low is not None and value < rule.low) or (rule.high is not None and value > rule.high):
                raise BadArguments(f"{name} is out of range")
        else:
            if not isinstance(value, str):
                raise BadArguments(f"{name} must be text")
            value = value.strip()
            if len(value) > rule.max_len:
                raise BadArguments(f"{name} is too long (max {rule.max_len} characters)")
            if rule.choices:
                if value.lower() not in rule.choices:
                    raise BadArguments(f"{name} must be one of {list(rule.choices)}")
                value = value.lower()
        out[name] = value
    return out


TOOLS: tuple[Tool, ...] = (
    Tool("get_my_orders", "List the signed-in customer's recent orders, newest first.",
         {"status": Field("string", "Only orders with this status.", choices=ORDER_STATUSES),
          "limit": Field("integer", "How many orders (1-10).", low=1, high=10)}),
    Tool("get_order", "Details of one of the signed-in customer's orders.",
         {"order_id": Field("integer", "The order number.", required=True, low=1, high=10**9)}),
    Tool("get_my_cart", "Items currently in the signed-in customer's cart."),
    Tool("get_my_account", "The signed-in customer's account summary (email is masked)."),
    Tool("get_my_reviews", "Ratings and reviews the signed-in customer has written."),
    Tool("search_products", "Search the public product catalogue.",
         {"query": Field("string", "Words to look for in product names or categories.", max_len=100),
          "category": Field("string", "Exact category name.", max_len=60),
          "max_price": Field("number", "Maximum price in dollars.", low=0, high=100000),
          "in_stock_only": Field("boolean", "Only products in stock.")}, route="catalog"),
    Tool("get_product", "Details of one product.",
         {"product_id": Field("integer", "Product id from search_products.", required=True, low=1, high=10**9)},
         route="catalog"),
    Tool("search_faq", "Search store policies and FAQs (returns, shipping, payment, support...). Returns passages "
                       "with citation ids; cite them as [id].",
         {"question": Field("string", "The policy question.", required=True, max_len=300)}, route="faq"),
    Tool("run_catalog_analytics", "Staff only. Run one read-only SELECT over the views v_catalog, v_product_sales "
                                  "and v_orders_by_month (no customer data).",
         {"sql": Field("string", "A single SELECT statement.", required=True, max_len=2000)},
         staff_only=True, route="analytics"),
)
TOOL_BY_NAME = {t.name: t for t in TOOLS}


def tools_for(principal: Principal) -> list[Tool]:
    return [t for t in TOOLS if principal.is_staff or not t.staff_only]


@dataclass
class ToolContext:
    """Everything a tool may touch, bound to one signed-in principal."""

    principal: Principal
    db: StoreDB
    retriever: HybridRetriever | None
    passages_seen: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def scope(self) -> CustomerScope:
        return CustomerScope(self.db, self.principal.customer_id)

    @property
    def catalog(self) -> Catalog:
        return Catalog(self.db)


def _orders(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    orders = ctx.scope.orders(limit=a.get("limit", 5), status=a.get("status"))
    return {"found": bool(orders), "orders": orders}


def _order(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    order = ctx.scope.order(a["order_id"])
    if order is None:  # same answer for "not yours" and "does not exist"
        return {"found": False, "message": f"No order {a['order_id']} on your account."}
    return {"found": True, "order": order}


def _cart(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    cart = ctx.scope.cart()
    return {"found": bool(cart["items"]), **cart}


def _account(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    profile = ctx.scope.profile()
    return {"found": profile is not None, "account": profile}


def _reviews(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    reviews = ctx.scope.my_reviews()
    return {"found": bool(reviews), "reviews": reviews}


def _products(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    max_cents = round(a["max_price"] * 100) if "max_price" in a else None
    items = ctx.catalog.search(a.get("query"), category=a.get("category"), max_price_cents=max_cents,
                               in_stock_only=a.get("in_stock_only", False))
    return {"found": bool(items), "products": items}


def _product(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    product = ctx.catalog.product(a["product_id"])
    return {"found": product is not None, "product": product}


def _faq(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    if ctx.retriever is None:
        return {"found": False, "message": "The FAQ index is not available yet (run `retailia build-index`)."}
    passages = ctx.retriever.search(a["question"])
    for p in passages:
        ctx.passages_seen[p.chunk_id] = {"title": p.title, "text": p.text}
    return {"found": bool(passages),
            "passages": [{"id": p.chunk_id, "title": p.title, "text": p.text} for p in passages]}


def _analytics(ctx: ToolContext, a: dict[str, Any]) -> dict[str, Any]:
    if not ctx.principal.is_staff:
        return {"found": False, "error": "forbidden", "message": "Analytics is available to staff only."}
    try:
        result = run_analytics_query(ctx.db, a["sql"])
    except AnalyticsDenied as exc:
        return {"found": False, "error": "query_rejected", "message": str(exc)}
    return {"found": bool(result["rows"]), **result}


HANDLERS: dict[str, Callable[[ToolContext, dict[str, Any]], dict[str, Any]]] = {
    "get_my_orders": _orders, "get_order": _order, "get_my_cart": _cart, "get_my_account": _account,
    "get_my_reviews": _reviews, "search_products": _products, "get_product": _product, "search_faq": _faq,
    "run_catalog_analytics": _analytics,
}


def run_tool(ctx: ToolContext, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    tool = TOOL_BY_NAME.get(name)
    if tool is None or tool not in tools_for(ctx.principal):
        return {"found": False, "error": "unknown_tool", "message": f"No tool called {name!r} is available."}
    try:
        clean = check_args(tool, args)
    except BadArguments as exc:
        return {"found": False, "error": "bad_arguments", "message": str(exc)}
    return HANDLERS[name](ctx, clean)


def encode_result(result: dict[str, Any]) -> str:
    return json.dumps(result, default=str, ensure_ascii=False)
