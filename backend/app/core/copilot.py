"""Agentul „Explain & Cite”: răspunde la întrebări libere despre un dosar procesat. Proprietar: Om2.

Funcționează pe orice modul, pentru că citește doar ce e comun tuturor dosarelor: decizia, regulile aplicate
(cu temeiul legal), excepțiile (cu dovezi) și tranzacțiile clasificate.

Pas 1: alege faptele din dosar relevante pentru întrebare (ID-uri, IBAN-uri, articole de lege, cuvinte comune).
Pas 2: dacă LLM-ul e disponibil, formulează răspunsul DOAR din aceste fapte; citările care nu există în dosar
       se elimină, iar fără nicio citare validă răspunsul LLM e aruncat.
Pas 3: altfel, răspuns determinist compus din aceleași fapte.
"""
import json
import re
from dataclasses import dataclass

from app.contracts import Case, Citation, Severity
from app.core import llm
from app.core.validators import normalize_text

MAX_FACTS = 5
_ENFORCEMENT_MODULES = {"popriri", "sechestre"}   # module în care regulile calculează sume urmăribile
_STOP = {
    "CARE", "PENTRU", "DACA", "ACEST", "ACESTA", "ACEASTA", "ESTE", "SUNT", "NOSTRU", "LUI", "EII", "CUM", "CAND",
    "UNDE", "CEEA", "DESPRE", "DOSAR", "DOSARUL", "DOSARULUI", "AVETI", "ATI", "NOI", "VOI", "SAU", "DAR", "TOTI",
    "TOATE", "TOT", "TOATA", "DIN", "PRIN", "CEL", "CEA", "CELE", "CEI", "INCAT", "AFOST", "FOST", "FOARTE", "MAI",
}
_ART = re.compile(r"\bART(?:ICOLUL|ICOL|\.)?\s*(\d+)")
_IBAN_PART = re.compile(r"\bRO\d{2}[A-Z0-9]*")

_SYSTEM = """Ești asistentul „Explain & Cite” al departamentului Operațiuni Juridice din Raiffeisen Bank România.
Un ofițer (sau un membru al juriului) întreabă de ce dosarul a fost soluționat așa.
Reguli stricte:
- Răspunzi DOAR din faptele primite (decizie, reguli aplicate, excepții, tranzacții). Nu inventa articole, sume sau tranzacții.
- Pentru fiecare regulă pe care te bazezi, scrii în text temeiul legal exact, copiat din fapte, între paranteze
  după ID, ex. „R-WAGE-04 (CPC art. 729 alin. (1) lit. b))”, și numești tranzacțiile relevante (ex. TX-1001).
- Explici toate regulile care contribuie la rezultat, nu doar una (ex. ce s-a blocat ȘI ce a rămas protejat).
- Dacă faptele nu răspund la întrebare, spui clar că dosarul nu conține această informație.
- Română, ton profesionist, maximum 120 de cuvinte, fără markdown.
Returnează JSON: {"answer": "...", "citations": ["R-WAGE-04", "TX-1001", "E06"]} — citations conține doar ID-uri din fapte."""


@dataclass
class _Fact:
    citation: Citation
    text: str                                   # textul normalizat după care se caută
    ibans: tuple[str, ...] = ()
    line: str = ""                              # propoziția din răspunsul determinist


def _ron(value) -> str:
    return f"{float(value):.2f} RON"


def _facts(case: Case) -> list[_Fact]:
    facts: list[_Fact] = []
    tx_iban = {t.tx_id: t.iban for t in case.classified_transactions}
    enforcement = case.module_id in _ENFORCEMENT_MODULES
    if case.decision:
        for r in case.decision.rules_applied:
            if enforcement:
                amounts = f" Bază {_ron(r.base_amount)}, urmăribil {_ron(r.seizable_amount)}."
            else:   # GDPR / insolvență / succesiuni: „urmăribil” n-are sens; la moștenitori e cota fiecăruia
                amounts = f" Sumă rezultată: {_ron(r.seizable_amount)}." if r.seizable_amount else ""
            line = (f"{r.rule_id} ({r.legal_source}): {r.description}{amounts}"
                    + (f" Tranzacții: {', '.join(r.tx_ids)}." if r.tx_ids else ""))
            facts.append(_Fact(
                Citation(kind="RULE", ref=r.rule_id, legal_source=r.legal_source, text=r.description,
                         tx_ids=list(r.tx_ids)),
                normalize_text(f"{r.rule_id} {r.legal_source} {r.description} {' '.join(r.tx_ids)}"),
                tuple(tx_iban[t] for t in r.tx_ids if t in tx_iban), line))
    for e in case.exceptions:
        state = "rezolvată" if e.resolved else "nerezolvată"
        severity = "blocantă" if e.severity == Severity.BLOCKING else "atenționare"
        line = (f"{e.code.value} ({severity}, {state}): {e.message}"
                + (f" Dovezi: {', '.join(e.evidence)}." if e.evidence else ""))
        facts.append(_Fact(
            Citation(kind="EXCEPTION", ref=e.code.value, text=e.message, tx_ids=list(e.evidence)),
            normalize_text(f"{e.code.value} {e.message} {' '.join(e.evidence)}"),
            tuple(tx_iban[t] for t in e.evidence if t in tx_iban), line))
    for t in case.classified_transactions:
        payer = f" de la {t.counterparty_name}" if t.counterparty_name.strip(" —-") else ""
        line = f"{t.tx_id}: {_ron(t.amount)}{payer} în {t.iban}, clasificată {t.category.value} — {t.rationale}"
        facts.append(_Fact(
            Citation(kind="TRANSACTION", ref=t.tx_id, text=f"{_ron(t.amount)} · {t.category.value} · {t.rationale}",
                     tx_ids=[t.tx_id]),
            normalize_text(f"{t.tx_id} {t.counterparty_name} {t.description} {t.category.value} {t.rationale}"),
            (t.iban,), line))
    return facts


