"""
Secrets loader — works both locally (.env) and on Streamlit Cloud (st.secrets).
Import this instead of reading os.environ directly for any sensitive key.
"""
from __future__ import annotations
import os


def get_secret(key: str, default: str = "") -> str:
    """
    Look up a secret in this order:
    1. st.secrets  (Streamlit Cloud vault)
    2. os.environ  (local .env via load_dotenv, or system env)
    3. default
    """
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)


def inject_all_into_env() -> None:
    """
    Call this once at app startup to push all st.secrets into os.environ
    so that any code doing os.environ.get(...) also picks them up.
    """
    try:
        import streamlit as st
        for key, val in st.secrets.items():
            if isinstance(val, str) and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass
