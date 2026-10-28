"""Extragerea textului din PDF-uri. Proprietar: Om1 (cu Om3 pentru PDF-urile de test).

- PDF digital: PyMuPDF (rapid, exact).
- PDF scanat (fără strat de text): TODO Om1 — OCR local (ex. rapidocr-onnxruntime).
"""
from pathlib import Path


def pdf_to_text(path: str | Path) -> str:
    import fitz  # PyMuPDF
    with fitz.open(str(path)) as doc:
        text = "\n".join(page.get_text() for page in doc)
    if len(text.strip()) < 30:
        # TODO(Om1): document scanat -> OCR. Până atunci întoarcem ce avem.
        pass
    return text


def bytes_to_text(data: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        import fitz
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)
    return data.decode("utf-8", errors="replace")
