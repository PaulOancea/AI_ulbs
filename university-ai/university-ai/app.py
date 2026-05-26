"""
app.py  —  Punct de intrare clasic (backwards-compatible).

Aplicația a fost restructurată în pachete (backend/, frontend/), însă păstrăm
acest fișier pentru a putea rula cu comanda originală:

    streamlit run app.py

Ce face: importă și execută conținutul frontend/streamlit_app.py.
"""

import runpy
from pathlib import Path

# Echivalent cu `streamlit run frontend/streamlit_app.py`
STREAMLIT_APP = Path(__file__).parent / "frontend" / "streamlit_app.py"
runpy.run_path(str(STREAMLIT_APP), run_name="__main__")
