"""
Streamlit entry point — run: streamlit run app.py

Streamlit Cloud and Render expect app.py at the repo root. The UI lives in
ui/app.py; we execute it here so Streamlit owns the script run (import-only
wrappers break on Cloud).
"""
from pathlib import Path
import runpy

_UI_APP = Path(__file__).resolve().parent / "ui" / "app.py"
runpy.run_path(str(_UI_APP), run_name="__main__")
