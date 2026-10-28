"""Extragerea textului din PDF-uri. Proprietar: Om1 (cu Om3 pentru PDF-urile de test).

- PDF digital: PyMuPDF (rapid, exact) + normalizare spații/ligaturi.
- PDF scanat (fără strat de text): fallback OCR opțional (dacă e instalat rapidocr_onnxruntime).
"""
import re
from pathlib import Path


def _clean_pdf_text(raw: str) -> str:
    """Curăță artefacte comune din PDF-urile generate sau scanate."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _try_ocr_on_doc(doc) -> str:
    """Fallback opțional OCR pentru PDF-uri scanate (nu blochează dacă biblioteca nu e instalată)."""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        ocr = RapidOCR()
        lines: list[str] = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            result, _ = ocr(pix.tobytes("png"))
            if result:
                lines.extend(item[1] for item in result if len(item) > 1)
        return "\n".join(lines)
    except Exception:
        return ""


def pdf_to_text(path: str | Path) -> str:
    import fitz  # PyMuPDF
    with fitz.open(str(path)) as doc:
        text = "\n".join(page.get_text() for page in doc)
        if len(text.strip()) < 30:
            ocr_text = _try_ocr_on_doc(doc)
            if ocr_text:
                text = ocr_text
    return _clean_pdf_text(text)


def bytes_to_text(data: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        import fitz
        with fitz.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
            if len(text.strip()) < 30:
                ocr_text = _try_ocr_on_doc(doc)
                if ocr_text:
                    text = ocr_text
            return _clean_pdf_text(text)
    return _clean_pdf_text(data.decode("utf-8", errors="replace"))
