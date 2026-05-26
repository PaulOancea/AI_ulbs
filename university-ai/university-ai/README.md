# 🎓 AI Universitar — Asistent virtual avansat pentru regulamente

Sistem **RAG (Retrieval-Augmented Generation)** de nivel enterprise, conceput pentru
a răspunde, **în limba română**, cu **ton academic** și **citare directă**, la
întrebări legate de regulamentele, procedurile administrative și informațiile
academice ale unei facultăți.

> **100% gratuit. Rulează local, fără internet, fără costuri API.**
> Folosește Ollama (LLM open-source) + sentence-transformers + ChromaDB.

---

## 📊 De ce „premium" și nu doar funcțional

| Capabilitate | RAG basic | **Sistemul nostru** |
|---|---|---|
| Retrieval | dense (embeddings) | **hibrid: BM25 + dense + RRF fusion** |
| Re-ranking | ❌ | ✅ **cross-encoder `BAAI/bge-reranker-v2-m3`** |
| Chunking | caracter-based | ✅ **legal-aware (recunoaște Art./Capitol/Secțiune)** |
| Memorie conversațională | ❌ | ✅ **ConversationBufferWindow + query rewriting** |
| **Suport PDF scanate + imagini** | ❌ | ✅ **OCR cu Tesseract (ron+eng), fallback automat** |
| **Autentificare utilizatori** | ❌ | ✅ **SQLite + bcrypt, register / login / logout** |
| **Istoric chat persistent** | ❌ | ✅ **chat-uri salvate în DB, sidebar cu listă completă** |
| **Limită guest** | ❌ | ✅ **3 întrebări fără cont, prompt automat la înregistrare** |
| **Multi-page UI** | ❌ | ✅ **Home → Login → Chat cu router custom** |
| Backend | monolit Streamlit | ✅ **FastAPI separat, WebSocket streaming** |
| Logging | `print()` | ✅ **Loguru, rotație zilnică, erori separate** |
| Error handling | excepții brute | ✅ **ierarhie de excepții cu mesaje în română** |
| Containerizare | ❌ | ✅ **Docker Compose (3 servicii)** |
| Testare | ❌ | ✅ **pytest + teste unitare** |
| Configurare | constante hard-coded | ✅ **Pydantic Settings + .env** |

---

## 🏗️ Arhitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                     STREAMLIT FRONTEND (premium)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / WebSocket
┌────────────────────────────▼────────────────────────────────────┐
│                       FASTAPI BACKEND                            │
│            /chat  /chat/stream  /documents  /health              │
└────────────────────────────┬────────────────────────────────────┘
                             │
       ┌─────────────────────┼──────────────────────┐
       ▼                     ▼                      ▼
┌─────────────┐     ┌────────────────┐    ┌────────────────┐
│ Conversation│     │   RAG CHAIN    │    │   Ingestie     │
│  Memory     │────▶│                │◀───│   docs         │
└─────────────┘     └───────┬────────┘    └────────┬───────┘
                            │                      │
              ┌─────────────┼──────────────┐       │
              ▼             ▼              ▼       ▼
       ┌──────────┐  ┌──────────┐  ┌──────────────────────┐
       │  Query   │  │ Retrieval│  │  Legal-aware         │
       │ Rewriter │  │  Hybrid  │  │  Chunker             │
       └──────────┘  │  BM25 +  │  └──────────┬───────────┘
                     │  Dense   │             │
                     └────┬─────┘             ▼
                          │           ┌──────────────────┐
                          ▼           │  ChromaDB        │
                  ┌──────────────┐   │  (persistent)    │
                  │ Cross-Encoder│◀──┤                  │
                  │  Re-ranker   │   └──────────────────┘
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ Ollama LLM   │
                  │ (streaming)  │
                  └──────────────┘
