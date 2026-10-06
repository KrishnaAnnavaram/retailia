"""Offline, deterministic model: router-driven tool calls and template answers.

It implements the same :class:`ChatModel` protocol as a hosted LLM, so the
demo and the evaluation exercise the real assistant loop, tool validation,
customer scoping and guardrails without any network access.
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from retailia.agent.models import ModelTurn, ToolRequest
from retailia.agent.router import Route, classify

HELP = ("I can check your orders, cart and account, search products, and answer questions about returns, "
        "shipping, payment and support. For example: 'where is my last order?', 'do you have yoga mats under $40?' "
        "or 'how do refunds work?'.")

ANALYTICS_SQL = [
    (re.compile(r"best[- ]?selling|top[- ]?selling|units sold", re.I),
     "SELECT name, category, units_sold, revenue_cents FROM v_product_sales ORDER BY units_sold DESC, name LIMIT 5"),
    (re.compile(r"revenue|sales by", re.I),
     "SELECT month, SUM(orders) AS orders, SUM(revenue_cents) AS revenue_cents FROM v_orders_by_month "
     "WHERE status NOT IN ('cancelled', 'returned') GROUP BY month ORDER BY month DESC LIMIT 6"),
    (re.compile(r"out of stock|low stock", re.I),
     "SELECT sku, name, category FROM v_catalog WHERE stock = 0 ORDER BY category, name LIMIT 20"),
    (re.compile(r"highest[- ]rated", re.I),
     "SELECT name, category, avg_rating, rating_count FROM v_catalog WHERE rating_count > 0 "
     "ORDER BY avg_rating DESC, rating_count DESC LIMIT 5"),
    (re.compile(r"lowest[- ]rated", re.I),
     "SELECT name, category, avg_rating, rating_count FROM v_catalog WHERE rating_count > 0 "
     "ORDER BY avg_rating, rating_count DESC LIMIT 5"),
]


def _latest_user(messages: Sequence[dict[str, Any]]) -> str:
    return next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")


def _results_this_turn(messages: Sequence[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for m in reversed(messages):
        if m["role"] == "user":
            break
        if m["role"] == "tool":
            found.append((m["tool"], json.loads(m["content"])))
    return found[::-1]


def _last_order_in_history(messages: Sequence[dict[str, Any]]) -> int | None:
    """Conversation memory: the most recent order number that appeared in a tool result."""
    for m in reversed(messages):
        if m["role"] != "tool":
            continue
        payload = json.loads(m["content"])
        if payload.get("order"):
            return payload["order"]["order_id"]
        if payload.get("orders"):
            return payload["orders"][0]["order_id"]
    return None


class OfflineModel:
    def next_turn(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]) -> ModelTurn:
        available = {t["name"] for t in tools}
        question = _latest_user(messages)
        results = _results_this_turn(messages)
        if results:
            follow_up = self._fallback(question, results, available, messages)
            return follow_up or ModelTurn(content=self._answer(results))
        return self._plan(question, classify(question), available, messages)

    @staticmethod
    def _call(messages: Sequence[dict[str, Any]], tool: str, **args: Any) -> ModelTurn:
        return ModelTurn(requests=(ToolRequest(f"call-{len(messages)}", tool, args),))

    def _plan(self, question: str, route: Route, available: set[str],
              messages: Sequence[dict[str, Any]]) -> ModelTurn:
        if route.label == "smalltalk":
            return ModelTurn(content="Hi! " + HELP if not question.lower().startswith("thank") else
                             "You're welcome! Anything else I can help with?")
        if route.label == "analytics":
            if "run_catalog_analytics" not in available:
                return ModelTurn(content="Sales and catalogue analytics are available to store staff only.")
            explicit = re.search(r"sql\s*:\s*(.+)$", question, re.I | re.S)
            sql = explicit.group(1).strip() if explicit else next(
                (q for pattern, q in ANALYTICS_SQL if pattern.search(question)), None)
            if sql is None:
                return ModelTurn(content="Which report do you need: best sellers, revenue by month, out of stock "
                                         "products or highest/lowest rated products?")
            return self._call(messages, "run_catalog_analytics", sql=sql)
        if route.label == "account":
            if route.intent == "order":
                return self._call(messages, "get_order", order_id=route.slots["order_id"])
            if route.intent == "follow_up":
                last = _last_order_in_history(messages)
                if last is None:
                    if route.slots.get("policy"):  # "can I return it?" with no order in context
                        return self._call(messages, "search_faq", question=question)
                    return ModelTurn(content="Which order do you mean? Please give me the order number.")
                return self._call(messages, "get_order", order_id=last)
            if route.intent == "orders":
                args = {"status": route.slots["status"]} if route.slots.get("status") else {}
                return self._call(messages, "get_my_orders", **args)
            tool = {"cart": "get_my_cart", "account": "get_my_account", "reviews": "get_my_reviews"}[route.intent]
            return self._call(messages, tool)
        if route.label == "catalog":
            args = {k: v for k, v in (("query", route.slots.get("query")),
                                      ("category", (route.slots.get("category") or "").title() or None),
                                      ("max_price", route.slots.get("max_price"))) if v}
            return self._call(messages, "search_products", **args)
        if route.label in ("faq", "unknown"):
            return self._call(messages, "search_faq", question=question)
        return ModelTurn(content=HELP)  # pragma: no cover

    def _fallback(self, question: str, results: list[tuple[str, dict[str, Any]]], available: set[str],
                  messages: Sequence[dict[str, Any]]) -> ModelTurn | None:
        """Chain to the FAQ when the question also asks about policy, or when a catalogue search found nothing."""
        tools_used = {name for name, _ in results}
        if "search_faq" in tools_used:
            return None
        last_tool, last = results[-1]
        route = classify(question)
        if last_tool in ("get_order", "get_my_orders") and route.slots.get("policy"):
            return self._call(messages, "search_faq", question=question)
        if last_tool == "search_products" and not last.get("found") and route.slots.get("policy"):
            return self._call(messages, "search_faq", question=question)
        return None

    # ------------------------------------------------------------------ wording
    def _answer(self, results: list[tuple[str, dict[str, Any]]]) -> str:
        return "\n\n".join(self._say(name, payload) for name, payload in results)

    @staticmethod
    def _say(tool: str, r: dict[str, Any]) -> str:
        if r.get("error"):
            return f"Sorry, I couldn't do that: {r['message']}"
        if tool == "get_my_orders":
            if not r["found"]:
                return "I couldn't find any matching orders on your account."
            lines = [f"- Order #{o['order_id']} placed {o['placed_on']}: {o['status']}, {o['units']} item(s), "
                     f"{o['total']}" + (f", tracking {o['tracking_code']}" if o["tracking_code"] else "")
                     for o in r["orders"]]
            return "Your recent orders:\n" + "\n".join(lines)
        if tool == "get_order":
            if not r["found"]:
                return r["message"]
            o = r["order"]
            items = "; ".join(f"{i['quantity']} x {i['product']} ({i['unit_price']})" for i in o["items"])
            tracking = f" Tracking code: {o['tracking_code']}." if o["tracking_code"] else ""
            return (f"Order #{o['order_id']} (placed {o['placed_on']}) is {o['status']}. Total {o['total']}. "
                    f"Items: {items}.{tracking}")
        if tool == "get_my_cart":
            if not r["found"]:
                return "Your cart is empty."
            lines = [f"- {i['quantity']} x {i['product']} ({i['unit_price']})"
                     + ("" if i["in_stock"] else " - currently out of stock") for i in r["items"]]
            return f"Your cart has {r['units']} item(s), subtotal {r['subtotal']}:\n" + "\n".join(lines)
        if tool == "get_my_account":
            a = r["account"]
            return f"You're signed in as {a['username']} ({a['name']}), email {a['email']}, city {a['city']}."
        if tool == "get_my_reviews":
            if not r["found"]:
                return "You haven't reviewed any products yet."
            return "Your reviews:\n" + "\n".join(f"- {v['product']}: {v['rating']}/5, \"{v['comment']}\""
                                                 for v in r["reviews"])
        if tool == "search_products":
            if not r["found"]:
                return "I couldn't find products matching that. Try other words or a higher price limit."
            lines = [f"- {p['name']} ({p['category']}), {p['price']}, "
                     + ("in stock" if p["in_stock"] else "out of stock")
                     + (f", rated {p['rating']}/5 by {p['ratings']}" if p["ratings"] else "") for p in r["products"]]
            return "Here is what I found:\n" + "\n".join(lines)
        if tool == "get_product":
            if not r["found"]:
                return "I couldn't find that product."
            p = r["product"]
            return f"{p['name']} ({p['category']}) costs {p['price']} and is {'in' if p['in_stock'] else 'out of'} stock."
        if tool == "search_faq":
            if not r["found"]:
                return ("I couldn't find that in our store FAQ. Our support team can help; ask me "
                        "'how do I contact support?' for their hours and contact details.")
            top = r["passages"][0]
            return f"{top['text']} [{top['id']}]"  # the passage verbatim: times, URLs and lists stay intact
        if tool == "run_catalog_analytics":
            if not r["found"]:
                return "The query returned no rows."
            header = " | ".join(r["columns"])
            rows = "\n".join(" | ".join(str(v) for v in row) for row in r["rows"])
            return f"{header}\n{rows}" + ("\n(truncated)" if r.get("truncated") else "")
        return json.dumps(r)
