# 👤 OM 2: Motorul Determinist de Reguli (Art. 729 CPC), Validatoare & FastAPI Backend

## 1. Misiunea ta în echipă
Tu ești **garantul corectitudinii matematice și juridice** a platformei. Într-o bancă, LLM-ul nu are voie să facă adunări și împărțiri „din cap”. Tu deții **Motorul Determinist de Reguli** (`calculator.py` + `v2026_10.yaml`), validatoarele matematice (CNP, CUI, IBAN) și serverul **FastAPI** care leagă agenții lui Om1 de interfața lui Om4 și Om5.

---

## 2. Fișierele pe care lucrezi EXCLUSIV tu (Zero conflicte Git)

| Fișier | Ce conține acum (Schelet) | Ce trebuie să extinzi tu (TODO) |
| :--- | :--- | :--- |
| `backend/app/modules/popriri/rules/v2026_10.yaml` | Registrul de reguli YAML versionat (`R-EXEMPT-01` .. `R-CAP-08`) cu citarea articolelor din Codul de Procedură Civilă. | Verifică toate regulile, adaugă regula de prioritate între creditori (`R-PRIO-09`: întreținere > fiscal > comercial) și expune un endpoint `GET /api/rules` ca Frontend-ul să poată afișa registrul de reguli! |
| `backend/app/modules/popriri/engine/calculator.py` | Calculul determinist cu `Decimal` (fără `float`): sume exceptate, cota 1/3 și 1/2, plafon cumulat, plafon datorie. | Extinde alocarea pe mai mulți creditori (`CreditorAllocation`) când există popriri concurente (`S3`): distribuie suma disponibilă în ordinea de preferință legală. |
| `backend/app/core/validators.py` | Validatoare matematice pentru cifra de control CNP, CUI și IBAN (mod-97) + comparare nume fără diacritice. | Adaugă validare că IBAN-ul de consemnare aparține unei bănci/trezorerii din RO și extrage codul băncii din IBAN. |
| `backend/app/core/core_banking.py` | Portul `CoreBankingPort` + `CoreBankingMock` în memorie. | Adaugă suport pentru conturi multiple (RON + EUR cu conversie la curs BNR mock) sau conturi cu regim special (cont de garanție / escrow -> excepția `E08`). |
| `backend/app/main.py` | Serverul FastAPI cu endpoint-urile `/api/modules`, `/api/scenarios`, `/api/cases`, `/api/cases/{id}/review`, `/api/cases/{id}/stream`. | 1. Implementează `POST /api/cases/upload` (pentru încărcarea unui PDF live în timpul demo-ului).<br>2. Adaugă `GET /api/cases/{id}/response-pdf` (care cheamă generatorul lui Om3).<br>3. Adaugă `GET /api/metrics` (timp mediu procesare, % automatizare, sume protejate). |
| `backend/tests/test_calculator.py` | 2 teste unitare de bază. | Scrie **12–15 teste unitare cu `pytest`** care acoperă fiecare regulă din `v2026_10.yaml` (la pitch vei spune: *„Motorul determinist este validat de 15 teste unitare pe toate alineatele Art. 729 CPC”*). |

---

## 3. Contractul API pe care îl garantezi pentru Frontend (Om4 & Om5)

Nu schimba numele câmpurilor din `backend/app/contracts/` fără să te sincronizezi cu Om4/Om5!

| Metodă | Endpoint | Ce trimite Frontend-ul | Ce întoarce Backend-ul |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/modules` | — | `list[ModuleInfo]` (PopririZero `ACTIVE` + 4 module `ROADMAP`) |
| `GET` | `/api/scenarios` | — | `list[ScenarioInfo]` (`S1..S8`) |
| `GET` | `/api/cases` | — | `list[CaseSummary]` (pentru tabelul din Inbox) |
| `POST` | `/api/cases/from-scenario` | `{"scenario_id": "S1"}` | `Case` complet procesat |
| `POST` | `/api/cases/upload` | `multipart/form-data` (`file`) | `Case` complet procesat |
| `GET` | `/api/cases/{case_id}` | — | `Case` |
| `GET` | `/api/cases/{case_id}/events` | — | `list[AgentEvent]` (pașii agenților) |
| `POST` | `/api/cases/{case_id}/review` | `ReviewAction` (override-uri HITL) | `Case` recalculat instant |

---

## 4. Cum pornești serverul și testele

```bash
cd backend
python -m pip install -r requirements.txt
pytest tests/
uvicorn app.main:app --reload --port 8000
```
Deschide apoi `http://localhost:8000/docs` — ai toată documentația Swagger generată automat!
