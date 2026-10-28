# 👤 OM 4: Frontend Lead — Dashboard LexOps, Vizualizare Live Agenți & Disecție Extras

## 1. Misiunea ta în echipă
Nu mai folosim Lovable — tu ai control total asupra aplicației din `frontend/` (React + TypeScript + Vite + Tailwind, sau setup-ul tău preferat).
Obiectivul tău este să construiești **interfața principală pe care o vede juriul Raiffeisen Bank**, astfel încât în 10 secunde să înțeleagă:
1. Că **LexOps** este o platformă enterprise cu mai multe module juridice (*PopririZero* activ + *Cereri Autorități*, *Sechestre*, *Insolvențe*, *GDPR* în roadmap).
2. Cum lucrează cei **7 pași din pipeline-ul de agenți** în timp real.
3. Cum este „disecat” extrasul de cont linie cu linie, cu articolele din Codul de Procedură Civilă.

---

## 2. Ce ai deja pregătit în `frontend/` (Schelet)

* `frontend/src/types/contracts.ts` — **Toate interfețele TypeScript** (`Case`, `CaseSummary`, `ClassifiedTransaction`, `GarnishmentDecision`, `ExceptionFlag`, `AgentEvent`, `ModuleInfo`, `ScenarioInfo`), aliniate 1:1 cu backend-ul FastAPI.
* `frontend/src/api/client.ts` — Funcțiile `api.listModules()`, `api.listScenarios()`, `api.listCases()`, `api.createFromScenario(id)`, `api.getCase(id)`, `api.getCaseEvents(id)`, `api.submitReview(id, review)`.

---

## 3. Cum vă împărțiți ecranul tu (Om4) și Om5 (Zero conflicte Git)

Ca să nu editați aceleași componente React în același timp:

| Componentă / Pagină | Proprietar | Fișier recomandat | Ce afișează |
| :--- | :--- | :--- | :--- |
| **Layout & Topbar (Raiffeisen Theme + Switcher Module LexOps)** | **Om 4** | `src/components/AppShell.tsx` | Bara de sus cu modulele din `GET /api/modules` (badge verde `ACTIVE` pe *PopririZero*, badge gri `ROADMAP` pe *Cereri Autorități*, *Sechestre*, *Insolvențe*, *GDPR*). |
| **Legal Inbox & Lansator Scenarii (`S1..S8`)** | **Om 4** | `src/components/CaseInbox.tsx` | Buton „Simulează Scenariu” (dropdown cu `GET /api/scenarios` -> `POST /api/cases/from-scenario`) + tabelul cu dosarele intrate (`GET /api/cases`). |
| **Agent Pipeline Visualizer (Graful celor 7 Agenți)** | **Om 4** | `src/components/AgentPipeline.tsx` | Cele 7 noduri (`INTAKE_ROUTER` -> `EXTRACTION` -> `RECONCILIATION` -> `INCOME_CLASSIFIER` -> `RULE_ENGINE` -> `ANOMALY` -> `OUTCOME`) care se aprind pe baza `GET /api/cases/{id}/events`. |
| **Disecția Extrasului de Cont & Cardul de Calcul Legal** | **Om 4** | `src/components/AccountDissection.tsx` | Tabelul cu `case.classified_transactions`:<br>• **Verde** (`ALOCATIE`, `INDEMNIZATIE_COPIL`, `DIURNA` -> `0% Protejat Art. 729`)<br>• **Albastru** (`SALARIU`, `PENSIE` -> `1/3 sau 1/2`)<br>• **Portocaliu** (`ALT_VENIT`, `SOLD_ANTERIOR` -> `100%`)<br>+ Sumarul din `case.decision` (`amount_to_hold` vs `amount_protected` + `rules_applied`). |
| **Workbench HITL (Rezolvare Excepții & Reclasificare)** | **Om 5** | `src/components/HitlWorkbench.tsx` | Panoul unde ofițerul vede `case.exceptions`, apasă „Reclasifică în Salariu” pe o tranzacție suspectă și trimite `POST /api/cases/{id}/review`. |
| **Preview Documente (Adresa Executor vs. Răspuns Bancă)** | **Om 5** | `src/components/DocumentViewer.tsx` | Afișează în stânga textul adresei primite (`case.document.text`) cu câmpurile extrase în `case.order`, iar în dreapta adresa de răspuns generată (`case.outcome.response_letter_text`). |

---

## 4. Paleta de culori recomandată (Raiffeisen Enterprise)
* **Accent primar (Raiffeisen Yellow):** `#FFE600` cu text negru `#111827` pe butoanele principale.
* **Fundal / Sidebar:** `#0F172A` (Slate 900) sau un Light Mode curat `#F8FAFC` cu carduri albe și borduri `#E2E8F0`.
* **Badge-uri de status dosar (`CaseStatus`):**
  * `AUTO_PROCESSED` → Verde (`#10B981`)
  * `EXCEPTION_FLAGGED` → Roșu/Ambră (`#EF4444` / `#F59E0B`)
  * `LIFTED` → Albastru (`#3B82F6`)
  * `ROUTED_TO_OTHER_MODULE` → Mov (`#8B5CF6`)
