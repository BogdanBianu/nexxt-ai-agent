"""Agentul 3: Clasificarea încasărilor după natura juridică. Proprietar: Om1.

Ordine (de la cel mai sigur la cel mai puțin sigur):
  0. HUMAN          override de la ofițer (Workbench)
  1. KEYWORD        cuvinte cheie din descriere
  2. PAYER_REGISTRY plătitori cunoscuți (data/payers_registry.json)
  3. PATTERN        plătitor recurent care a plătit „salariu” în lunile trecute
  4. LLM            Featherless, cu justificare
  5. FALLBACK       ALT_VENIT cu încredere mică -> E03 dacă suma e mare
"""
import json
from datetime import timedelta
from decimal import Decimal

from app import config
from app.contracts import (AgentName, AgentStatus, ClassificationMethod, ClassifiedTransaction,
                           ExceptionCode, ExceptionFlag, IncomeCategory, PayerRegistryEntry, Severity,
                           Transaction, TxDirection)
from app.core import llm
from app.core.validators import normalize_text
from .context import AgentContext

# (categorie, cuvinte cheie, încredere). Ordinea contează.
KEYWORDS: list[tuple[IncomeCategory, list[str], float]] = [
    (IncomeCategory.INDEMNIZATIE_COPIL, ["INDEMNIZATIE CRESTERE", "CRESTERE COPIL", "ICC"], 0.95),
    (IncomeCategory.ALOCATIE, ["ALOCATIE"], 0.95),
    (IncomeCategory.INDEMNIZATIE_BOALA, ["CONCEDIU MEDICAL", "INDEMNIZATIE BOALA", "INCAPACITATE"], 0.9),
    (IncomeCategory.AJUTOR_SOCIAL, ["AJUTOR SOCIAL", "VENIT MINIM", "AJUTOR DE DECES", "AJUTOR INCALZIRE"], 0.9),
    (IncomeCategory.DIURNA, ["DIURNA"], 0.9),
    (IncomeCategory.PENSIE, ["PENSIE"], 0.9),
    (IncomeCategory.SALARIU, ["SALARIU", "SALARIAL", "AVANS CHENZINA", "LICHIDARE"], 0.92),
    (IncomeCategory.ALT_VENIT, ["CHIRIE", "DIVIDENDE", "IMPRUMUT", "RAMBURSARE", "TRANSFER", "VANZARE"], 0.85),
]

_SYSTEM = """Ești analist într-o bancă din România. Stabilești natura juridică a unei încasări
pentru aplicarea unei popriri. Categorii: SALARIU, PENSIE, ALOCATIE, INDEMNIZATIE_COPIL, DIURNA,
AJUTOR_SOCIAL, INDEMNIZATIE_BOALA, ALT_VENIT.
Format: {"category": "...", "confidence": 0.0-1.0, "rationale": "o frază în română"}"""


