# 👤 OM 1: Arhitect Agenți AI, LangGraph & Integrare Featherless.ai

## 1. Misiunea ta în echipă
Tu ești responsabil de **inteligența agentică a platformei LexOps**. Scheletul de bază cu fallback pe reguli deterministe este deja funcțional, astfel încât nimeni din echipă să nu fie blocat dacă pică conexiunea la LLM. Rolul tău este să rafinezi prompt-urile pentru **Featherless.ai**, să extinzi capabilitățile agenților și să te asiguri că graful LangGraph emite evenimente bogate și clare pentru Frontend.

---

## 2. Fișierele pe care lucrezi EXCLUSIV tu (Zero conflicte Git)

| Fișier | Ce conține acum (Schelet) | Ce trebuie să extinzi tu (TODO) |
| :--- | :--- | :--- |
| `backend/app/core/llm.py` | Client OpenAI configurat pe `https://api.featherless.ai/v1`, cu `chat_json` și `chat_text`. | Testează cheia Featherless a echipei, adaugă retry cu backoff și logare de latență/tokeni pentru metricile din UI. |
| `backend/app/core/router.py` | **Agent 0 (Intake Router):** clasifică documentul pe cuvinte cheie + fallback LLM. | Îmbunătățește prompt-ul LLM ca să recunoască adrese mai complexe (sechestre penale, insolvență, GDPR, cereri ANAF/Poliție) și să extragă un scurt rezumat la intrare. |
| `backend/app/core/pdf_text.py` | Extrage text din PDF digital cu `PyMuPDF` (`fitz`). | Adaugă fallback OCR pentru PDF-uri scanate (sau pre-extrage textul cu un script pentru PDF-urile lui Om3). |
| `backend/app/modules/popriri/agents/extraction.py` | **Agent 1 (Extragere & Triaj):** prompt LLM + fallback regex pentru formatul standard. | Rafinează prompt-ul `_SYSTEM` (few-shot examples) ca LLM-ul de pe Featherless să extragă impecabil datele din toate cele 3-4 formate diferite de adrese create de Om3 (BEJ, ANAF, Sistare). |
| `backend/app/modules/popriri/agents/income_classifier.py` | **Agent 3 (Clasificare Venituri):** pipeline în 3 trepte (Keywords -> Payer Registry -> Pattern -> LLM). | Îmbunătățește treapta LLM pentru descrieri bancare criptice (ex. `"Plata cf ctr 44/2026"`, `"OP 112"`, `"Virament"`) astfel încât să dea o explicație juridică clară în `rationale` și un scor `confidence` realist. |
| `backend/app/modules/popriri/agents/anomaly.py` | **Agent 5 (Detector Anomalii & Eludare):** are regulile A1 (salariu deghizat în diurnă) și A2 (golire cont după poprire). | Implementează **A3 (Fragmentarea salariului în mai multe tranșe mici)** și **A4 (Cont nou de tranzit)** + adaugă un apel LLM care sintetizează un raport de investigație pentru ofițerul juridic. |
| `backend/app/modules/popriri/graph.py` | Graful LangGraph compilat + runner secvențial de siguranță. | Adaugă noduri/evenimente intermediare dacă vreți ca animația din UI (Om4) să arate și uneltele apelate (`tool_call`). |

---

## 3. Contractul de Date pe care trebuie să îl respecți (NU modifica fără să anunți!)

Toate modelele sunt în `backend/app/contracts/`. Cele mai importante pentru tine:

1. **Output-ul lui `extraction.py`:** trebuie să întoarcă `{"order": GarnishmentOrder, "exceptions": list[ExceptionFlag]}`.
2. **Output-ul lui `income_classifier.py`:** trebuie să întoarcă `{"classified": list[ClassifiedTransaction], "exceptions": list[ExceptionFlag]}`.
3. **Output-ul lui `anomaly.py`:** trebuie să întoarcă `{"exceptions": list[ExceptionFlag]}` (lista se adună automat în starea grafului prin `operator.add`).
4. **Evenimentele pentru Frontend:** în fiecare agent ai acces la `ctx.emit(AgentName, AgentStatus, message, data)`. Orice emiți aici apare live în graful vizual al lui Om4!

---

## 4. Checklist de lucru pe ore

- [ ] **Ora 1:** Copiază `.env.example` în `.env`, pune cheia `FEATHERLESS_API_KEY` și rulează `python scripts/run_scenarios.py` ca să verifici că S1 și S4 trec atât cu `USE_LLM=off`, cât și cu `USE_LLM=auto`.
- [ ] **Orele 2–5:** Lucrează cu **Om3** pe textele adreselor din scenariile `S1..S8` și asigură-te că `extraction.py` extrage 100% corect CNP-ul, dosarul, sumele și IBAN-ul de consemnare.
- [ ] **Orele 6–10:** Rafinează `anomaly.py` și `income_classifier.py` pentru scenariul `S4` (Salariu deghizat în diurnă) și `S3` (Venit ambiguu + popriri concurente).
- [ ] **Orele 11–15:** Adaugă un mecanism de **cache pe disc al răspunsurilor LLM** în `backend/app/core/llm.py` (hash pe prompt -> JSON salvat), ca la demo-ul final în fața juriului răspunsul să vină în <1 secundă și să nu depindeți de Wi-Fi-ul din sală!