```

---

## 📁 Structura proiectului

```
university-ai/
├── backend/                       Backend Python (FastAPI + RAG)
│   ├── main.py                    Aplicația FastAPI (entry point)
│   ├── config.py                  Configurație Pydantic Settings
│   ├── logging_config.py          Loguru setup (rotație + fișier erori)
│   ├── schemas.py                 Modele Pydantic (request/response)
│   ├── exceptions.py              Excepții custom cu mesaje în RO
│   ├── auth/                      Autentificare + istoric chat
│   │   ├── database.py            SQLite schema (users/chats/messages)
│   │   └── service.py             Register / login / chat CRUD cu bcrypt
│   ├── core/
│   │   ├── loaders.py             Extracție PDF/DOCX/TXT/imagini + OCR fallback
│   │   ├── ocr.py                 Motor OCR (Tesseract + pypdfium2)
│   │   ├── chunker.py             Chunking legal-aware (Art./Capitol)
│   │   ├── vector_store.py        Wrapper ChromaDB + embeddings
│   │   ├── retriever.py           Retrieval hibrid (BM25 + dense + RRF)
│   │   ├── reranker.py            Cross-encoder re-ranking
│   │   ├── memory.py              ConversationBufferWindowMemory
│   │   ├── prompts.py             System prompts în română
│   │   ├── llm.py                 Wrapper Ollama (sync + async stream)
│   │   ├── ingestion.py           Pipeline complet de indexare
│   │   └── rag_chain.py           Orchestrator pipeline complet
│   └── api/
│       ├── chat.py                /chat + /chat/stream (WebSocket)
│       ├── documents.py           /documents (upload, listare)
│       └── health.py              /health (status componente)
│
├── frontend/                      UI Streamlit multi-pagină
│   ├── streamlit_app.py           ROUTER principal (home/login/chat)
│   ├── components/
│   │   ├── styles.py              CSS premium partajat
│   │   └── session.py             Helpers session_state (auth, navigare)
│   └── views/
│       ├── home.py                Landing page modernă (hero + features)
│       ├── auth.py                Login + Register
│       └── chat.py                Chat cu istoric persistent + sidebar
│
├── scripts/
│   └── ingest.py                  CLI pentru ingestie batch
│
├── tests/
│   ├── test_chunker.py
│   └── test_memory.py
│
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
│
├── documente/                     Aici pui regulamentele (PDF/DOCX/imagini)
├── data/
│   ├── chroma_db/                 Baza vectorială (auto-generată)
│   ├── app.db                     SQLite (users + chat history)
│   └── logs/                      Loguri rotative
│
├── app.py                         Entry point legacy (shim)
├── requirements.txt
├── .env.example                   Exemplu configurație
├── Makefile                       Comenzi rapide
└── README.md                      Acest fișier
```

---

## ⚙️ Instalare locală (3 pași)

### Pasul 1 — Ollama (LLM local, gratuit)

Descarcă și instalează de la **https://ollama.com**.

Apoi, în terminal:
```bash
ollama serve                      # rulează serverul (lasă deschis)
ollama pull llama3.1:8b           # descarcă modelul (~5 GB)
```

> 💡 **RAM < 8 GB?** Folosește `mistral:7b` sau `qwen2.5:7b`.
> 💡 **Ai GPU?** Modelele rulează automat pe GPU, mult mai rapid.

### Pasul 2 — Python + dependențe

Necesită Python 3.10+:
```bash
cd university-ai
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

pip install -r requirements.txt
```

⏳ Prima instalare durează 3–5 minute (torch ~2 GB).

### Pasul 2.5 — Tesseract OCR (opțional, pentru PDF-uri scanate)

Dacă vrei să suporți **PDF-uri scanate** (poze) și **upload de imagini** (PNG/JPG/TIFF):

**Windows:**
1. Descarcă de la [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. La instalare bifează limba **Romanian** (foarte important!)
3. Calea implicită: `C:\Program Files\Tesseract-OCR\tesseract.exe`
4. (Opțional) Adaugă în `.env`:
   ```
   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

