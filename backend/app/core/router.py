"""Agentul 0: Intake Router — clasifică orice document juridic intrat în registratura băncii. Proprietar: Om1.

Pas 1: reguli pe cuvinte cheie (rapid, sigur pentru documentele tipice: popriri BEJ/ANAF vs. cereri Poliție/DNA).
Pas 2: dacă formularea e atipică și LLM-ul (AWS Bedrock) e disponibil, clasifică semantic cu LLM-ul.
"""
from app.contracts import AgentName, AgentStatus, DocType, IncomingDocument
from app.core import llm
from app.core.events import EmitFn
from app.core.validators import normalize_text

_KEYWORDS: list[tuple[DocType, list[str]]] = [
    # Ordinea contează: cele mai specifice primele
    (DocType.CERTIFICAT_MOSTENITOR, [
        "CERTIFICAT DE MOSTENITOR", "CERTIFICATUL DE MOSTENITOR", "CERTIFICAT DE CALITATE DE MOSTENITOR",
    ]),
    (DocType.NOTIFICARE_INSOLVENTA, [
        "DESCHIDEREA PROCEDURII INSOLVENTEI", "DESCHIDERE A PROCEDURII INSOLVENTEI",
        "DESCHIDEREA PROCEDURII GENERALE A INSOLVENTEI", "DESCHIDEREA PROCEDURII SIMPLIFICATE",
        "DESCHIDEREA FALIMENTULUI", "LEGEA NR. 85/2014", "LEGII NR. 85/2014", "LEGEA 85/2014", "LEGII 85/2014",
    ]),
    (DocType.POPRIRE_SISTARE, [
        "SISTARE A POPRIRII", "SISTAREA POPRIRII", "RIDICARE A POPRIRII",
        "RIDICAREA POPRIRII", "INCETARE A POPRIRII", "INCETAREA POPRIRII",
        "DESFIINTAREA POPRIRII", "RIDICARE A MASURILOR ASIGURATORII",
        "RIDICAREA MASURILOR ASIGURATORII", "RIDICAREA SECHESTRULUI ASIGURATOR",
        "RIDICARE A MASURII ASIGURATORII",
    ]),
    (DocType.POPRIRE_INFIINTARE, [
        "DECIZIE DE INSTITUIRE A MASURILOR ASIGURATORII",
        "ORDONANTA DE INSTITUIRE A MASURII ASIGURATORII",
        "INSTITUIREA MASURII ASIGURATORII A SECHESTRULUI",
        "INSTITUIRE A SECHESTRULUI ASIGURATOR",
        "SECHESTRU ASIGURATOR", "SECHESTRULUI ASIGURATOR",
    ]),
    (DocType.CERERE_AUTORITATE, [
        "INSPECTORATUL DE POLITIE", "INSPECTORATUL GENERAL AL POLITIEI", "PARCHETUL",
        "DIRECTIA NATIONALA ANTICORUPTIE", "DIICOT", "DOSAR PENAL", "URMARIRE PENALA",
        "ORDONANTA PROCURORULUI", "CRIMINALITATII ECONOMICE",
    ]),
    (DocType.POPRIRE_MODIFICARE, [
        "MODIFICARE A POPRIRII", "MODIFICAREA CUANTUMULUI", "DIMINUAREA POPRIRII",
        "ACTUALIZARE DEBIT POPRIRE",
    ]),
    (DocType.POPRIRE_INFIINTARE, [
        "INFIINTARE A POPRIRII", "INFIINTAREA POPRIRII", "INFIINTARE POPRIRE",
        "ADRESA DE INFIINTARE", "DISPUN INFIINTAREA POPRIRII", "SOMATIE SI ADRESA DE INFIINTARE",
    ]),
    (DocType.CERERE_INFORMATII, [
        "SOLICITARE DE INFORMATII", "CERERE DE INFORMATII", "COMUNICARE RULAJ CONT",
    ]),
]

_TARGET_MODULE = {
    DocType.CERERE_AUTORITATE: "autoritati (Cereri autorități)",
    DocType.NOTIFICARE_INSOLVENTA: "insolventa (Insolvență și succesiuni)",
    DocType.CERTIFICAT_MOSTENITOR: "insolventa (Insolvență și succesiuni)",
}

_SYSTEM = """Ești ofițerul de triaj (Intake Router) din departamentul Operațiuni Juridice al Raiffeisen Bank România.
Clasifici documentul primit într-una din categoriile:
- POPRIRE_INFIINTARE: adresă de înființare a popririi de la executor judecătoresc (BEJ) sau ANAF (Art. 781 CPC).
- POPRIRE_SISTARE: adresă de sistare / ridicare / încetare a unei popriri active după achitarea datoriei.
- POPRIRE_MODIFICARE: adresă de modificare a cuantumului sumei poprite.
- CERERE_INFORMATII: solicitare de informații de la executor fără indisponibilizare de sume.
- CERERE_AUTORITATE: solicitare de la Poliție (IGPR/IPJ), Parchet, DNA, DIICOT într-un dosar penal (se rutează către modulul Cereri Autorități).
- NOTIFICARE_INSOLVENTA: notificare de la tribunal / administrator / lichidator judiciar despre deschiderea procedurii insolvenței sau a falimentului (Legea 85/2014).
- CERTIFICAT_MOSTENITOR: certificat de moștenitor emis de notarul public după decesul unui client (succesiune).
- NECUNOSCUT: documentul nu se încadrează în niciuna din categoriile de mai sus.

Returnează JSON cu formatul:
{"doc_type": "...", "confidence": 0.0-1.0, "reason": "explicație scurtă în română"}"""


def classify_document(doc: IncomingDocument, emit: EmitFn) -> tuple[DocType, float, str]:
    emit(AgentName.INTAKE_ROUTER, AgentStatus.STARTED, "Clasific documentul juridic intrat în registratură", {
        "filename": doc.filename,
        "document_id": doc.document_id,
    })
    text = normalize_text(doc.text)

    for doc_type, keys in _KEYWORDS:
        hit = next((k for k in keys if k in text), None)
        if hit:
            reason = f"Expresie cheie identificată în document: „{hit.lower()}”"
            target_module = _TARGET_MODULE.get(doc_type, "popriri (PopririZero)")
            emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED,
                 f"Document clasificat: {doc_type.value} → {target_module}",
                 {"doc_type": doc_type.value, "confidence": 0.96, "method": "KEYWORD",
                  "reason": reason, "target_module": target_module})
            return doc_type, 0.96, reason

    result = llm.chat_json(_SYSTEM, (doc.text or "")[:4000])
    if isinstance(result, dict) and result.get("doc_type") in DocType.__members__:
        dt = DocType(result["doc_type"])
        conf = float(result.get("confidence", 0.75))
        reason = result.get("reason", "Clasificat semantic de AWS Bedrock.")
        emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED,
             f"Document clasificat (LLM): {dt.value}",
             {"doc_type": dt.value, "confidence": conf, "method": "LLM",
              "reason": reason, "llm_metrics": llm.last_call_metrics()})
        return dt, conf, reason

    emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED, "Tip de document necunoscut",
         {"doc_type": DocType.NECUNOSCUT.value, "confidence": 0.0, "method": "FALLBACK"})
    return DocType.NECUNOSCUT, 0.0, "Nicio regulă și niciun răspuns LLM"
