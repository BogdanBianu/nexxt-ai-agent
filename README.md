# LexOps — Platformă Multi-Agent pentru Operațiuni Juridice Bancare
## Modulul 1 (MVP): **PopririZero** (Procesarea și Reconcilierea Autonomă a Popririlor)

Proiect dezvoltat pentru **Raiffeisen Bank — VibeHack / nexxt (AI for Operational Efficiency)**.

---

## 🧭 Cum începem lucrul în echipă (5 Oameni)

Fiecare membru al echipei are propriul său ghid detaliat (cu fișierele pe care lucrează exclusiv, contractul de date și checklist-ul pe ore):

* 👉 **[om1/README.md](om1/README.md)** — **Om 1:** Arhitect Agenți AI, LangGraph & Integrare Featherless.ai
* 👉 **[om2/README.md](om2/README.md)** — **Om 2:** Motorul Determinist de Reguli (Art. 729 CPC), Validatoare & FastAPI Backend
* 👉 **[om3/README.md](om3/README.md)** — **Om 3:** Inginer Date Sintetice, Scenarii Juridice (`S1..S8`) & Fabrica de PDF-uri
* 👉 **[om4/README.md](om4/README.md)** — **Om 4:** Frontend Lead — Dashboard LexOps, Vizualizare Live Agenți & Disecție Extras
* 👉 **[om5/README.md](om5/README.md)** — **Om 5:** Workbench HITL (Human-in-the-Loop), QA Scenarii & Pitch Deck Raiffeisen

---

## 🔒 Sursa Unică de Adevăr: Contractul de Date

Toată echipa comunică prin modelele definite în:
* **Backend (Pydantic):** `backend/app/contracts/` (`enums.py`, `documents.py`, `banking.py`, `decision.py`, `case.py`, `scenario.py`, `api.py`)
* **Frontend (TypeScript):** `frontend/src/types/contracts.ts`

> **REGULĂ DE ECHIPĂ:** Nimeni nu redenumește un câmp sau o valoare de `Enum` din `contracts` fără să anunțe pe grup și să actualizeze ambele fișiere (`backend/app/contracts/` + `frontend/src/types/contracts.ts`) în același commit!

---

## ⚡ Quickstart (În 2 minute aveți totul pornit)

### 1. Configurare Python & Pornire Backend
```bash
# Din rădăcina repo-ului (lexops/)
cp .env.example .env
# (Opțional) Puneți cheia FEATHERLESS_API_KEY în .env.
# Fără cheie, sistemul rulează automat pe fallback-ul determinist!

pip install -r backend/requirements.txt

# Verifică că scenariile de bază (S1 și S4) trec end-to-end:
python scripts/run_scenarios.py

# Rulează testele unitare pe motorul de calcul:
pytest backend/tests

# Pornește serverul FastAPI pe http://localhost:8000 (Swagger UI la http://localhost:8000/docs):
cd backend
uvicorn app.main:app --reload --port 8000
```

### 2. Structura Proiectului
```text
lexops/
├── om1/README.md                 # Specificații & TODO pentru Om 1 (Agenți & LLM)
├── om2/README.md                 # Specificații & TODO pentru Om 2 (Motor Reguli & FastAPI)
├── om3/README.md                 # Specificații & TODO pentru Om 3 (Scenarii S1..S8 & PDF-uri)
├── om4/README.md                 # Specificații & TODO pentru Om 4 (Frontend Dashboard & Graf)
├── om5/README.md                 # Specificații & TODO pentru Om 5 (Workbench HITL & Pitch)
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── config.py             # Configurare centrală (.env)
│   │   ├── main.py               # FastAPI Server + SSE Streaming (Om 2)
│   │   ├── contracts/            # CONTRACTUL DE DATE PYDANTIC (Sursa unică de adevăr)
│   │   ├── core/                 # Nucleul platformei LexOps (Router, LLM, Validatoare, CoreBankingMock)
│   │   └── modules/
│   │       └── popriri/          # Modulul PopririZero (Reguli YAML, Calculator, Agenți, Graf LangGraph)
│   └── tests/                    # Teste unitare pytest (Om 2)
├── data/
│   ├── payers_registry.json      # Registrul de plătitori cunoscuți (ANPIS, Casa de Pensii etc.) (Om 3)
│   └── scenarios/                # Scenariile sintetice S1.json .. S8.json (Om 3)
├── frontend/
│   └── src/
│       ├── types/contracts.ts    # CONTRACTUL DE DATE TYPESCRIPT (Om 4 & Om 5)
│       └── api/client.ts         # Client HTTP către FastAPI (Om 4 & Om 5)
└── scripts/
    ├── run_scenarios.py          # Verificare automată a scenariilor S1..S8 (Om 5 / Om 3)
    └── generate_pdfs.py          # Generator PDF-uri adrese executori & răspuns bancă (Om 3)
```