**Linux:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-ron
```

**Mac:**
```bash
brew install tesseract tesseract-lang
```

> ✨ Dacă Tesseract NU e instalat, aplicația funcționează normal — doar că PDF-urile
> scanate vor fi sărite (cu un warning clar în log-uri). Nu e blocant.

### Pasul 3 — Configurare (opțional)

```bash
cp .env.example .env
# Editează .env pentru a schimba modelul, top-k, etc.
```

---

## 🚀 Rulare

### Modul A — Doar frontend (Streamlit, fără API)

Cel mai simplu pentru demo:

```bash
streamlit run frontend/streamlit_app.py
# sau echivalent:
streamlit run app.py
```

Browserul se deschide automat la **http://localhost:8501**.

### Modul B — Backend + frontend separate

Pentru o arhitectură reală, scalabilă:

**Terminal 1** — Ollama:
```bash
ollama serve
```

**Terminal 2** — Backend FastAPI:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3** — Frontend Streamlit:
```bash
streamlit run frontend/streamlit_app.py
```

API docs disponibile la **http://localhost:8000/docs** (Swagger UI).

### Modul C — Docker (un singur pas)

```bash
cd docker
docker compose up -d --build

# Descarcă modelul în Ollama (o singură dată)
docker compose exec ollama ollama pull llama3.1:8b
```

Apoi accesezi:
- Frontend: **http://localhost:8501**
- API: **http://localhost:8000/docs**

---

## 🔐 Sistem utilizatori

Aplicația suportă **3 moduri de utilizare**:

### Mod invitat (guest)
- **3 întrebări gratuite** fără cont (limită configurabilă în `.env`)
- Nu se păstrează istoricul
- Memorie conversațională activă doar în timpul sesiunii

### Cont înregistrat
- **Întrebări nelimitate**
- **Istoric chat persistent** — toate conversațiile salvate în SQLite
- Sidebar cu lista chat-urilor (click pentru re-deschidere)
- Posibilitatea de a șterge conversații individual
- Memorie conversațională reluată automat la încărcarea unui chat vechi

### Creare cont
- **Username**: 3-32 caractere (litere, cifre, `_`, `.`, `-`)
- **Email**: validat regex
- **Parolă**: minim 6 caractere (configurabil), stocată **bcrypt-hashed**
- **Autologin** automat după înregistrare

Toate parolele sunt hashed cu **bcrypt** (work factor 12, salt aleator). Baza
de date e SQLite la `data/app.db` cu CASCADE delete (ștergerea unui user
șterge automat chat-urile și mesajele asociate).

---

## 📚 Adăugarea documentelor

### Formate suportate

| Format | Suport | Mecanism |
|---|---|---|
| `.pdf` (text nativ) | ✅ | `pdfplumber` — extracție rapidă |
| `.pdf` (scanat / imagini) | ✅ | **OCR automat** cu `pypdfium2` + `pytesseract` |
| `.docx`, `.doc` | ✅ | `python-docx` (paragrafe + tabele) |
| `.txt` | ✅ | Detectare automată encoding |
| `.png`, `.jpg`, `.jpeg` | ✅ | **OCR direct** (necesită Tesseract) |
| `.tiff`, `.tif`, `.bmp` | ✅ | **OCR direct** |

**Pipeline OCR automat:**
1. PDF nativ → `pdfplumber` extrage textul rapid
2. Pagini fără text (sub `OCR_MIN_TEXT_THRESHOLD=50` caractere) → rasterizate la 300 DPI
3. Tesseract OCR cu limbile `ron+eng` → extrage textul
4. Fragmentele marcate cu badge `OCR` în UI

### Trei moduri de încărcare

**1. Upload prin UI** — Sidebar (în chat) → secțiunea „📂 Adaugă documente" → selectează fișiere → „Indexează".

**2. Folder pe disc** — pune fișierele în `documente/`:
```bash
make ingest
# sau
python -m scripts.ingest
```

**3. API (programatic)**
```bash
curl -X POST http://localhost:8000/documents/folder?folder=./documente
```

---

## 🧪 Testare

```bash
make test
# sau
pytest tests/ -v
```

---

## 🎯 Cum funcționează (sub capotă)

### 1. Chunking inteligent

Spre deosebire de chunking-ul cu split la caracter, sistemul nostru:
- detectează „Articolul 17", „Capitolul II", „Secțiunea 3";
- păstrează un articol întreg într-un singur chunk dacă încape;
- atașează eticheta articolului ca metadată (afișată în UI).

### 2. Retrieval hibrid (Reciprocal Rank Fusion)

```
                 Întrebare
                     │
       ┌─────────────┴─────────────┐
       ▼                            ▼
  Dense (semantic)             BM25 (lexical)
  Top-20 candidați             Top-20 candidați
       │                            │
       └──────────┬─────────────────┘
                  ▼
            RRF Fusion (α=0.5)
                  │
                  ▼
       Top-20 candidați unificați
                  │
                  ▼
       Cross-Encoder Re-ranking
                  │
                  ▼
        Top-5 fragmente → LLM
