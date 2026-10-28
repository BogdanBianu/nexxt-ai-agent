"""Serverul FastAPI și Store-ul de dosare. Proprietar: Om2.

Acest fișier expune toate endpoint-urile HTTP și SSE (Server-Sent Events) pe care
le consumă Frontend-ul (Om4 și Om5).
"""
from collections import Counter
from decimal import Decimal
from functools import lru_cache
import importlib.util
import json
import logging
import re
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

from app import config
from app.contracts import (
    ActiveGarnishment, AgentName, AgentStatus, AuditEntry, BankSnapshot, DocType, Case, CaseStatus, CaseSummary, CreateCaseFromScenario,
    CustomerStatus,
    IncomingDocument, ModuleInfo, PlatformMetrics, ReviewAction, RuleBookInfo, Scenario, ScenarioInfo,
)
from app.core.events import EventSink, now
from app.core.modules import module_for, registry
from app.core.pdf_text import bytes_to_text
from app.core.router import classify_document
from app.modules.popriri.engine.rules import load_rulebook

log = logging.getLogger("lexops")

app = FastAPI(title="LexOps Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stocare în memorie pentru hackathon (Om2 poate migra pe SQLite dacă dorește)
CASES: dict[str, Case] = {}
BANKS: dict[str, BankSnapshot] = {}
EVENTS: dict[str, list[dict]] = {}
PROCESSING_MS: dict[str, float] = {}           # durata primei rulări a pipeline-ului (pentru /api/metrics)
AUDIT_LOG: dict[str, list[AuditEntry]] = {}    # istoricul TUTUROR rulărilor (o re-rulare HITL nu șterge nimic)
# Popririle înființate în această sesiune: case_id -> (scenariu, CNP/CUI, poprire). Fiecare scenariu e
# o „bancă” separată; fără registru, aceeași adresă trimisă de două ori s-ar bloca de două ori (R-DUP-10).
REGISTERED: dict[str, tuple[str | None, str, ActiveGarnishment]] = {}
# Insolvențele înregistrate în sesiune: case_id -> (scenariu, CUI). Clientul devine INSOLVENTA pentru
# documentele următoare, iar popririle lui sunt suspendate (Legea 85/2014, art. 75).
INSOLVENT: dict[str, tuple[str | None, str]] = {}

_SCENARIO_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
UPLOADS_DIR = config.DATA_DIR / "uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
FINAL_AUTO_STATUSES = {CaseStatus.AUTO_PROCESSED, CaseStatus.LIFTED}


def load_scenario(scenario_id: str) -> Scenario:
    """Încarcă un scenariu sintetic din data/scenarios/{scenario_id}.json."""
    path = config.SCENARIOS_DIR / f"{scenario_id}.json"
    # ID-ul vine din request: fără „../” (altfel se citesc alte fișiere din data/ -> 500)
    if not _SCENARIO_ID.fullmatch(scenario_id) or not path.exists():
        raise HTTPException(status_code=404, detail=f"Scenariul {scenario_id} nu există")
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))


@app.get("/", include_in_schema=False)
def root():
    """Serverul e doar API: rădăcina trimite la documentația Swagger."""
    return RedirectResponse(url="/docs")


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_enabled": config.llm_enabled(), "model": config.LLM_MODEL}


@app.get("/api/rules", response_model=RuleBookInfo)
def get_rules():
    """Registrul de reguli versionat (v2026_10.yaml), cu sursa legală a fiecărei reguli."""
    return RuleBookInfo.model_validate(load_rulebook().as_dict())


@app.get("/api/metrics", response_model=PlatformMetrics)
def get_metrics():
    """KPI-uri agregate peste dosarele procesate: automatizare, timp mediu, sume protejate."""
    cases = list(CASES.values())
    popriri = [c for c in cases if c.status != CaseStatus.ROUTED_TO_OTHER_MODULE]
    decisions = [c.decision for c in cases if c.decision]
    automated = sum(1 for c in popriri if c.status in FINAL_AUTO_STATUSES)
    durations = [PROCESSING_MS[c.case_id] for c in cases if c.case_id in PROCESSING_MS]
    zero = Decimal(0)
    return PlatformMetrics(
        total_cases=len(cases),
        cases_by_status=dict(Counter(c.status.value for c in cases)),
        automation_rate=round(100 * automated / len(popriri), 1) if popriri else 0.0,
        avg_processing_ms=round(sum(durations) / len(durations), 1) if durations else 0.0,
        total_amount_held=float(sum((d.amount_to_hold for d in decisions), zero)),
        total_amount_protected=float(sum((d.amount_protected for d in decisions), zero)),
        total_exempt=float(sum((d.exempt_total for d in decisions), zero)),
        exceptions_by_code=dict(Counter(e.code.value for c in cases for e in c.exceptions)),
        reviews_count=sum(len(c.reviews) for c in cases),
    )


