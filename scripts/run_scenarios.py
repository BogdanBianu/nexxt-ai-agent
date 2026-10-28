"""Script de evaluare pe toate scenariile sintetice (data/scenarios/*.json). Proprietar: Om5.

Rulare:
    python scripts/run_scenarios.py

Verifică pentru fiecare scenariu dacă `status`, `amount_to_hold` și `exception_codes`
corespund cu `expected` din JSON.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.contracts import ReviewAction  # noqa: E402
from app.main import CreateCaseFromScenario, create_case_from_scenario, load_scenario, review_case  # noqa: E402


def main() -> int:
    passed = 0
    total = 0
    for path in sorted(config.SCENARIOS_DIR.glob("*.json")):
        total += 1
        sc = load_scenario(path.stem)
        case = create_case_from_scenario(CreateCaseFromScenario(scenario_id=sc.scenario_id))
        actual_hold = case.decision.amount_to_hold if case.decision else 0
        actual_exc = sorted({e.code.value for e in case.exceptions if not e.resolved})
        exp_exc = sorted(sc.expected.exception_codes)

        ok = (
            case.doc_type == sc.expected.doc_type
            and case.status == sc.expected.status
            and actual_hold == sc.expected.amount_to_hold
            and actual_exc == exp_exc
        )
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {sc.scenario_id} — {sc.title}")
        print(f"       status={case.status.value} (exp {sc.expected.status.value}), "
              f"hold={actual_hold} (exp {sc.expected.amount_to_hold}), "
              f"exc={actual_exc} (exp {exp_exc})")

        if sc.demo_review and sc.expected.amount_after_review is not None:
            reviewed = review_case(case.case_id, ReviewAction.model_validate(sc.demo_review))
            after_hold = reviewed.decision.amount_to_hold if reviewed.decision else 0
            ok_review = after_hold == sc.expected.amount_after_review
            ok = ok and ok_review
            print(f"       după HITL review -> status={reviewed.status.value}, "
                  f"hold={after_hold} (exp {sc.expected.amount_after_review})")

        if ok:
            passed += 1

    print(f"\nRezultat: {passed}/{total} scenarii au trecut.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
