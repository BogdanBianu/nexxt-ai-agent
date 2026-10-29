# LexOps — agenți AI pentru Operațiuni Juridice Bancare

Proiect dezvoltat pentru **Raiffeisen Bank — VibeHack / nexxt (AI for Operational Efficiency)**.

O bancă primește zilnic documente juridice: adrese de poprire de la executori și ANAF, sechestre, notificări de insolvență, certificate de moștenitor, cereri GDPR, solicitări de la Poliție și Parchet. Fiecare cere ca un ofițer să citească documentul, să găsească clientul, să analizeze conturile și să aplice legea, în medie 15 minute pe dosar.

**LexOps** face această muncă cu o echipă de agenți AI: clasifică documentul, extrage datele, identifică clientul, aplică regulile legale (cu articolul de lege citat) și redactează răspunsul băncii. **Agenții nu decid singuri**: un dosar conform este doar propus, iar un angajat îl aprobă sau îl respinge.

---

## Module

| Modul | Documente | Ce face |
|---|---|---|
| **PopririZero** | înființare, sistare, modificare poprire | Calculează cât se poate bloca conform CPC art. 729 (venituri protejate, cota de 1/3 din salariu, popriri concurente) și emite instrucțiunile de blocare |
| **Sechestre asigurătorii** | instituire / ridicare sechestru | Indisponibilizează sume în limita plafonului măsurii (fiscal art. 213 CPF, civil art. 952 CPC, penal art. 249 CPP) |
| **Insolvență și succesiuni** | notificare insolvență, certificat de moștenitor | Suspendă popririle (Legea 85/2014 art. 75), marchează conturile, împarte soldul defunctului pe cotele moștenitorilor |
| **Cereri GDPR** | acces, ștergere, opoziție, portabilitate, ANSPDCP | Inventariază datele clientului, aplică excepțiile legale (păstrare AML 5 ani / contabilitate 10 ani) și redactează răspunsul DPO |
| **Cereri autorități** | solicitări Poliție, Parchet, DNA, DIICOT | Identifică persoana și pregătește datele comunicate în dosarul penal |

Un **Intake Router** comun clasifică orice document (cuvinte cheie, apoi LLM ca rezervă) și îl trimite la modulul potrivit.

## Cum funcționează un dosar

```
Document (PDF / text)
  → INTAKE_ROUTER      tipul documentului și modulul
  → EXTRACTION         emitent, debitor, CNP/CUI, sume, număr de dosar (regex + LLM)
  → RECONCILIATION     clientul și conturile lui din Core Banking
  → INCOME_CLASSIFIER  natura fiecărei încasări (salariu, alocație, pensie...)
  → RULE_ENGINE        regulile legale versionate (YAML), cu temeiul legal
  → ANOMALY            situații suspecte (ex. salariu deghizat în diurnă)
  → OUTCOME            decizia propusă și adresa de răspuns
  → angajat            Aprobă / Respinge (ultimul cuvânt e al omului)
```

- **Conform criteriilor** → statusul `PENDING_APPROVAL` („Conform, de aprobat”). Nu se blochează nimic și nu pleacă niciun răspuns până la aprobare.
- **Problemă găsită** → statusul `EXCEPTION_FLAGGED`, cu un cod (E01 debitor neidentificat … E09 cont de consemnare suspect). Ofițerul o rezolvă în Workbench-ul HITL, iar agenții refac calculul.
- **Aprobat** → `AUTO_PROCESSED` (sau `LIFTED` la sistări): se emite blocarea și se poate descărca adresa de răspuns.
- **Respins** → `REJECTED`, cu motiv obligatoriu.

Fiecare pas (agent, regulă, decizie umană) intră în **jurnalul de audit**, exportabil CSV.

## Tehnologii

- **Backend:** Python, FastAPI, Pydantic v2, LangGraph, AWS Bedrock (Amazon Nova Pro, cu modele de rezervă), PyMuPDF, ReportLab
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4
- **Fără AI disponibil**, platforma merge mai departe pe reguli deterministe: orice apel LLM are o rezervă fără AI.

