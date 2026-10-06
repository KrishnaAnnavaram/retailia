"""Streamlit UI: sign-in form, chat with history, and FAQ citations.

Run with ``retailia ui`` (needs ``pip install retailia[ui]``). The browser
session holds only an opaque token; the principal lives in the server-side
:class:`SessionStore`, and every answer goes through :class:`Assistant`.
"""

from __future__ import annotations

import streamlit as st

from retailia.app import build
from retailia.auth.service import LoginFailed
from retailia.config import Settings, SettingsError, load_env_file


@st.cache_resource
def get_app():
    load_env_file()
    return build(Settings.from_env())


def login_form(app) -> None:
    with st.form("login"):
        st.markdown("#### Sign in")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            try:
                principal = app.auth.login(username, password)
            except LoginFailed as exc:
                st.error(str(exc))
                return
            st.session_state.token = app.sessions.create(principal)
            st.session_state.conversation = app.assistant.start(principal)
            st.session_state.transcript = []
            st.rerun()


def chat(app, principal) -> None:
    with st.sidebar:
        st.write(f"Signed in as **{principal.username}** ({principal.role})")
        if app.index_problem:
            st.warning(f"FAQ answers unavailable: {app.index_problem}")
        if st.button("Sign out"):
            app.sessions.revoke(st.session_state.pop("token"))
            st.session_state.pop("conversation", None)
            st.rerun()
    for role, text, sources in st.session_state.transcript:
        with st.chat_message(role):
            st.markdown(text)
            if sources:
                st.caption("Sources: " + ", ".join(sources))
    question = st.chat_input("Ask about your orders, products or store policies")
    if question:
        answer = app.assistant.ask(st.session_state.conversation, question)
        st.session_state.transcript += [("user", question, []), ("assistant", answer.text, answer.citations)]
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Retailia", page_icon=":shopping_bags:", layout="centered")
    st.title("Retailia")
    try:
        app = get_app()
    except SettingsError as exc:
        st.error(f"Configuration error: {exc}")
        return
    if not app.db.path.exists():
        st.warning("No store database found. Run `retailia init-db` first.")
        return
    principal = app.sessions.get(st.session_state.get("token"))
    if principal is None:
        login_form(app)
    else:
        chat(app, principal)


main()
