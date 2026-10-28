"""Generator de PDF-uri sintetice pentru adresele de poprire și răspunsul băncii. Proprietar: Om3.

TODO(Om3):
1. Din fiecare scenariu `data/scenarios/S*.json`, generează un PDF în `data/pdfs/{scenario_id}.pdf`
   folosind `reportlab` (cu 2-3 layout-uri diferite: BEJ clasic, ANAF tabelar, Adresă Sistare).
2. Implementează funcția `render_bank_response_pdf(case_id, text) -> Path` care salvează în
   `data/output/{case_id}_raspuns.pdf` adresa oficială cu antetul Raiffeisen Bank.
"""
from pathlib import Path


def generate_scenario_pdfs() -> None:
    # TODO(Om3): parcurge data/scenarios/*.json și generează PDF-urile cu reportlab
    print("TODO Om3: implementează generate_scenario_pdfs() în scripts/generate_pdfs.py")


def render_bank_response_pdf(case_id: str, letter_text: str, output_dir: Path) -> Path:
    # TODO(Om3): generează PDF-ul de răspuns către executor
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{case_id}_raspuns.pdf"
    out.write_text(letter_text, encoding="utf-8")
    return out


if __name__ == "__main__":
    generate_scenario_pdfs()