@app.get("/api/modules", response_model=list[ModuleInfo])
def list_modules():
    """Returnează toate modulele platformei LexOps (PopririZero activ + cele din roadmap)."""
    return [m.info for m in registry().values()]


@app.get("/api/scenarios", response_model=list[ScenarioInfo])
def list_scenarios():
    """Returnează lista scenariilor sintetice pregătite de Om3."""
    items: list[ScenarioInfo] = []
    if config.SCENARIOS_DIR.exists():
        # sortare naturală: S2 înainte de S10
        for p in sorted(config.SCENARIOS_DIR.glob("*.json"),
                        key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.stem)]):
            raw = json.loads(p.read_text(encoding="utf-8"))
            items.append(ScenarioInfo(
                scenario_id=raw["scenario_id"],
                title=raw["title"],
                description=raw["description"],
            ))
    return items


@app.get("/api/cases", response_model=list[CaseSummary])
def list_cases():
    """Returnează lista scurtă de dosare pentru Inbox-ul juridic (Om4)."""
    out: list[CaseSummary] = []
    for c in sorted(CASES.values(), key=lambda x: x.created_at, reverse=True):
        open_exc = sum(1 for e in c.exceptions if not e.resolved)
        out.append(CaseSummary(
            case_id=c.case_id,
            scenario_id=c.scenario_id,
            module_id=c.module_id,
            doc_type=c.doc_type,
            status=c.status,
            debtor_name=c.order.debtor_name if c.order else (c.customer.full_name if c.customer else None),
            case_number=c.order.case_number if c.order else None,
            amount_to_hold=float(c.decision.amount_to_hold) if c.decision else None,
            open_exceptions=open_exc,
            created_at=c.created_at.isoformat(),
        ))
    return out


@app.post("/api/cases/from-scenario", response_model=Case)
def create_case_from_scenario(body: CreateCaseFromScenario):
    """Creează și rulează un dosar dintr-un scenariu sintetic (S1..S8)."""
    sc = load_scenario(body.scenario_id)
    case_id = f"CASE-{body.scenario_id}-{uuid.uuid4().hex[:6].upper()}"
    ts = now()
    case = Case(
        case_id=case_id,
        scenario_id=sc.scenario_id,
        status=CaseStatus.PROCESSING,
        created_at=ts,
        updated_at=ts,
        document=sc.document,
    )
    BANKS[case_id] = sc.bank
    CASES[case_id] = _run_pipeline(case, sc.bank)
    return CASES[case_id]


