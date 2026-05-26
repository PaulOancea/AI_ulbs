# ──────────────────────────────────────────────────────────────────────────────
#  Makefile — comenzi rapide de dezvoltare
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help install run-frontend run-backend run-ollama ingest test \
        docker-up docker-down docker-logs clean

help:
	@echo ""
	@echo "  AI Universitar — comenzi disponibile:"
	@echo ""
	@echo "  make install         — instalează dependențele Python"
	@echo "  make run-ollama      — pornește serverul Ollama (în prim-plan)"
	@echo "  make run-backend     — pornește FastAPI (uvicorn cu reload)"
	@echo "  make run-frontend    — pornește interfața Streamlit"
	@echo "  make ingest          — indexează documentele din ./documente"
	@echo "  make test            — rulează testele cu pytest"
	@echo "  make docker-up       — pornește tot stack-ul Docker"
	@echo "  make docker-down     — oprește stack-ul Docker"
	@echo "  make docker-logs     — vizualizează loguri Docker"
	@echo "  make clean           — șterge cache + chroma_db"
	@echo ""

install:
	pip install --upgrade pip
	pip install -r requirements.txt

run-ollama:
	ollama serve

run-backend:
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

run-frontend:
	streamlit run frontend/streamlit_app.py

ingest:
	python -m scripts.ingest

test:
	pytest tests/ -v

docker-up:
	cd docker && docker compose up -d --build

docker-down:
	cd docker && docker compose down

docker-logs:
	cd docker && docker compose logs -f

clean:
	rm -rf __pycache__ .pytest_cache
	rm -rf backend/__pycache__ backend/**/__pycache__
	rm -rf data/chroma_db data/logs
	@echo "Cache + DB șterse."