def load_payer_registry() -> list[PayerRegistryEntry]:
    path = config.DATA_DIR / "payers_registry.json"
    if not path.exists():
        return []
    return [PayerRegistryEntry.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def _make(t: Transaction, cat: IncomeCategory, method: ClassificationMethod, conf: float, why: str,
          in_window: bool = True) -> ClassifiedTransaction:
    return ClassifiedTransaction(tx_id=t.tx_id, iban=t.iban, booking_date=t.booking_date, amount=t.amount,
                                 counterparty_name=t.counterparty_name, description=t.description,
                                 category=cat, method=method, confidence=conf, rationale=why,
                                 in_analysis_window=in_window)


def classify_one(t: Transaction, history: list[Transaction], registry: list[PayerRegistryEntry],
                 overrides: dict[str, IncomeCategory]) -> ClassifiedTransaction:
    if t.tx_id in overrides:
        return _make(t, overrides[t.tx_id], ClassificationMethod.HUMAN, 1.0, "Reclasificat manual de ofițer.")

    desc = normalize_text(t.description)
    for cat, keys, conf in KEYWORDS:
        hit = next((k for k in keys if k in desc.split() or (" " in k and k in desc)), None)
        if hit:
            return _make(t, cat, ClassificationMethod.KEYWORD, conf, f"Descrierea conține „{hit.lower()}”.")

    payer = normalize_text(t.counterparty_name)
    for entry in registry:
        if (entry.iban and entry.iban == t.counterparty_iban) or (entry.match and entry.match in payer):
            return _make(t, entry.default_category, ClassificationMethod.PAYER_REGISTRY, 0.97,
                         f"Plătitor cunoscut: {entry.label}.")

    past_salary = [h for h in history if h.counterparty_name == t.counterparty_name and h.tx_id != t.tx_id
                   and "SALAR" in normalize_text(h.description)]
    if len(past_salary) >= 2:
        return _make(t, IncomeCategory.SALARIU, ClassificationMethod.PATTERN, 0.8,
                     f"Același plătitor a virat salariul în {len(past_salary)} luni anterioare.")

    data = llm.chat_json(_SYSTEM, json.dumps({
        "platitor": t.counterparty_name, "descriere": t.description, "suma": str(t.amount),
        "istoric_platitor": [h.description for h in history if h.counterparty_name == t.counterparty_name][-5:],
    }, ensure_ascii=False))
    if isinstance(data, dict) and data.get("category") in IncomeCategory.__members__:
        return _make(t, IncomeCategory(data["category"]), ClassificationMethod.LLM,
                     float(data.get("confidence", 0.6)), data.get("rationale", "Clasificat de LLM."))

    return _make(t, IncomeCategory.ALT_VENIT, ClassificationMethod.FALLBACK, 0.5,
                 "Natura încasării nu a putut fi stabilită; tratată ca alt venit.")


def run(state: dict, ctx: AgentContext) -> dict:
    emit, doc = ctx.emit, state["document"]
    emit(AgentName.INCOME_CLASSIFIER, AgentStatus.STARTED, "Clasific încasările din cont după natura juridică", {})
    review = state.get("review")
    overrides = {o.tx_id: o.category for o in (review.overrides if review else [])}
    registry = load_payer_registry()
    window_start = doc.received_at.date() - timedelta(days=config.ANALYSIS_WINDOW_DAYS)

    history = state.get("transactions", [])
    credits = [t for t in history if t.direction == TxDirection.CREDIT and t.booking_date >= window_start]
    classified = [classify_one(t, history, registry, overrides) for t in credits]

    # soldul de la începutul ferestrei = urmăribil integral
    for acc in state.get("accounts", []):
        if acc.opening_balance > 0:
            classified.insert(0, ClassifiedTransaction(
                tx_id=f"SOLD-{acc.iban[-6:]}", iban=acc.iban, booking_date=window_start,
                amount=acc.opening_balance, counterparty_name="—", description="Sold la începutul perioadei",
                category=IncomeCategory.SOLD_ANTERIOR, method=ClassificationMethod.PATTERN, confidence=1.0,
                rationale="Sume existente în cont înainte de perioada analizată."))

    exc = []
    threshold = Decimal(str(config.AMBIGUOUS_AMOUNT_THRESHOLD))
    for c in classified:
        if (c.method != ClassificationMethod.HUMAN and c.confidence < config.MIN_CLASSIFICATION_CONFIDENCE
                and c.amount >= threshold):
            exc.append(ExceptionFlag(code=ExceptionCode.E03_VENIT_AMBIGUU, severity=Severity.BLOCKING,
                                     agent=AgentName.INCOME_CLASSIFIER,
                                     message=f"Încasarea de {c.amount} RON de la {c.counterparty_name} "
                                             f"(„{c.description}”) are natură neclară; cota aplicabilă diferă "
                                             "între 0%, 33% și 100%.", evidence=[c.tx_id]))
        emit(AgentName.INCOME_CLASSIFIER, AgentStatus.PROGRESS,
             f"{c.amount} RON · {c.counterparty_name} → {c.category.value}",
             {"tx_id": c.tx_id, "category": c.category.value, "method": c.method.value, "confidence": c.confidence})

    emit(AgentName.INCOME_CLASSIFIER, AgentStatus.COMPLETED, f"{len(classified)} încasări clasificate",
         {"exceptions": [e.code.value for e in exc]})
    return {"classified": classified, "exceptions": exc}
