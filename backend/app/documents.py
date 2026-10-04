"""Local document text extraction and small, explainable NLP helpers."""

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree


SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".log", ".pdf", ".docx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
}
MAX_EXTRACTED_CHARS = 2_000_000
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 160


def capabilities():
    try:
        import pypdf  # noqa: F401
        digital_pdf = True
    except ImportError:
        digital_pdf = False
    try:
        import fitz  # noqa: F401
        scanned_pdf_renderer = True
    except ImportError:
        scanned_pdf_renderer = False
    return {
        "digital_pdf_text": digital_pdf,
        "tesseract_ocr": bool(shutil.which("tesseract")),
        "scanned_pdf_renderer": scanned_pdf_renderer,
    }


def _decode_text(data):
    try:
        return data.decode("utf-8-sig"), "Text decoded as UTF-8."
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "Some characters could not be decoded and were replaced."


def _ocr_image(path):
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return "", "OCR is unavailable on this machine. Install Tesseract OCR to process scanned files and images."
    try:
        result = subprocess.run(
            [tesseract, str(path), "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "", "OCR took too long to process this image. Try a smaller or clearer file."
    if result.returncode != 0:
        return "", "OCR could not read this image. Check that it is a supported, readable image."
    text = result.stdout.strip()
    return text, "Text extracted locally with Tesseract OCR." if text else "OCR found no readable text."


def _ocr_pdf(path):
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return "", "This PDF has no text layer. Install Tesseract OCR to process scanned pages."
    try:
        import fitz
    except ImportError:
        return "", "This PDF has no text layer. PyMuPDF and Tesseract are needed for scanned-page OCR."
    parts = []
    try:
        with fitz.open(path) as pdf:
            for page in pdf[:10]:
                image = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).tobytes("png")
                try:
                    result = subprocess.run(
                        [tesseract, "stdin", "stdout", "-l", "eng"],
                        input=image,
                        capture_output=True,
                        text=False,
                        timeout=20,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    continue
                if result.returncode == 0 and result.stdout.strip():
                    parts.append(result.stdout.decode("utf-8", errors="replace").strip())
    except Exception:
        return "", "The scanned PDF could not be rendered for local OCR."
    if not parts:
        return "", "OCR found no readable text in the first 10 pages."
    return "\n\n".join(parts), "Scanned PDF pages were read locally with Tesseract OCR."


def _ocr_pdf_pages(path):
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return [], "This PDF has no text layer. OCR required: install Tesseract to process scanned pages."
    try:
        import fitz
    except ImportError:
        return [], "This PDF has no text layer. OCR required: PyMuPDF and Tesseract are needed for scanned pages."
    pages = []
    try:
        with fitz.open(path) as pdf:
            for index, page in enumerate(pdf[:250]):
                image = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).tobytes("png")
                try:
                    result = subprocess.run(
                        [tesseract, "stdin", "stdout", "-l", "eng"],
                        input=image,
                        capture_output=True,
                        text=False,
                        timeout=20,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    continue
                text = result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else ""
                if text:
                    pages.append((index + 1, text))
    except Exception:
        return [], "The scanned PDF could not be rendered for local OCR."
    if not pages:
        return [], "OCR found no readable text in the scanned pages."
    return pages, "Scanned PDF pages were read locally with Tesseract OCR."


def extract_text(path, extension):
    extension = extension.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported formats: PDF, DOCX, TXT, MD, CSV, JSON, LOG, PNG, JPG, JPEG, TIF, and TIFF.")

    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return "", "PDF text extraction is unavailable. Install the optional pypdf package."
        try:
            reader = PdfReader(str(path))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:250]).strip()
        except Exception:
            return "", "The PDF could not be read. Check that it is not encrypted or damaged."
        if text:
            return text[:MAX_EXTRACTED_CHARS], "Digital PDF text extracted locally."
        text, note = _ocr_pdf(path)
        return text[:MAX_EXTRACTED_CHARS], note

    if extension == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            for paragraph in root.iter(namespace + "p"):
                text = "".join(node.text or "" for node in paragraph.iter(namespace + "t"))
                if text.strip():
                    paragraphs.append(text)
            text = "\n".join(paragraphs)
            return text[:MAX_EXTRACTED_CHARS], "DOCX text extracted locally." if text else "The DOCX contains no readable text."
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            return "", "The DOCX could not be read. Check that it is not damaged."

    if extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        text, note = _ocr_image(path)
        return text[:MAX_EXTRACTED_CHARS], note

    data = Path(path).read_bytes()[:MAX_EXTRACTED_CHARS * 4]
    text, note = _decode_text(data)
    return text[:MAX_EXTRACTED_CHARS], note


