"""Agentul 0: Intake Router — clasifică orice document juridic intrat. Proprietar: Om1.

Pas 1: reguli pe cuvinte cheie (rapid, sigur pentru documentele tipice).
Pas 2: dacă e neclar și LLM-ul e disponibil, întreabă LLM-ul.
"""
from app.contracts import AgentName, AgentStatus, DocType, IncomingDocument
from app.core import llm
from app.core.events import EmitFn
from app.core.validators import normalize_text

_KEYWORDS: list[tuple[DocType, list[str]]] = [
    # ordinea contează: cele mai specifice primele
    (DocType.CERERE_AUTORITATE, ["INSPECTORATUL DE POLITIE", "PARCHETUL", "DIRECTIA NATIONALA ANTICORUPTIE",
                                 "DOSAR PENAL", "URMARIRE PENALA"]),
    (DocType.POPRIRE_SISTARE, ["SISTARE A POPRIRII", "SISTAREA POPRIRII", "RIDICARE A POPRIRII",
                               "RIDICAREA POPRIRII", "INCETARE A POPRIRII"]),
    (DocType.POPRIRE_MODIFICARE, ["MODIFICARE A POPRIRII", "MODIFICAREA CUANTUMULUI"]),
    (DocType.POPRIRE_INFIINTARE, ["INFIINTARE A POPRIRII", "INFIINTAREA POPRIRII", "INFIINTARE POPRIRE"]),
    (DocType.CERERE_INFORMATII, ["SOLICITARE DE INFORMATII", "CERERE DE INFORMATII"]),
]

_SYSTEM = """Ești un ofițer juridic dintr-o bancă din România. Clasifici documentele primite.
Tipuri posibile: POPRIRE_INFIINTARE, POPRIRE_SISTARE, POPRIRE_MODIFICARE, CERERE_INFORMATII,
CERERE_AUTORITATE (Poliție/Parchet/DNA), NECUNOSCUT.
Format: {"doc_type": "...", "confidence": 0.0-1.0, "reason": "..."}"""


def classify_document(doc: IncomingDocument, emit: EmitFn) -> tuple[DocType, float, str]:
    emit(AgentName.INTAKE_ROUTER, AgentStatus.STARTED, "Clasific documentul primit", {"filename": doc.filename})
    text = normalize_text(doc.text)

    for doc_type, keys in _KEYWORDS:
        hit = next((k for k in keys if k in text), None)
        if hit:
            reason = f"Expresie identificată: „{hit.lower()}”"
            emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED, f"Document clasificat: {doc_type.value}",
                 {"doc_type": doc_type.value, "confidence": 0.95, "method": "KEYWORD", "reason": reason})
            return doc_type, 0.95, reason

    result = llm.chat_json(_SYSTEM, (doc.text or "")[:4000])
    if isinstance(result, dict) and result.get("doc_type") in DocType.__members__:
        dt, conf = DocType(result["doc_type"]), float(result.get("confidence", 0.6))
        reason = result.get("reason", "")
        emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED, f"Document clasificat (LLM): {dt.value}",
             {"doc_type": dt.value, "confidence": conf, "method": "LLM", "reason": reason})
        return dt, conf, reason

    emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED, "Tip de document necunoscut",
         {"doc_type": DocType.NECUNOSCUT.value, "confidence": 0.0})
    return DocType.NECUNOSCUT, 0.0, "Nicio regulă și niciun răspuns LLM"
