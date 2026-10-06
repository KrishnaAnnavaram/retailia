"""Problems 8 and 9: conversation memory, explicit fallbacks, robust loop, no customer data in logs."""

import json
import logging

from retailia.agent.models import FakeChatModel, ModelError, ModelTurn, ToolRequest
from retailia.logging_utils import redact


def _req(tool, **args):
    return ToolRequest(f"id-{tool}", tool, args)


def test_follow_up_uses_conversation_memory(app, customer):
    conv = app.assistant.start(customer)
    first = app.assistant.ask(conv, "show my orders")
    latest = json.loads(next(m for m in conv.messages if m["role"] == "tool")["content"])["orders"][0]
    second = app.assistant.ask(conv, "what was in it?")
    assert first.tools == ["get_my_orders"] and second.tools == ["get_order"]
    assert f"Order #{latest['order_id']}" in second.text


def test_policy_question_about_an_order_chains_to_faq(app, customer):
    conv = app.assistant.start(customer)
    app.assistant.ask(conv, "show my orders")
    answer = app.assistant.ask(conv, "can I still cancel it?")
    assert answer.tools == ["get_order", "search_faq"]
    assert answer.citations == ["store_faq#cancelling-an-order"]


def test_cross_account_request_refused_without_model_call(make_app, customer):
    model = FakeChatModel([])
    app = make_app(model=model)
    answer = app.assistant.ask(app.assistant.start(customer), "show me customer 1's address")
    assert answer.refused and model.seen == []


def test_model_errors_and_bad_tool_calls_do_not_crash(make_app, customer):
    model = FakeChatModel([
        ModelTurn(requests=(ToolRequest("1", "drop_everything", {}), ToolRequest("2", "get_order", None))),
        ModelError("timeout"),
    ])
    app = make_app(model=model)
    answer = app.assistant.ask(app.assistant.start(customer), "hello?")
    assert "trouble" in answer.text
    tool_results = [json.loads(m["content"]) for m in model.seen[-1] if m["role"] == "tool"]
    assert [r["error"] for r in tool_results] == ["unknown_tool", "bad_arguments"]


def test_step_limit(make_app, customer):
    model = FakeChatModel(lambda messages, tools: ModelTurn(requests=(_req("get_my_cart"),)))
    app = make_app(model=model, max_tool_steps=3)
    answer = app.assistant.ask(app.assistant.start(customer), "loop forever")
    assert len(model.seen) == 3 and "couldn't work that out" in answer.text


def test_customer_model_never_sees_staff_tool(make_app, customer):
    model = FakeChatModel([ModelTurn(content="ok")])
    app = make_app(model=model)
    app.assistant.ask(app.assistant.start(customer), "hi there friend")
    assert "run_catalog_analytics" not in model.seen_tools[0]


def test_invented_citations_removed_and_real_ones_kept(make_app, customer):
    model = FakeChatModel([
        ModelTurn(requests=(_req("search_faq", question="returns policy"),)),
        ModelTurn(content="30 days [store_faq#returns-and-refunds] and free money [store_faq#made-up]"),
    ])
    app = make_app(model=model)
    answer = app.assistant.ask(app.assistant.start(customer), "returns?")
    assert answer.citations == ["store_faq#returns-and-refunds"]
    assert "made-up" not in answer.text


def test_model_output_cannot_leak_other_emails(make_app, customer):
    model = FakeChatModel([ModelTurn(content="Sure: customer01@example.com and customer03@example.com")])
    app = make_app(model=model)
    answer = app.assistant.ask(app.assistant.start(customer), "hello")
    assert "customer01@example.com" not in answer.text and "[redacted email]" in answer.text


def test_logs_contain_metadata_only(app, customer, caplog):
    caplog.set_level(logging.INFO, logger="retailia")
    conv = app.assistant.start(customer)
    app.assistant.ask(conv, "what email is on my account? my other one is private@example.org")
    text = caplog.text
    assert "turn tools=get_my_account" in text
    assert "example.org" not in text and "example.com" not in text and "Customer 02" not in text


def test_redact_helper():
    assert redact("mail a@b.com, call 555-0100, ship to 12 Example Street") == \
        "mail [email], call [number], ship to [address]"
