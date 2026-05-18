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
    Handles both flat keys ("KEY = value") and nested TOML sections ([section] KEY = value).
    """
    try:
        import streamlit as st

        def _flatten(mapping, prefix=""):
            for k, v in mapping.items():
                full_key = f"{prefix}{k}" if not prefix else f"{prefix}_{k}"
                if isinstance(v, str):
                    if full_key not in os.environ:
                        os.environ[full_key] = v
                    # Also inject without prefix for top-level keys
                    if not prefix and k not in os.environ:
                        os.environ[k] = v
                elif hasattr(v, "items"):
                    _flatten(v, prefix=k.upper() + "_" if not prefix else prefix + k.upper() + "_")

        _flatten(st.secrets)
    except Exception:
        pass
