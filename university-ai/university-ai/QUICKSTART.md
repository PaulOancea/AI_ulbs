# ⚡ Quickstart — pornire în 5 minute

> Acest ghid e versiunea condensată. Pentru detalii complete, vezi `README.md`.

---

## Varianta 1 — Cu Docker (recomandat pentru demo)

```bash
# 1. Pornește tot stack-ul (Ollama + Backend + Frontend)
cd docker
docker compose up -d --build

# 2. Descarcă modelul LLM o singură dată (~5 GB)
docker compose exec ollama ollama pull llama3.1:8b

# 3. Pune fișierele PDF/DOCX în folderul ../documente/, apoi indexează:
docker compose exec backend python -m scripts.ingest

# 4. Deschide în browser:
#    Frontend chat:  http://localhost:8501
#    API docs:       http://localhost:8000/docs
```

Oprire:
```bash
docker compose down
```

---

## Varianta 2 — Local, fără Docker

### Pasul 1: Ollama (LLM)

Descarcă de la [ollama.com](https://ollama.com) și instalează. Apoi:

```bash
ollama serve            # Terminal 1 — lasă deschis
ollama pull llama3.1:8b # Terminal 2 — o singură dată
```

### Pasul 2: Python + dependențe

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Linux/Mac

pip install -r requirements.txt
```

### Pasul 3: Indexează documente

Pune PDF-urile/DOCX-urile cu regulamentele în `documente/`, apoi:

```bash
python -m scripts.ingest
```

Așteaptă să termine indexarea (1–3 minute prima dată — descarcă modelele
de embeddings + reranker, ~1 GB).

### Pasul 4: Pornește interfața

```bash
streamlit run frontend/streamlit_app.py
```

Se deschide automat **http://localhost:8501** în browser.

### Opțional: pornește și backend-ul API

```bash
# Terminal 3 (paralel cu Streamlit)
uvicorn backend.main:app --reload
```

API docs interactive: **http://localhost:8000/docs**

---

## ✅ Verificare că totul funcționează

1. **Pagina home** se deschide la `http://localhost:8501` — vezi hero modern + stats live.
2. Click **🚀 Începe conversația** sau **🔐 Autentificare** (creează un cont).
3. În chat, sidebar trebuie să arate: **● Ollama activ** și **● N documente**.
4. Scrie: *„Care sunt condițiile de promovare?"*
5. Răspunsul trebuie să apară în română, cu **citare la articol/pagina** și
   **badge-uri cu sursele** dedesubt.

### Test rapid cele 4 funcționalități noi

| Test | Cum | Rezultat așteptat |
|---|---|---|
| **Home modernă** | Deschide app | Hero gradient + cards + stats — NU intri direct în chat |
| **Limită guest** | Fără login, întreabă de 3 ori | Chat-ul se dezactivează după a 3-a, apare buton „Creează cont" |
| **Auth + istoric** | Creează cont → întreabă ceva → New chat → reîncarcă vechiul | Conversațiile rămân salvate în sidebar |
| **OCR poze** | Upload o poză `.jpg` cu text scris pe ea | Textul e extras și indexat (necesită Tesseract) |
| **OCR PDF scanat** | Upload un PDF scanat | Text extras automat, fragmentele apar cu badge `OCR` |

---

## 🆘 Probleme rapide

| Eroare | Soluție |
|---|---|
| `Ollama nu este pornit` | În terminal: `ollama serve` |
| `Modelul nu e instalat` | `ollama pull llama3.1:8b` |
| `ImportError: backend.config` | Rulezi din rădăcina proiectului? `cd university-ai` |
| Răspunsuri lente | Trece la model mai mic: `ollama pull qwen2.5:7b` și schimbă în `.env` |
| `torch` install eșuează | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |

---

## 🎯 Întrebări demo (pentru evaluator)

Folosește aceste exemple pentru a testa diferite capabilități:

| Întrebare | Ce demonstrează |
|---|---|
| „Care e media minimă pentru promovare?" | Retrieval semantic + citare |
| „Conform Art. 17, ce drepturi am?" | **BM25 lexical** — potrivire exactă |
| „Dar pentru burse?" *(după o întrebare precedentă)* | **Memorie conversațională** + query rewriting |
| „How are exams contested?" *(în engleză)* | **Constrângerea de limbă** — răspuns tot în română |
| „Câte zile am la dispoziție pentru contestație?" | Acuratețe numerică din regulament |
| „Care e capitala Franței?" | Refuz politicos — nu e în domeniu |

---

## 🏗️ Ce e impresionant tehnic (pentru profesor)

- **Retrieval hibrid RRF**: combină BM25 lexical + embeddings dense
  (`paraphrase-multilingual-mpnet-base-v2`) prin Reciprocal Rank Fusion.
- **Re-ranking cu cross-encoder**: `BAAI/bge-reranker-v2-m3` (SOTA multilingv).
- **Chunking legal-aware**: detectează automat „Art. X", „Capitolul Y" și
  păstrează articolele întregi în același chunk.
- **Memorie conversațională + query rewriting**: întrebări tip „Dar pentru anul II?"
  sunt automat reformulate complet folosind contextul anterior.
- **Streaming real-time**: token-cu-token prin WebSocket (FastAPI) sau
  generator clasic (Streamlit).
- **Logging profesional**: Loguru cu rotație zilnică + fișier separat pentru erori.
- **Containerizare**: stack complet cu `docker compose up`.
- **Type safety**: Pydantic Settings pentru config + Pydantic models pentru API.