---

## Pornire rapidă

### 1. Backend (http://localhost:8000, documentație Swagger la `/docs`)

```bash
cp .env.example .env            # apoi completează credențialele AWS Bedrock (vezi „De unde iei cheile AWS”)
python -m venv .venv
.venv\Scripts\activate          # Windows; pe macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (http://localhost:5173)

```bash
cd frontend
npm install
npm run dev
```

Adresa backend-ului se poate schimba cu `VITE_API_BASE_URL` (implicit `http://localhost:8000`).

### 3. Verificare

```bash
# din rădăcina repo-ului
python scripts/run_scenarios.py     # cele 26 de scenarii demo, end-to-end
cd backend && pytest                 # testele backend-ului
cd frontend && npx tsc --noEmit      # verificarea tipurilor din frontend
```

Pentru rulări rapide și offline, setează `USE_LLM=off`.

## Configurare (`.env`)

| Variabilă | Rol |
|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_DEFAULT_REGION` | Credențiale AWS Bedrock. Cele temporare (cu `SESSION_TOKEN`) expiră după câteva ore |
| `LLM_MODEL` | Modelul Bedrock (implicit `us.amazon.nova-pro-v1:0`) |
| `USE_LLM` | `auto` = folosește LLM dacă există credențiale; `off` = doar reguli deterministe |
| `USD_EUR_RATE`, `OFFICER_MINUTES_PER_CASE`, `OFFICER_HOURLY_COST_EUR` | Presupunerile pentru calculul de ROI din pagina de statistici |

> `.env` conține chei secrete și este exclus din git. Nu îl urca și nu îl trimite nimănui.

### De unde iei cheile AWS

1. Intră pe [dashboard-ul AWS Workshop](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US/workshop).
2. Apasă butonul **Get AWS CLI credentials**.
3. Copiază valorile `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` și `AWS_SESSION_TOKEN` în `.env`, fără `export` și fără ghilimele (ex. `AWS_ACCESS_KEY_ID=ASIA...`).
4. Repornește backend-ul: cheile se citesc doar la pornire.

Cheile sunt temporare și expiră după câteva ore. Când agenții încep să meargă doar pe reguli și în log apare `ExpiredTokenException`, ia chei noi de la același buton.

---

## Scenarii demo

Scenariile sintetice din `data/scenarios/` (document + situația din bancă + rezultatul așteptat) acoperă toate modulele. Câteva reprezentative:

| Scenariu | Ce arată |
|---|---|
| **S1** | Salariat cu alocație: se blochează doar partea legală, alocația rămâne protejată |
| **S4** | Salariu deghizat în „diurnă” după poprire: agentul semnalează eludarea |
| **S7** | Sistare după achitarea datoriei: poprirea se ridică |
| **S8** | Solicitare de la Poliție: rutată la modulul Cereri autorități |
| **S17–S20** | Sechestre fiscal, civil, penal și ridicarea lor |
| **S21–S24** | Succesiuni (împărțire pe moștenitori) și insolvență / faliment |
| **S25–S26** | GDPR: cerere de acces și cerere de ștergere refuzată parțial (AML) |

PDF-urile pentru S1–S24 sunt în `data/pdfs/` și se pot încărca direct din interfață (individual sau în lot); orice scenariu se poate rula și prin `POST /api/cases/from-scenario`.

### Cazuri de test pentru drag & drop

Folderul [`cazuri-test-drag-and-drop/`](cazuri-test-drag-and-drop/) are 4 PDF-uri fictive, gata de tras în căsuța de încărcare de pe pagina de start, ca să vezi încărcarea în lot și agenții lucrând live:

| Fișier | Ce este | Ce face LexOps |
|---|---|---|
| `CASE-UP-751EE2_S5.pdf` | Înființare poprire, Ionescu Mihai, 8.000 RON | Oprește dosarul: CNP-ul din adresă e invalid (E01, debitor neidentificat) |
| `CASE-UP-0776DA_S6.pdf` | Înființare poprire, Dragomir Vasile, 22.000 RON | Oprește dosarul: poprirea există deja pe același dosar de executare (E02, duplicat) |
| `CASE-UP-769E88_S7.pdf` | Sistare poprire, Stănescu Andrei | Conform: propune ridicarea popririi, de aprobat |
| `CASE-UP-0898DF_S8.pdf` | Cerere de informații de la Poliție (dosar penal) | Rutată la Cereri autorități, conformă, de aprobat |

Selectează toate cele 4 fișiere și trage-le în căsuță: agenții le iau pe rând, iar dosarele apar în tabelul „Toate dosarele”. Numele fișierelor trebuie să păstreze sufixul `_S5`, `_S6` etc., pentru că din el aplicația știe ce client fictiv (scenariu) să folosească. Toate datele (nume, CNP-uri, IBAN-uri, dosare) sunt inventate.

## API (principalele endpoint-uri)

| Metodă | Endpoint | Rol |
|---|---|---|
| `POST` | `/api/cases/upload` | Încarcă un PDF / .txt și rulează agenții |
| `POST` | `/api/cases/from-scenario` | Rulează un scenariu demo |
| `GET` | `/api/cases`, `/api/cases/{id}` | Lista dosarelor, dosarul complet |
| `GET` | `/api/cases/{id}/events`, `/stream` | Evenimentele agenților (SSE pentru animația live) |
| `POST` | `/api/cases/{id}/review` | Decizia ofițerului pe o problemă (HITL) → recalculare |
| `POST` | `/api/cases/{id}/approve`, `/reject` | Decizia finală a angajatului |
| `GET` | `/api/cases/{id}/audit`, `/response-pdf` | Jurnalul de audit, adresa de răspuns (doar după aprobare) |
| `GET` | `/api/metrics` | KPI-uri, telemetrie AI (apeluri, tokeni, cache, cost) și ROI |
| `GET` | `/api/modules`, `/api/scenarios`, `/api/rules` | Modulele, scenariile, registrul de reguli |

## Structura proiectului

```text
backend/
  app/
    main.py              FastAPI: endpoint-uri, stocarea dosarelor, aprobare, metrici
    contracts/           Contractul de date Pydantic (sursa unică de adevăr)
    core/                Router, client LLM (Bedrock), telemetrie, LangGraph comun, validatoare
    modules/
      popriri/           PopririZero: agenți, motor de reguli, reguli YAML
      sechestre/         Sechestre asigurătorii
      insolventa/        Insolvență și succesiuni
      gdpr/              Cereri GDPR
      autoritati/        Cereri autorități
  tests/                 Teste pytest
frontend/src/
  types/contracts.ts     Oglinda TypeScript a contractului de date
  api/client.ts          Client HTTP către FastAPI
  components/            Pagini și panouri (listă dosare, agenți live, HITL, aprobare, statistici)
cazuri-test-drag-and-drop/  4 PDF-uri fictive (S5–S8) pentru încărcarea în lot din interfață
data/
  scenarios/             Scenariile S1–S26
  pdfs/                  PDF-urile demo
scripts/
  run_scenarios.py       Verificarea automată a scenariilor
  generate_pdfs.py       Generatorul de PDF-uri (documente primite și răspunsuri)
```

**Regulă de echipă:** orice schimbare în `backend/app/contracts/` se face în același commit și în `frontend/src/types/contracts.ts`.

## Echipa

Proiect realizat de o echipă de 5 persoane: agenți AI și LangGraph, motor de reguli și backend, date sintetice și PDF-uri, frontend, Workbench HITL și pitch.

> Temeiurile legale din reguli sunt pentru demonstrație și trebuie validate de un jurist înainte de orice utilizare reală.