def _stems(text: str) -> set[str]:
    # primele 5 litere: „poprit” / „popririi” / „poprire” se potrivesc între ele
    return {w[:5] for w in re.findall(r"[A-Z]{4,}", text) if w not in _STOP}


def _score(fact: _Fact, q: str, q_stems: set[str]) -> int:
    score = 0
    if normalize_text(fact.citation.ref) in q:
        score += 10
    for part in _IBAN_PART.findall(q):
        if any(i.replace(" ", "").startswith(part) for i in fact.ibans):
            score += 5
    legal = normalize_text(fact.citation.legal_source)
    for art in _ART.findall(q):
        if re.search(rf"\bART\.?\s*{art}\b", legal) or re.search(rf"\bART\.?\s*{art}\b", fact.text):
            score += 6
    score += len(q_stems & _stems(fact.text))
    return score


def relevant_facts(case: Case, question: str) -> list[_Fact]:
    """Faptele care răspund la întrebare; dacă nimic nu se potrivește, regulile și excepțiile deschise."""
    facts = _facts(case)
    q = normalize_text(question)
    q_stems = _stems(q)
    scored = sorted(((s, i, f) for i, f in enumerate(facts) if (s := _score(f, q, q_stems)) > 0),
                    key=lambda x: (-x[0], x[1]))
    if scored:
        return [f for _s, _i, f in scored[:MAX_FACTS]]
    open_exc = [e.code.value for e in case.exceptions if not e.resolved]
    return [f for f in facts if f.citation.kind == "RULE"
            or (f.citation.kind == "EXCEPTION" and f.citation.ref in open_exc)][:MAX_FACTS]


def _headline(case: Case) -> str:
    if case.outcome and case.outcome.summary:
        headline = case.outcome.summary
    else:
        headline = f"Dosarul are statusul {case.status.value} (modul: {case.module_id or 'necunoscut'})."
    d = case.decision
    if d and case.module_id in _ENFORCEMENT_MODULES and d.exempt_total:
        headline += f" Din banii rămași clientului, {_ron(d.exempt_total)} sunt neurmăribili conform legii."
    return headline


def _deterministic(case: Case, facts: list[_Fact]) -> str:
    if not facts:
        return (_headline(case) + " Dosarul nu conține reguli aplicate, excepții sau tranzacții "
                "care să explice mai mult.")
    return _headline(case) + "\nMotivele din dosar:\n" + "\n".join(f"• {f.line}" for f in facts)


def _context(case: Case, facts: list[_Fact]) -> str:
    d = case.decision
    payload = {
        "dosar": {"case_id": case.case_id, "modul": case.module_id, "tip_document": case.doc_type.value,
                  "status": case.status.value,
                  "debitor": case.order.debtor_name if case.order else (case.customer.full_name if case.customer else None),
                  "emitent": case.order.issuer_name if case.order else None,
                  "sumar": case.outcome.summary if case.outcome else None},
        "decizie": {"blocat": float(d.amount_to_hold), "protejat": float(d.amount_protected),
                    "neurmaribil": float(d.exempt_total), "datorat": float(d.total_due)} if d else None,
        "fapte_relevante": [f.line for f in facts],
        "toate_faptele": [f.line for f in _facts(case)][:40],
    }
    return json.dumps(payload, ensure_ascii=False)[:8000]


def answer(case: Case, question: str) -> tuple[str, list[Citation], str]:
    """Întoarce (răspuns, citări, metodă). Metoda: „LLM” sau „DETERMINISTIC”."""
    facts = relevant_facts(case, question)
    result = llm.chat_json(_SYSTEM, f"Fapte din dosar:\n{_context(case, facts)}\n\nÎntrebare: {question}")
    if isinstance(result, dict) and isinstance(result.get("answer"), str) and result["answer"].strip():
        by_ref: dict[str, list[Citation]] = {}
        for f in _facts(case):
            by_ref.setdefault(f.citation.ref, []).append(f.citation)
        refs = [str(r) for r in result.get("citations") or [] if str(r) in by_ref]
        cited = [c for r in dict.fromkeys(refs) for c in by_ref[r]]
        if cited:   # fără nicio citare verificabilă din dosar, nu ne bazăm pe LLM
            return result["answer"].strip(), cited, "LLM"
    return _deterministic(case, facts), [f.citation for f in facts], "DETERMINISTIC"
