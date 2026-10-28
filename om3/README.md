# 👤 OM 3: Inginer Date Sintetice, Scenarii Juridice & Fabrica de PDF-uri

## 1. Misiunea ta în echipă
Slide-ul Raiffeisen spune explicit: **„Use synthetic documents and datasets. Internal banking data is not required.”**
Tu ești creatorul lumii sintetice pe care rulăm demo-ul. Dacă scenariile tale sunt realiste, variate și spectaculoase, juriul va fi cucerit în primele 30 de secunde.

În schelet există deja **`S1.json` (caz curat)** și **`S4.json` (salariu deghizat în diurnă)** ca model. Tu trebuie să completezi toate cele **8 scenarii (`S1`–`S8`)**, să generezi **PDF-urile adreselor de intrare** și să faci **generatorul PDF pentru Adresa de Răspuns a Băncii către Executor**.

---

## 2. Fișierele pe care lucrezi EXCLUSIV tu (Zero conflicte Git)

| Fișier / Folder | Ce conține acum (Schelet) | Ce trebuie să construiești tu (TODO) |
| :--- | :--- | :--- |
| `data/scenarios/S1.json` .. `S8.json` | `S1.json` și `S4.json` sunt gata și funcționează. | Creează `S2.json`, `S3.json`, `S5.json`, `S6.json`, `S7.json`, `S8.json` respectând **exact** structura din `S1.json` (validată de `backend/app/contracts/scenario.py`). |
| `data/payers_registry.json` | 5 instituții publice (AJPIS, Casa de Pensii, Primărie). | Adaugă încă 10–15 plătitori cunoscuți din România (ANPIS, DGASPC, CNPP, universități pentru burse, companii mari). |
| `scripts/generate_pdfs.py` | Schelet cu `TODO(Om3)`. | 1. Folosește `reportlab` ca să generezi în `data/pdfs/S1.pdf .. S8.pdf` documente PDF care arată ca adrese reale de la Executori Judecătorești (BEJ), ANAF și Poliție.<br>2. Implementează `render_bank_response_pdf(...)` care generează PDF-ul oficial de răspuns cu antetul Raiffeisen Bank. |

---

## 3. Specificația celor 8 Scenarii pe care trebuie să le avem în `data/scenarios/`

> **FOARTE IMPORTANT:** Toate CNP-urile și IBAN-urile din JSON trebuie să fie **matematic valide** (altfel validatorul lui Om2 va ridica `E01`!).
> Poți folosi CNP-uri valide precum `1850615400011`, `2900312400028` (verifică-le cu `validate_cnp` din `backend/app/core/validators.py`) și IBAN-ul valid `RO49AAAA1B31007593840000`.

| ID | Titlu Scenariu | Ce trebuie să conțină JSON-ul | `expected` (Ground Truth) |
| :--- | :--- | :--- | :--- |
| **S1** *(Gata)* | Salariat cu alocație copil — Poprire comercială curată | Salariu 6.000 + Alocație 292 + Diurnă 1.500 + Transfer 800 + Sold 3.000. Datorie 15.000 RON. | `AUTO_PROCESSED`, `amount_to_hold: 5800.0`, `exception_codes: []` |
| **S2** *(De făcut)* | Mamă în concediu creștere copil — Venituri 100% protejate | Doar `Indemnizatie crestere copil` (3.500 RON) + `Alocatie de stat` (719 RON), sold 0. Datorie 5.000 RON. | `AUTO_PROCESSED`, `amount_to_hold: 0.0`, `exception_codes: []` (0 RON blocați, 100% protejat conform Art. 729!) |
| **S3** *(De făcut)* | Popriri concurente — Pensie alimentară peste poprire comercială | Salariu 6.000 RON. Are deja în `active_garnishments` o poprire comercială care îi ia `2000.0` RON/lună (1/3). Vine a doua poprire pentru `INTRETINERE` (pensie alimentară). Plafonul cumulat de 1/2 (3.000 RON) lasă doar `1000.0` RON și declanșează `E04`. | `EXCEPTION_FLAGGED`, `amount_to_hold: 1000.0`, `exception_codes: ["E04"]` |
| **S4** *(Gata)* | Eludare: Salariu deghizat în Diurnă (Momentul WOW) | 2 luni salariu 6.000 RON de la `SC CONSTRUCT PRO SRL`, apoi în luna popririi 6.000 RON cu descrierea `"Diurna delegatie externa"`. | `EXCEPTION_FLAGGED`, `amount_to_hold: 0.0`, `exception_codes: ["E06"]`, `amount_after_review: 2000.0` |
| **S5** *(De făcut)* | Eroare în adresa executorului: CNP invalid | În textul adresei, CNP-ul are ultima cifră greșită (`1850615400019` în loc de `1850615400011`). | `EXCEPTION_FLAGGED`, `amount_to_hold: 0.0`, `exception_codes: ["E01"]` |
| **S6** *(De făcut)* | Dublă poprire pe același dosar de executare (Duplicat) | Adresă de înființare poprire cu `case_number: "9988/2026"`, dar în `active_garnishments` există deja înregistrat dosarul `"9988/2026"`. | `EXCEPTION_FLAGGED`, `amount_to_hold: 0.0`, `exception_codes: ["E02"]` |
| **S7** *(De făcut)* | Adresă de Sistare (Ridicare) Poprire după achitarea datoriei | Textul conține `"ADRESĂ DE SISTARE A POPRIRII"` pentru dosarul `"7700/2026"`, care există în `active_garnishments`. | `doc_type: "POPRIRE_SISTARE"`, `status: "LIFTED"`, `amount_to_hold: 0.0`, `exception_codes: []` |
| **S8** *(De făcut)* | Solicitare de la Inspectoratul de Poliție / DNA (Demo Platformă LexOps) | Textul este o adresă oficială de la `"INSPECTORATUL GENERAL AL POLIȚIEI ROMÂNE — Serviciul Investigarea Criminalității Economice"` într-un `"DOSAR PENAL"`. Routerul o recunoaște și o trimite către modulul `autoritati` (în roadmap). | `doc_type: "CERERE_AUTORITATE"`, `status: "ROUTED_TO_OTHER_MODULE"`, `amount_to_hold: 0.0`, `exception_codes: []` |

---

## 4. Cum îți verifici singur munca în 2 secunde

După ce adaugi sau modifici un fișier `S*.json` în `data/scenarios/`, rulează din rădăcina proiectului:
```bash
python scripts/run_scenarios.py
```
Scriptul îți arată imediat `[PASS]` sau `[FAIL]` pe fiecare scenariu!
