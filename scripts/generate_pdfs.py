"""Generator de PDF-uri sintetice pentru adresele de poprire și răspunsul băncii. Proprietar: Om3.

Funcționalitate:
1. Generează PDF-uri din fiecare scenariu `data/scenarios/S*.json` în `data/pdfs/{scenario_id}.pdf`
   folosind `reportlab` cu suport Unicode complet pentru diacritice românești (ă, â, î, ș, ț)
   și 3 layout-uri distincte (BEJ clasic, Adresă Sistare, Cerere Autoritate).
2. `render_bank_response_pdf(case_id, letter_text, output_dir) -> Path` generează PDF-ul oficial
   de răspuns al băncii cu antetul Raiffeisen Bank.

Rulare:
    python scripts/generate_pdfs.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import config


# --------------- Înregistrare Font Unicode (Diacritice Românești) ---------------

def _register_unicode_fonts() -> tuple[str, str, str]:
    """Înregistrează fonturi TrueType cu suport UTF-8 complet (Windows Arial / Linux DejaVu)."""
    candidates = [
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/ariali.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        ),
    ]
    for reg, bold, italic in candidates:
        if reg.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("DocFont", str(reg)))
            pdfmetrics.registerFont(TTFont("DocFont-Bold", str(bold)))
            it_path = italic if italic.exists() else reg
            pdfmetrics.registerFont(TTFont("DocFont-Italic", str(it_path)))
            pdfmetrics.registerFontFamily(
                "DocFont",
                normal="DocFont",
                bold="DocFont-Bold",
                italic="DocFont-Italic",
                boldItalic="DocFont-Bold",
            )
            return "DocFont", "DocFont-Bold", "DocFont-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT_REGULAR, FONT_BOLD, FONT_ITALIC = _register_unicode_fonts()

# --------------- Culori & Stiluri Raiffeisen & Legal ---------------

RAIFFEISEN_YELLOW = HexColor("#FFC72C")
RAIFFEISEN_BLACK = HexColor("#1A1A1A")
DARK_GREY = HexColor("#444444")
LIGHT_GREY = HexColor("#F5F5F5")
BORDER_GREY = HexColor("#CCCCCC")
NAVY_BLUE = HexColor("#003366")
CRIMSON_RED = HexColor("#A80000")

styles = getSampleStyleSheet()

STYLE_BEJ_HEADER = ParagraphStyle(
    "BejHeader",
    parent=styles["Normal"],
    fontName=FONT_BOLD,
    fontSize=11,
    leading=14,
    alignment=TA_CENTER,
    spaceAfter=4,
)
STYLE_BEJ_SUBHEADER = ParagraphStyle(
    "BejSubHeader",
    parent=styles["Normal"],
    fontName=FONT_REGULAR,
    fontSize=9,
    leading=12,
    alignment=TA_CENTER,
    textColor=DARK_GREY,
    spaceAfter=6,
)
STYLE_OBJECT = ParagraphStyle(
    "ObjectTitle",
    parent=styles["Normal"],
    fontName=FONT_BOLD,
    fontSize=12,
    leading=15,
    alignment=TA_CENTER,
    spaceBefore=8,
    spaceAfter=12,
)
STYLE_BODY = ParagraphStyle(
    "Body",
    parent=styles["Normal"],
    fontName=FONT_REGULAR,
    fontSize=9.5,
    leading=13.5,
    alignment=TA_JUSTIFY,
    spaceAfter=6,
)
STYLE_SIGNATURE = ParagraphStyle(
    "Signature",
    parent=styles["Normal"],
    fontName=FONT_BOLD,
    fontSize=9,
    leading=12,
    alignment=TA_LEFT,
)
STYLE_SMALL = ParagraphStyle(
    "Small",
    parent=styles["Normal"],
    fontName=FONT_ITALIC,
    fontSize=8,
    leading=10,
    textColor=DARK_GREY,
)


# --------------- Generare PDF scenarii intrare ---------------

def _build_bej_classic(doc_data: dict, out_path: Path) -> None:
    """Layout clasic: Birou Executor Judecătoresc."""
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story = []
    text = doc_data.get("text", "")
    lines = [l for l in text.split("\n") if l.strip()]

    # Antet BEJ
    if lines:
        story.append(Paragraph(lines[0], STYLE_BEJ_HEADER))
    if len(lines) > 1:
        story.append(Paragraph(lines[1], STYLE_BEJ_SUBHEADER))
    if len(lines) > 2 and "Data:" in lines[2]:
        story.append(Paragraph(lines[2], STYLE_BEJ_SUBHEADER))

    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=black, spaceAfter=10))

    # Către & Obiect
    start_body = 1
    for i, line in enumerate(lines[1:], start=1):
        if line.startswith("CĂTRE:"):
            story.append(Paragraph(f"<b>{line}</b>", STYLE_BODY))
        elif line.startswith("Obiect:"):
            story.append(Paragraph(line, STYLE_OBJECT))
            start_body = i + 1
            break

    # Corpul adresei
    for line in lines[start_body:]:
        if any(prefix in line for prefix in [
            "Debitor:", "Creditor:", "Natura creanței:", "Debit principal:",
            "Cheltuieli de executare:", "Total de recuperat:", "Cont consemnare",
            "Sumele reținute vor fi consemnate",
        ]):
            story.append(Paragraph(f"<b>{line}</b>", STYLE_BODY))
        else:
            story.append(Paragraph(line, STYLE_BODY))

    story.append(Spacer(1, 1.2 * cm))

    # Bloc semnătură & ștampilă executor
    sig_data = [
        ["", "EXECUTOR JUDECĂTORESC,"],
        ["", "Semnătură și ștampilă oficială L.S."],
    ]
    sig_table = Table(sig_data, colWidths=[9 * cm, 7 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (1, 0), (1, 0), FONT_BOLD),
        ("FONTNAME", (1, 1), (1, -1), FONT_ITALIC),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (1, 1), (1, -1), DARK_GREY),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(sig_table)

    doc.build(story)


def _build_sistare(doc_data: dict, out_path: Path) -> None:
    """Layout distinct pentru Adresa de Sistare / Ridicare poprire."""
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story = []
    text = doc_data.get("text", "")
    lines = [l for l in text.split("\n") if l.strip()]

    if lines:
        story.append(Paragraph(lines[0], STYLE_BEJ_HEADER))
    for line in lines[1:3]:
        if "Dosarul" in line or "Data:" in line:
            story.append(Paragraph(line, STYLE_BEJ_SUBHEADER))

    story.append(Spacer(1, 0.4 * cm))

    # Banner vizual pentru SISTARE
    banner = Table([["ADRESĂ DE SISTARE A POPRIRII"]], colWidths=[16 * cm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CRIMSON_RED),
        ("TEXTCOLOR", (0, 0), (-1, -1), white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 0.6 * cm))

    for line in lines[3:]:
        if any(prefix in line for prefix in ["Debitor:", "Creditor:", "Total de recuperat:"]):
            story.append(Paragraph(f"<b>{line}</b>", STYLE_BODY))
        else:
            story.append(Paragraph(line, STYLE_BODY))

    story.append(Spacer(1, 1.2 * cm))

    sig_data = [
        ["", "EXECUTOR JUDECĂTORESC,"],
        ["", "Semnătură și ștampilă L.S."],
    ]
    sig_table = Table(sig_data, colWidths=[9 * cm, 7 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (1, 0), (1, 0), FONT_BOLD),
        ("FONTNAME", (1, 1), (1, -1), FONT_ITALIC),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
    ]))
    story.append(sig_table)

    doc.build(story)


def _build_autoritate(doc_data: dict, out_path: Path) -> None:
    """Layout oficial pentru cerere de la autorități publice (Poliție/DNA/Parchet)."""
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story = []
    text = doc_data.get("text", "")
    lines = [l for l in text.split("\n") if l.strip()]

    # Antet Guvernamental / MAI
    gov_table = Table(
        [["ROMÂNIA — MINISTERUL AFACERILOR INTERNE"],
         [lines[0] if lines else "INSPECTORATUL GENERAL AL POLIȚIEI ROMÂNE"]],
        colWidths=[16 * cm],
    )
    gov_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_GREY),
        ("TEXTCOLOR", (0, 1), (-1, 1), RAIFFEISEN_BLACK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 1), (-1, 1), FONT_BOLD),
        ("FONTSIZE", (0, 1), (-1, 1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(gov_table)
    story.append(Spacer(1, 0.5 * cm))

    for line in lines[1:]:
        if line.startswith(("1.", "2.", "3.", "4.", "CĂTRE:", "În DOSAR PENAL")):
            story.append(Paragraph(f"<b>{line}</b>", STYLE_BODY))
        else:
            story.append(Paragraph(line, STYLE_BODY))

    story.append(Spacer(1, 1.2 * cm))

    sig_data = [
        ["", "OFIȚER DE POLIȚIE JUDICIARĂ,"],
        ["", "Semnătură și ștampilă oficială L.S."],
    ]
    sig_table = Table(sig_data, colWidths=[9 * cm, 7 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (1, 0), (1, 0), FONT_BOLD),
        ("FONTNAME", (1, 1), (1, -1), FONT_ITALIC),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
    ]))
    story.append(sig_table)

    doc.build(story)


def generate_scenario_pdfs() -> None:
    """Parcurge data/scenarios/*.json și generează PDF-urile în data/pdfs/."""
    out_dir = config.DATA_DIR / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generez PDF-uri pentru scenarii în {out_dir}...")
    for path in sorted(config.SCENARIOS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = raw["scenario_id"]
        doc_data = raw.get("document", {})
        text = doc_data.get("text", "")
        out_path = out_dir / f"{scenario_id}.pdf"

        if "SISTARE" in text.upper():
            _build_sistare(doc_data, out_path)
        elif any(kw in text.upper() for kw in ["INSPECTORATUL", "DOSAR PENAL", "POLITIE", "PARCHET"]):
            _build_autoritate(doc_data, out_path)
        else:
            _build_bej_classic(doc_data, out_path)

        print(f"  [OK] {scenario_id} -> {out_path.name}")

    print(f"Toate PDF-urile au fost generate cu succes în {out_dir}\n")


# --------------- Generare PDF răspuns bancă ---------------

def render_bank_response_pdf(case_id: str, letter_text: str, output_dir: Path | None = None) -> Path:
    """Generează PDF-ul oficial de răspuns cu antetul Raiffeisen Bank."""
    if output_dir is None:
        output_dir = config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{case_id}_raspuns.pdf"

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story = []

    # Antet oficial Raiffeisen Bank
    header_data = [
        ["RAIFFEISEN BANK S.A."],
        ["Departamentul Popriri și Operațiuni Juridice"],
        ["Direcția Operațiuni și Servicii Centrale | Clădirea FCC, București"],
    ]
    header_table = Table(header_data, colWidths=[16 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), RAIFFEISEN_YELLOW),
        ("TEXTCOLOR", (0, 0), (-1, 0), RAIFFEISEN_BLACK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 13),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_GREY),
        ("TEXTCOLOR", (0, 1), (-1, 1), RAIFFEISEN_BLACK),
        ("FONTNAME", (0, 1), (-1, 1), FONT_BOLD),
        ("FONTSIZE", (0, 1), (-1, 1), 9.5),
        ("BACKGROUND", (0, 2), (-1, 2), white),
        ("TEXTCOLOR", (0, 2), (-1, 2), DARK_GREY),
        ("FONTNAME", (0, 2), (-1, 2), FONT_REGULAR),
        ("FONTSIZE", (0, 2), (-1, 2), 7.5),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.8 * cm))

    # Corpul scrisorii de răspuns
    for line in letter_text.split("\n"):
        line_clean = line.strip()
        if not line_clean:
            story.append(Spacer(1, 0.25 * cm))
            continue
        if line_clean.startswith(("Ref.:", "Către:", "Data:")):
            story.append(Paragraph(f"<b>{line_clean}</b>", STYLE_BODY))
        elif line_clean.startswith("RAIFFEISEN BANK"):
            continue
        elif "Cu stimă," in line_clean or "Departamentul" in line_clean:
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph(f"<b>{line_clean}</b>", STYLE_BODY))
        else:
            story.append(Paragraph(line_clean, STYLE_BODY))

    story.append(Spacer(1, 1.2 * cm))

    # Semnătură electronică bancară
    sig_data = [
        ["", "RAIFFEISEN BANK S.A."],
        ["", "Departamentul Popriri și Executări Silite"],
        ["", "[ Semnat electronic conform Regulamentului eIDAS ]"],
    ]
    sig_table = Table(sig_data, colWidths=[8 * cm, 8 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (1, 0), (1, 1), FONT_BOLD),
        ("FONTNAME", (1, 2), (1, 2), FONT_ITALIC),
        ("FONTSIZE", (0, 0), (-1, 1), 9),
        ("FONTSIZE", (1, 2), (1, 2), 7.5),
        ("TEXTCOLOR", (1, 2), (1, 2), DARK_GREY),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
    ]))
    story.append(sig_table)

    doc.build(story)
    return out


if __name__ == "__main__":
    generate_scenario_pdfs()
    print("Testare generare răspuns bancă:")
    demo_letter = (
        "Către: BIROUL EXECUTORULUI JUDECĂTORESC POPESCU ION\n"
        "Data: 28.10.2026\n"
        "Ref.: dosar de executare nr. 1234/2026\n\n"
        "Urmare a adresei de înființare a popririi privind debitorul IONESCU MIHAI (CNP 1850615400011), "
        "vă comunicăm că am procedat la indisponibilizarea sumei de 5800.00 RON din totalul de 15000.00 RON datorați.\n\n"
        "Suma de 5792.00 RON nu a fost indisponibilizată, fiind protejată conform art. 729 CPC "
        "(venituri neurmăribile: alocație copil, diurnă sau sume ce depășesc cota legală de 1/3 din salariu).\n\n"
        "Sumele indisponibilizate vor fi virate în contul de consemnare RO49AAAA1B31007593840000 conform legii.\n\n"
        "Cu stimă,\n"
        "Departamentul Popriri și Executări Silite"
    )
    p = render_bank_response_pdf("DEMO-S1", demo_letter)
    print(f"  [OK] Răspuns salvat la: {p}")