```

**De ce hibrid?**
- Dense excelează la întrebări parafrazate ("regula promovării" → "condiții de promovare").
- BM25 excelează la potriviri exacte ("Art. 17", "Legea nr. 1/2011", cifre).
- Combinația acoperă ambele scenarii.

### 3. Memorie conversațională cu query rewriting

```
[Schimb 1]
Student: Care e media minimă pentru promovare?
Bot:    Conform Art. 12, media minimă este 5.

[Schimb 2]
Student: Dar pentru burse?
         ↓
[Query rewriter detectează „Dar pentru" → contextual]
         ↓
Reformulează → "Care este media minimă pentru obținerea unei burse?"
         ↓
Retrieval pe întrebarea reformulată.
```

### 4. Logging structurat

Toate evenimentele importante sunt logate:
- în consolă (colorat, dev-friendly);
- în `data/logs/app_YYYY-MM-DD.log` (rotație zilnică, compresie ZIP, retenție 14 zile);
- erori separat în `data/logs/errors_YYYY-MM-DD.log`.

---

## ⚙️ Configurare avansată

Toate setările sunt în `.env` (vezi `.env.example`):

| Variabilă | Implicit | Descriere |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.1:8b` | Modelul LLM |
| `EMBED_MODEL` | `paraphrase-multilingual-mpnet-base-v2` | Embeddings |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-encoder |
| `RERANKER_ENABLED` | `true` | Activare rerank |
| `CHUNK_SIZE` | `900` | Mărimea unui fragment |
| `CHUNK_OVERLAP` | `150` | Suprapunere între fragmente |
| `CHUNK_LEGAL_AWARE` | `true` | Detectare Art./Capitol |
| `RETRIEVAL_TOP_K` | `20` | Câți candidați (per retriever) |
| `FINAL_TOP_K` | `5` | Câți merg la LLM după rerank |
| `HYBRID_ALPHA` | `0.5` | 0=BM25 pur, 1=dense pur |
| `MEMORY_WINDOW` | `6` | Câte schimburi reține în memorie |
| `MEMORY_ENABLED` | `true` | Activare memorie |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |

---

## ❓ Probleme frecvente

**„Ollama nu rulează"**
→ Pornește `ollama serve` în terminal și lasă-l deschis.

**„Modelul nu e instalat"**
→ `ollama pull llama3.1:8b` (sau modelul dorit).

**Răspunsuri lente (>30s)**
→ Folosește `mistral:7b` sau `qwen2.5:7b`. Pe CPU obișnuit, e normal 10–30s.

**PDF scanat (fără text extras)**
→ PDF-urile scanate (imagini) necesită OCR — folosește `tesseract` separat.

**Eroare la `pip install torch`**
→ `pip install torch --index-url https://download.pytorch.org/whl/cpu`

**Reranker-ul descarcă ~570 MB la prima utilizare**
→ Normal. Setează `RERANKER_ENABLED=false` în `.env` pentru a-l dezactiva (acuratețe mai mică).

---

## 🤝 Contribuții

Acest proiect a fost dezvoltat ca parte a unui proiect de facultate. Pentru a contribui:
1. Fork.
2. Branch nou: `git checkout -b feature/nume`.
3. Commit + push + Pull Request.

---

## 📜 Licență

Cod sursă — MIT. Documentele indexate rămân proprietatea instituției respective.
