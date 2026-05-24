"""
Streamlit entry point — run: streamlit run app.py
(Render and start_ui.bat use this file at the project root.)
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ui.app  # noqa: F401 — registers the Streamlit UI
