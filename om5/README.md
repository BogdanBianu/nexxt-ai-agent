# 👤 OM 5: Workbench HITL (Human-in-the-Loop), QA Scenarii & Pitch Deck Raiffeisen

## 1. Misiunea ta în echipă
Tu deții **două lucruri care fac diferența dintre un proiect tehnic bun și Locul 1 la Hackathon**:
1. **Momentul „WOW” interactiv din UI (`HitlWorkbench.tsx` + `DocumentViewer.tsx`):** Când sistemul prinde o tentativă de eludare (`E06` — salariul deghizat în diurnă din scenariul `S4`), ofițerul bancar apasă un singur buton în Workbench (*„Reclasifică în SALARIU și aprobă”*), iar motorul recalculează instant suma blocată de la `0 RON` la `2.000 RON` și generează adresa oficială către executor!
2. **Testarea cap-coadă (`scripts/run_scenarios.py`) + Pitch-ul de 3 minute** aliniat cuvânt cu cuvânt pe slide-ul de cerințe Raiffeisen Bank.

---

## 2. Fișierele pe care lucrezi EXCLUSIV tu (Zero conflicte Git)

| Fișier | Rol | Specificație tehnică |
| :--- | :--- | :--- |
| `frontend/src/components/HitlWorkbench.tsx` | Panoul de rezolvare a excepțiilor (`Human-in-the-Loop`) | Primește `caseData: Case` și un callback `onUpdated(newCase: Case)`.<br>1. Afișează toate alertele din `caseData.exceptions` (cod `E01..E09`, severitate `BLOCKING`/`WARNING`, mesaj și dovezi `evidence`).<br>2. Pentru fiecare tranzacție din `caseData.classified_transactions` (mai ales cele marcate în `evidence`), permite schimbarea categoriei dintr-un `<select>` (`SALARIU`, `DIURNA`, `ALOCATIE`, `ALT_VENIT`).<br>3. La click pe **„Aplică decizia ofițerului & Recalculează”**, apelează `api.submitReview(caseData.case_id, { reviewer: "ofiter.juridic@raiffeisen.ro", overrides: [...], resolve_codes: ["E06"], note: "..." })`. |
| `frontend/src/components/DocumentViewer.tsx` | Comparație Adresă Primită vs. Răspuns Generat | 1. Tab 1: Textul adresei de la executor (`caseData.document.text`) + tabel cu câmpurile extrase în `caseData.order` și scorul lor de încredere (`field_confidence`).<br>2. Tab 2: Adresa oficială de răspuns a băncii (`caseData.outcome?.response_letter_text`) cu buton de Copy / Download. |
| `scripts/run_scenarios.py` | Runner automat de QA pe toate scenariile | Rulează-l după fiecare modificare a colegilor ca să verifici că niciun scenariu `S1..S8` nu s-a stricat. |
| `om5/PITCH_SCRIPT.md` *(De creat de tine)* | Structura slide-urilor și discursul de 3 minute | Vezi secțiunea 3 de mai jos! |

---

## 3. Cum mapezi Pitch-ul exact pe slide-ul oficial Raiffeisen Bank

Pe slide-ul de prezentare folosește **exact termenii lor din cerință** ca juriul să bifeze mental punctajul maxim la fiecare criteriu:

1. **The Challenge:** *„Build an AI agent that handles repetitive internal banking work involving documents, data, and predefined rules.”*
   * **Răspunsul nostru:** Am construit **LexOps**, o platformă multi-agent pentru operațiuni juridice bancare, având ca prim modul complet funcțional **PopririZero** — automatizarea cap-coadă a popririlor și executărilor silite.
2. **Possible Directions (Le bifăm pe TOATE 4):**
   * **Triage and summarise requests:** Agentul `INTAKE_ROUTER` + `EXTRACTION` clasifică adresele intrate (înființare poprire BEJ/ANAF, sistare, sau cereri de la Poliție/DNA) și extrage datele structurate.
   * **Reconcile records and identify discrepancies:** Agentul `RECONCILIATION` + `INCOME_CLASSIFIER` verifică debitorul în Core Banking, prinde CNP-urile invalide sau dosarele duplicate și reconciliază încasările cu registrul de plătitori.
   * **Validate applications against requirements:** `RULE_ENGINE`-ul determinist aplică la centimă regulile din **Art. 729 și 781 Cod Procedură Civilă** (0% pe alocații/indemnizații/diurne, 1/3 pe salariu, 1/2 pentru pensie alimentară și plafon cumulat).
   * **Detect anomalies:** Agentul `ANOMALY` analizează istoricul pe 12 luni și prinde tentativele de eludare a popririi (ex: salariul reetichetat brusc drept „diurnă” în luna popririi -> ridică excepția `E06`).
3. **What to Demonstrate:** *„A working process that takes an input, applies the relevant rules, and produces an outcome or flags an exception.”*
   * **În demo arătăm 3 cazuri în 2 minute:**
     1. **Cazul `S1` (Outcome automat):** Salariat cu alocație de stat și salariu → `AUTO_PROCESSED` în 3 secunde, alocația protejată 100%, 1/3 din salariu indisponibilizat, adresă de răspuns generată.
     2. **Cazul `S4` (Flagged Exception + HITL):** Salariu deghizat în diurnă → `EXCEPTION_FLAGGED (E06)` → Ofițerul apasă un buton în Workbench → recalculare instantă la `2.000 RON`.
     3. **Cazul `S8` (Viziunea de Platformă):** Încărcăm o adresă de la Poliție → `INTAKE_ROUTER` o recunoaște și o rutează automat către modulul *Cereri Autorități*.
