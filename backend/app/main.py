"""Serverul FastAPI și Store-ul de dosare. Proprietar: Om2.

Acest fișier expune toate endpoint-urile HTTP și SSE (Server-Sent Events) pe care
le consumă Frontend-ul (Om4 și Om5).
"""
from datetime import datetime
from pathlib import Path
import json
import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import config
from app.contracts import (
    BankSnapshot, Case, CaseStatus, CaseSummary, CreateCaseFromScenario,
    DocType, IncomingDocument, ModuleInfo, ReviewAction, Scenario, ScenarioInfo,
)
from app.core.events import EventSink, now
from app.core.modules import module_for, registry
from app.core.router import classify_document

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


def load_scenario(scenario_id: str) -> Scenario:
    """Încarcă un scenariu sintetic din data/scenarios/{scenario_id}.json."""
    path = config.SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Scenariul {scenario_id} nu există în {config.SCENARIOS_DIR}")
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_enabled": config.llm_enabled(), "model": config.LLM_MODEL}


@app.get("/api/modules", response_model=list[ModuleInfo])
def list_modules():
    """Returnează toate modulele platformei LexOps (PopririZero activ + cele din roadmap)."""
    return [m.info for m in registry().values()]


@app.get("/api/scenarios", response_model=list[ScenarioInfo])
def list_scenarios():
    """Returnează lista scenariilor sintetice pregătite de Om3."""
    items: list[ScenarioInfo] = []
    if config.SCENARIOS_DIR.exists():
        for p in sorted(config.SCENARIOS_DIR.glob("*.json")):
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
async def upload_case_document(file: UploadFile = File(...), scenario_id: str = "S1"):
    """TODO(Om2): Preia un PDF încărcat manual în UI, extrage textul și îl rulează pe BankSnapshot-ul lui scenario_id."""
    raise HTTPException(status_code=501, detail="TODO Om2: implementează upload PDF cu app.core.pdf_text.bytes_to_text")


@app.get("/api/cases/{case_id}", response_model=Case)
def get_case(case_id: str):
    if case_id not in CASES:
        raise HTTPException(status_code=404, detail="Dosarul nu a fost găsit")
    return CASES[case_id]


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


def _run_pipeline(case: Case, bank: BankSnapshot, review: ReviewAction | None = None) -> Case:
    sink = EventSink(case.case_id)
    doc_type, _conf, _reason = classify_document(case.document, sink.emit)
    case.doc_type = doc_type
    mod = module_for(doc_type)

    if mod is None or mod.info.status.value == "ROADMAP":
        case.module_id = mod.info.module_id if mod else "necunoscut"
        case.status = CaseStatus.ROUTED_TO_OTHER_MODULE
    else:
        case.module_id = mod.info.module_id
        case = mod.process(case, bank, sink.emit, review=review)

    case.updated_at = now()
    EVENTS[case.case_id] = [e.model_dump(mode="json") for e in sink.events]
    return case