def extract_pages(path, extension):
    """Extract page-linked text where the file format provides page boundaries."""
    extension = extension.lower()
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return [], "PDF text extraction is unavailable. Install the optional pypdf package."
        try:
            reader = PdfReader(str(path))
            pages = []
            remaining = MAX_EXTRACTED_CHARS
            for index, page in enumerate(reader.pages[:250]):
                text = (page.extract_text() or "").strip()
                if text and remaining > 0:
                    text = text[:remaining]
                    pages.append((index + 1, text))
                    remaining -= len(text)
            if pages:
                return pages, "Digital PDF text extracted page by page."
        except Exception:
            return [], "The PDF could not be read. Check that it is not encrypted or damaged."
        return _ocr_pdf_pages(path)

    text, note = extract_text(path, extension)
    text = text[:MAX_EXTRACTED_CHARS]
    if not text.strip():
        return [], note
    if extension == ".docx":
        # DOCX has no stable page boundaries until rendered by a word processor.
        return [(None, text)], note + " Page numbers are unavailable for DOCX files."
    if extension in {".txt", ".md", ".csv", ".json", ".log"}:
        chunks = text.split("\f")
        pages = [(index + 1, part.strip()) for index, part in enumerate(chunks) if part.strip()]
        return pages or [(1, text)], note
    return [(1, text)], note


def extract_entities(text):
    if not text:
        return {"well_codes": [], "formations": [], "depths_m": [], "event_types": [], "severities": []}
    upper = text.upper()
    well_codes = sorted(set(re.findall(r"\b[A-Z]{1,3}-\d{2,5}\b", upper)))[:40]
    formations = sorted(set(re.findall(r"\bF[1-4]\b", upper)))
    depth_pattern = r"\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,4}(?:\.\d+)?)\s*(?:M|METRES?|METERS?)\b"
    depths = sorted({int(float(match.group(1).replace(",", ""))) for match in re.finditer(depth_pattern, upper)})[:40]
    event_terms = {
        "MUD_LOSS": ("MUD LOSS", "LOST CIRCULATION", "LOSSES", "REDUCED RETURNS"),
        "STUCK_PIPE": ("STUCK PIPE", "OVERPULL", "TIGHT HOLE"),
        "KICK_PRESSURE": ("KICK", "INFLUX", "FLOW CHECK", "PIT GAIN", "OVERPRESSURE"),
        "TORQUE_DRAG": ("TORQUE", "DRAG", "HIGH SIDE FORCE"),
        "CEMENTING": ("CEMENT", "CASING", "CEMENT RETURNS"),
    }
    event_types = [kind for kind, phrases in event_terms.items() if any(phrase in upper for phrase in phrases)]
    severities = [level for level in ("HIGH", "MEDIUM", "LOW") if re.search(r"\b" + level + r"\b", upper)]
    return {
        "well_codes": well_codes,
        "formations": formations,
        "depths_m": depths,
        "event_types": event_types,
        "severities": severities,
    }


def make_chunks(text):
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + CHUNK_SIZE)
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def make_page_chunks(pages):
    """Chunk page text without losing the source page used for citations."""
    result = []
    for page_number, text in pages:
        result.extend((page_number, chunk) for chunk in make_chunks(text))
    return result


def entities_json(text):
    return json.dumps(extract_entities(text), ensure_ascii=False, separators=(",", ":"))
