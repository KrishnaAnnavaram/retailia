"""``retailia`` command line.

    retailia init-db [--customers N]     create the synthetic store (prints a one-time demo password)
    retailia build-index [--faq-dir D]   build the FAQ index from markdown/text/PDF files
    retailia chat --username U           chat in the terminal
    retailia eval [--json PATH]          run the evaluation and red-team suites
    retailia ui                          launch the Streamlit app (needs the [ui] extra)
"""

from __future__ import annotations

import argparse
import getpass
import json
import secrets
import subprocess
import sys
from pathlib import Path

from retailia.app import build, make_embedder
from retailia.auth.service import LoginFailed
from retailia.config import Settings, SettingsError, load_env_file
from retailia.data.db import StoreDB
from retailia.data.seed import seed_store
from retailia.rag.index import build_index, save_index

MAX_DEMO_CUSTOMERS = 999


def cmd_init_db(settings: Settings, args: argparse.Namespace) -> int:
    password = secrets.token_urlsafe(9)
    report = seed_store(StoreDB(settings.db_path), demo_password=password, seed=settings.seed,
                        customers=args.customers)
    print(f"Store database written to {settings.db_path}")
    print(f"{report.customers} customers, {report.staff} staff, {report.products} products, {report.orders} orders")
    print(f"Demo accounts customer01..customer{report.customers:02d} and staff01 share this password "
          f"(shown once, stored only as a hash): {password}")
    return 0


def cmd_build_index(settings: Settings, args: argparse.Namespace) -> int:
    faq_dir = Path(args.faq_dir).resolve() if args.faq_dir else settings.faq_dir
    try:
        index = build_index(faq_dir, make_embedder(settings))
    except (FileNotFoundError, ValueError) as exc:  # missing folder, or no .md/.txt/.pdf content in it
        print(f"Cannot build the FAQ index: {exc}", file=sys.stderr)
        return 1
    save_index(index, settings.index_path)
    print(f"Indexed {len(index.chunks)} FAQ sections from {faq_dir} -> {settings.index_path} "
          f"(version {index.version}, embedder {index.embedder})")
    return 0


def cmd_chat(settings: Settings, args: argparse.Namespace) -> int:
    app = build(settings)
    if not app.db.path.exists():
        print("No store database yet; run `retailia init-db` first.", file=sys.stderr)
        return 1
    try:
        principal = app.auth.login(args.username, getpass.getpass("Password: "))
    except LoginFailed as exc:
        print(f"Sign-in failed: {exc}", file=sys.stderr)
        return 1
    if app.index_problem:
        print(f"Note: FAQ answers are unavailable ({app.index_problem}).")
    conversation = app.assistant.start(principal)
    print(f"Hi {principal.username}! Type 'quit' to leave.")
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if question.lower() in ("quit", "exit"):
            return 0
        print(f"retailia> {app.assistant.ask(conversation, question).text}\n")


def cmd_eval(settings: Settings, args: argparse.Namespace) -> int:
    from retailia.app import make_model
    from retailia.evaluation.harness import run_suites

    report = run_suites(lambda: make_model(settings))
    summary = report.summary()
    print(json.dumps(summary, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if report.passed else 1


def cmd_ui(settings: Settings, args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "streamlit", "run",
                            str(Path(__file__).parent / "ui" / "streamlit_app.py")])


def _customer_count(raw: str) -> int:
    # Staff accounts use customer ids from 1001, so at most 999 demo customers fit.
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a whole number, got {raw!r}") from None
    if not 1 <= value <= MAX_DEMO_CUSTOMERS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_DEMO_CUSTOMERS}, got {value}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="retailia", description="Retail customer-service assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init-db", help="create the synthetic store database (replaces existing demo data)")
    p.add_argument("--customers", type=_customer_count, default=20,
                   help=f"number of demo customers, 1 to {MAX_DEMO_CUSTOMERS} (default: 20)")
    p = sub.add_parser("build-index", help="build the FAQ index")
    p.add_argument("--faq-dir", default=None, help="folder of .md, .txt or .pdf FAQ files (default: RETAILIA_FAQ_DIR)")
    p = sub.add_parser("chat", help="chat in the terminal")
    p.add_argument("--username", required=True)
    p = sub.add_parser("eval", help="run evaluation + red-team suites")
    p.add_argument("--json", default=None, help="also write the summary to this file")
    sub.add_parser("ui", help="launch the Streamlit app")
    args = parser.parse_args(argv)

    load_env_file()
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    commands = {"init-db": cmd_init_db, "build-index": cmd_build_index, "chat": cmd_chat, "eval": cmd_eval,
                "ui": cmd_ui}
    return commands[args.command](settings, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
