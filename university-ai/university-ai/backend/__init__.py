"""Backend package — FastAPI + LangChain RAG pentru asistentul universitar."""

# ── Mod offline pentru Hugging Face (înainte de orice import HF) ──────────────
# Modelele (embeddings + reranker) se descarcă o singură dată și rămân în
# cache-ul local. Forțăm modul offline ca să NU se mai contacteze Hugging Face
# Hub la fiecare pornire. Sub Streamlit (reruns + cache_resource), clientul
# httpx din huggingface_hub poate fi închis și apoi reutilizat, provocând
# „RuntimeError: Cannot send a request, as the client has been closed".
# Acest __init__ rulează înainte ca `sentence_transformers`/`transformers` să
# fie importate (orice `from backend...` trece întâi pe-aici), deci variabilele
# sunt citite la timp de huggingface_hub.constants.
#
# Dezactivare (ex. pentru a descărca un model nou): setează în mediu
#   HF_HUB_OFFLINE=0  și  TRANSFORMERS_OFFLINE=0  (necesită internet).
import os as _os

_os.environ.setdefault("HF_HUB_OFFLINE", "1")
_os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

__version__ = "2.0.0"
