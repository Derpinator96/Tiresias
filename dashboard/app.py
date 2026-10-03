"""Blind Tuner operator dashboard entry point. Private: bound to 127.0.0.1, shows real names,
never hosted publicly. Two pages: Ask (home.py) and Details (details.py, every panel)."""
import streamlit as st

st.set_page_config(page_title="Blind Tuner", layout="centered")
st.navigation([st.Page("home.py", title="Ask", default=True), st.Page("details.py", title="Details")],
              position="top").run()