@app.post("/api/cases/upload", response_model=Case)
async def upload_case_document(file: UploadFile = File(...), scenario_id: str = Form("S1")):
    """Încarcă un PDF (sau .txt) în timpul demo-ului și îl rulează pe BankSnapshot-ul scenariului `scenario_id`.

    Se trimite ca `multipart/form-data` cu câmpurile `file` și (opțional) `scenario_id`.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fișierul încărcat este gol")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fișierul depășește 10 MB")

    filename = file.filename or "document"
    is_pdf = data[:5] == b"%PDF-"
    if not is_pdf and not filename.lower().endswith(".txt"):
        raise HTTPException(status_code=415, detail="Se acceptă doar fișiere PDF sau .txt")
    sc = load_scenario(scenario_id)

    try:
        text = bytes_to_text(data, "upload.pdf" if is_pdf else filename)
    except Exception as exc:  # PDF corupt / criptat
        raise HTTPException(status_code=422, detail=f"Nu am putut citi textul din fișier: {exc}") from exc

    case_id = f"CASE-UP-{uuid.uuid4().hex[:6].upper()}"
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stored = UPLOADS_DIR / f"{case_id}_{re.sub(r'[^A-Za-z0-9._-]', '_', filename)}"
    stored.write_bytes(data)

    ts = now()
    case = Case(
        case_id=case_id,
        scenario_id=sc.scenario_id,
        status=CaseStatus.PROCESSING,
        created_at=ts,
        updated_at=ts,
        document=IncomingDocument(
            document_id=f"DOC-{case_id}",
            filename=filename,
            received_at=ts,
            content_type="application/pdf" if is_pdf else "text/plain",
            text=text,
            pdf_path=_data_path(stored) if is_pdf else None,
        ),
    )
    BANKS[case_id] = sc.bank
    CASES[case_id] = _run_pipeline(case, sc.bank)
    return CASES[case_id]


@app.get("/api/cases/{case_id}", response_model=Case)
def get_case(case_id: str):
    if case_id not in CASES:
        raise HTTPException(status_code=404, detail="Dosarul nu a fost găsit")
    return CASES[case_id]


@app.get("/api/cases/{case_id}/audit", response_model=list[AuditEntry])
def get_case_audit(case_id: str):
    """Audit trail complet: ce agent / ce om a decis, pe ce regulă și cu ce dovezi."""
    case = get_case(case_id)
    entries = AUDIT_LOG.get(case_id, []) + case.audit
    entries += [AuditEntry(timestamp=r.timestamp or case.updated_at, actor=f"user:{r.reviewer}",
                           action="HITL_REVIEW", details=r.model_dump(mode="json", exclude={"timestamp"}))
                for r in case.reviews]
    return sorted(entries, key=lambda e: e.timestamp)


@app.get("/api/cases/{case_id}/response-pdf")
def get_response_pdf(case_id: str):
    """Adresa de răspuns a băncii către executor, generată de Om3 (scripts/generate_pdfs.py)."""
    case = get_case(case_id)
    letter = case.outcome.response_letter_text if case.outcome else None
    if not letter:
        raise HTTPException(status_code=409,
                            detail="Dosarul nu are adresă de răspuns (excepții nerezolvate sau dosar rutat)")
    path = _response_pdf_renderer()(case.case_id, letter, config.OUTPUT_DIR)
    case.outcome.response_letter_pdf = _data_path(path)
    with open(path, "rb") as fh:
        is_pdf = fh.read(5) == b"%PDF-"
    # până când Om3 termină generatorul reportlab, stub-ul scrie text simplu
    return FileResponse(path, media_type="application/pdf" if is_pdf else "text/plain; charset=utf-8",
                        filename=path.name if is_pdf else f"{path.stem}.txt")


@app.get("/api/cases/{case_id}/events")
def get_case_events(case_id: str):
    """Returnează toate evenimentele agenților pentru un dosar (pentru graful din UI)."""
    return EVENTS.get(case_id, [])


@app.get("/api/cases/{case_id}/stream")
def stream_case_events(case_id: str):
    """SSE endpoint: trimite evenimentele agenților ca stream `data: {...}\\n\\n`."""
    events = EVENTS.get(case_id, [])

    def gen():
        for ev in events:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/cases/{case_id}/review", response_model=Case)
def review_case(case_id: str, action: ReviewAction):
    """Workbench HITL (Om5): ofițerul reclasifică o tranzacție sau rezolvă o excepție -> graful recalculează."""
    if case_id not in CASES:
        raise HTTPException(status_code=404, detail="Dosarul nu a fost găsit")
    case = CASES[case_id]
    bank = BANKS.get(case_id, BankSnapshot())
    action.timestamp = now()
    case.reviews.append(action)
    CASES[case_id] = _run_pipeline(case, bank, review=action)
    return CASES[case_id]


def _data_path(path) -> str:
    """Cale relativă la data/ (cum o așteaptă contractul); absolută dacă fișierul e în altă parte."""
    try:
        return path.relative_to(config.DATA_DIR).as_posix()
    except ValueError:
        return path.as_posix()


@lru_cache
def _response_pdf_renderer():
    """Încarcă `render_bank_response_pdf` din scripts/generate_pdfs.py (scripts/ nu e pachet Python)."""
    path = config.ROOT_DIR / "scripts" / "generate_pdfs.py"
    spec = importlib.util.spec_from_file_location("lexops_generate_pdfs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render_bank_response_pdf


def _run_pipeline(case: Case, bank: BankSnapshot, review: ReviewAction | None = None) -> Case:
    sink = EventSink(case.case_id)
    started = time.perf_counter()
    doc_type, _conf, _reason = classify_document(case.document, sink.emit)
    case.doc_type = doc_type
    mod = module_for(doc_type)

    if mod is None or mod.info.status.value == "ROADMAP":
        case.module_id = mod.info.module_id if mod else "necunoscut"
        case.status = CaseStatus.ROUTED_TO_OTHER_MODULE
        _emit_routed(sink, mod)
    else:
        case.module_id = mod.info.module_id
        try:
            case = mod.process(case, _bank_with_registered(case, bank), sink.emit, review=review)
        except Exception as exc:  # un document neașteptat la demo nu trebuie să dea 500
            log.exception("Pipeline eșuat pentru %s", case.case_id)
            case.status = CaseStatus.FAILED
            case.audit.append(AuditEntry(timestamp=now(), actor="platform", action="PIPELINE_ERROR",
                                         details={"error": f"{type(exc).__name__}: {exc}"}))

    if review is None:
        PROCESSING_MS[case.case_id] = (time.perf_counter() - started) * 1000
    case.updated_at = now()
    _register(case)
    EVENTS[case.case_id] = [e.model_dump(mode="json") for e in sink.events]
    AUDIT_LOG.setdefault(case.case_id, []).extend(_audit_entries(case, sink))
    return case


def _bank_with_registered(case: Case, bank: BankSnapshot) -> BankSnapshot:
    """Banca scenariului + ce s-a înregistrat deja în sesiune pe același client (în afară de dosarul curent):
    popririle înființate și insolvențele (client INSOLVENTA, popriri suspendate)."""
    bank = _bank_with_insolvencies(case, bank)
    customer_ids = {c.national_id: c.customer_id for c in bank.customers}
    known = {(g.customer_id, g.case_number) for g in bank.active_garnishments}
    extra = []
    for case_id, (scenario_id, national_id, g) in REGISTERED.items():
        if case_id == case.case_id or scenario_id != case.scenario_id or national_id not in customer_ids:
            continue
        g = g.model_copy(update={"customer_id": customer_ids[national_id]})
        if (g.customer_id, g.case_number) not in known:
            extra.append(g)
    if not extra:
        return bank
    return bank.model_copy(update={"active_garnishments": bank.active_garnishments + extra})


def _bank_with_insolvencies(case: Case, bank: BankSnapshot) -> BankSnapshot:
    insolvent = {nid for case_id, (sid, nid) in INSOLVENT.items()
                 if case_id != case.case_id and sid == case.scenario_id}
    hit = {c.customer_id for c in bank.customers if c.national_id in insolvent}
    if not hit:
        return bank
    return bank.model_copy(update={
        "customers": [c.model_copy(update={"status": CustomerStatus.INSOLVENTA}) if c.customer_id in hit else c
                      for c in bank.customers],
        "active_garnishments": [g.model_copy(update={"active": False}) if g.customer_id in hit else g
                                for g in bank.active_garnishments],
    })


def _register(case: Case) -> None:
    """Ține minte popririle înființate automat; o sistare reușită le scoate din registru."""
    REGISTERED.pop(case.case_id, None)
    INSOLVENT.pop(case.case_id, None)
    order, decision, customer = case.order, case.decision, case.customer
    if not (order and customer):
        return
    if case.status == CaseStatus.AUTO_PROCESSED and order.doc_type == DocType.NOTIFICARE_INSOLVENTA:
        INSOLVENT[case.case_id] = (case.scenario_id, customer.national_id)
        for case_id in [k for k, (sid, nid, _g) in REGISTERED.items()
                        if sid == case.scenario_id and nid == customer.national_id]:
            del REGISTERED[case_id]           # popririle înființate în sesiune sunt suspendate
    if (case.status == CaseStatus.AUTO_PROCESSED and order.doc_type == DocType.POPRIRE_INFIINTARE
            and order.case_number and decision):
        REGISTERED[case.case_id] = (case.scenario_id, customer.national_id, ActiveGarnishment(
            garnishment_id=f"G-{case.case_id}", customer_id=customer.customer_id,
            case_number=order.case_number, issuer_name=order.issuer_name,
            creditor_name=order.creditor_name or "?", creditor_type=order.creditor_type,
            total_due=order.total_due, monthly_periodic_take=decision.seizable_periodic,
            registered_at=case.updated_at))
    elif case.status == CaseStatus.LIFTED:
        target = order.references_case_number or order.case_number
        for case_id in [k for k, (sid, nid, g) in REGISTERED.items()
                        if sid == case.scenario_id and nid == customer.national_id and g.case_number == target]:
            del REGISTERED[case_id]


def _emit_routed(sink: EventSink, mod) -> None:
    """Documentul nu e o poprire: spunem unde a plecat și marcăm agenții PopririZero ca neaplicabili,
    ca UI-ul să nu-i arate „în așteptare” la nesfârșit (ex. S8, cerere de la Poliție)."""
    target = f"modulul „{mod.info.name}” (în roadmap)" if mod else "un ofițer (tip de document necunoscut)"
    sink.emit(AgentName.INTAKE_ROUTER, AgentStatus.COMPLETED, f"Document redirecționat către {target}",
              {"module_id": mod.info.module_id if mod else None})
    for agent in AgentName:
        if agent != AgentName.INTAKE_ROUTER:
            sink.emit(agent, AgentStatus.SKIPPED, "Nu se aplică: documentul nu este o poprire", {})


def _audit_entries(case: Case, sink: EventSink) -> list[AuditEntry]:
    """Ce s-a decis la această rulare: pașii agenților, regulile aplicate, excepțiile ridicate."""
    entries = [AuditEntry(timestamp=ev.timestamp, actor=ev.agent.value, action=ev.status.value,
                          details={"message": ev.message, **ev.data})
               for ev in sink.events]
    if case.decision:
        entries += [AuditEntry(timestamp=case.updated_at, actor="RULE_ENGINE", action="RULE_APPLIED",
                               details=r.model_dump(mode="json"))
                    for r in case.decision.rules_applied]
    entries += [AuditEntry(timestamp=case.updated_at, actor=e.agent.value, action="EXCEPTION_RAISED",
                           details=e.model_dump(mode="json"))
                for e in case.exceptions]
    return entries
