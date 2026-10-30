"""Turn uploaded CV files into reviewable text.

Parsing happens locally and entirely in memory: uploaded bytes are never
written to disk or logged, and only the extracted text is returned to the
browser. The user reviews or edits that text before the existing CV analyser
scrubs it and calls the model.

PDF support uses ``pypdf`` (imported lazily so the rest of the app still
starts if it is missing). DOCX support uses only the standard library.
"""

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from .cv_profile import MAX_CV_CHARS

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGES = 40
MAX_TEXT_CHARS = MAX_CV_CHARS
MAX_DOCX_XML_BYTES = 25 * 1024 * 1024
MIN_TEXT_CHARS = 40

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_NS = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_XML_DECL_RE = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)


class ExtractError(ValueError):
    """Raised when an upload cannot be turned into usable CV text."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_text(text):
    """Normalise whitespace and drop control characters."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = _CONTROL_RE.sub("", text)
    lines = [" ".join(line.split()) for line in text.split("\n")]

    out = []
    after_blank = True
    for line in lines:
        if line:
            out.append(line)
            after_blank = False
        elif not after_blank:
            out.append("")
            after_blank = True
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def _sniff(data):
    """Identify the payload from its bytes, never from its extension."""
    if data.startswith(_ZIP_MAGIC):
        return "docx"
    if data[:1024].find(_PDF_MAGIC) != -1:
        return "pdf"
    if data.startswith(_OLE_MAGIC):
        raise ExtractError(
            "Legacy .doc files are not supported. Save the file as .docx or "
            "PDF and try again."
        )
    head = data[:512].lstrip()
    if head[:5].lower() == b"{\\rtf":
        raise ExtractError(
            "RTF files are not supported. Save the file as .docx or PDF and "
            "try again."
        )
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "text"
    if b"\x00" in data[:8192]:
        raise ExtractError(
            "That file does not look like a PDF, DOCX or text document."
        )
    return "text"


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------

def _read_text_file(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ExtractError("That text file could not be decoded.") from exc

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractError("That text file could not be decoded.")


# ---------------------------------------------------------------------------
# DOCX (stdlib only)
# ---------------------------------------------------------------------------

def _read_docx_part(data):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ExtractError("That file is not a valid .docx document.") from exc

    if "word/document.xml" not in archive.namelist():
        raise ExtractError(
            "That file is not a Word .docx document. Legacy .doc files must "
            "be saved as .docx first."
        )

    info = archive.getinfo("word/document.xml")
    if info.file_size > MAX_DOCX_XML_BYTES:
        raise ExtractError("That document is too large to read safely.")

    try:
        # Bound the read as well: a forged header can understate the real
        # expanded size.
        with archive.open("word/document.xml") as handle:
            raw = handle.read(MAX_DOCX_XML_BYTES + 1)
    except (KeyError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ExtractError("That .docx file could not be read.") from exc
    if len(raw) > MAX_DOCX_XML_BYTES:
        raise ExtractError("That document is too large to read safely.")

    # ElementTree expands internal entities. Refuse any document that tries
    # to declare them instead of relying on parser defaults.
    if _XML_DECL_RE.search(raw):
        raise ExtractError("That document contains unsupported XML declarations.")
    return raw


def _iter_content(element):
    """Walk descendants in document order, skipping compatibility fallbacks.

    Word stores text boxes twice (``mc:Choice`` and ``mc:Fallback``) for
    older readers. Reading both would duplicate every text box.
    """
    for child in element:
        if child.tag == _MC_NS + "Fallback":
            continue
        yield child
        yield from _iter_content(child)


def _paragraph_text(paragraph):
    parts = []
    for node in _iter_content(paragraph):
        if node.tag == _W_NS + "t":
            parts.append(node.text or "")
        elif node.tag == _W_NS + "tab":
            parts.append("\t")
        elif node.tag in (_W_NS + "br", _W_NS + "cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _collect_paragraphs(element, lines):
    for child in element:
        if child.tag == _MC_NS + "Fallback":
            continue
        if child.tag == _W_NS + "p":
            text = _paragraph_text(child)
            if text:
                lines.append(text)
        else:
            _collect_paragraphs(child, lines)


def _read_docx(data):
    raw = _read_docx_part(data)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ExtractError("That .docx document could not be parsed.") from exc

    lines = []
    try:
        _collect_paragraphs(root, lines)
    except RecursionError as exc:
        raise ExtractError("That .docx document is too complex to read.") from exc
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _read_pdf(data):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractError(
            "PDF support needs the pypdf package. Run "
            "pip install -r requirements.txt and restart J-Search."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ExtractError("That PDF could not be opened. It may be damaged.") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise ExtractError(
                "That PDF is password-protected. Remove the password and try again."
            ) from exc
        if not unlocked:
            raise ExtractError(
                "That PDF is password-protected. Remove the password and try again."
            )

    try:
        total_pages = len(reader.pages)
    except Exception as exc:
        raise ExtractError("That PDF could not be opened. It may be damaged.") from exc

    warnings = []
    chunks = []
    empty_pages = 0
    for page in reader.pages[:MAX_PAGES]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            chunks.append(text)
        else:
            empty_pages += 1

    body = "\n\n".join(chunks)
    if len(_clean_text(body)) < MIN_TEXT_CHARS:
        raise ExtractError(
            "No selectable text was found. This looks like a scanned PDF; OCR "
            "is not supported yet."
        )
    if total_pages > MAX_PAGES:
        warnings.append(
            "Only the first " + str(MAX_PAGES) + " of " + str(total_pages) +
            " pages were read."
        )
    if empty_pages:
        warnings.append(
            str(empty_pages) + " page(s) contained no selectable text and may "
            "be images."
        )
    return body, min(total_pages, MAX_PAGES), warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_text(data):
    """Return ``{text, kind, pages, truncated, warnings}`` for an upload.

    Nothing is written to disk. Raises :class:`ExtractError` with a
    user-facing message when the payload is unsupported or unreadable.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ExtractError("The uploaded file is empty.")

    data = bytes(data)
    if not data:
        raise ExtractError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ExtractError("That file is larger than 10 MB.")

    kind = _sniff(data)
    warnings = []
    pages = None

    if kind == "pdf":
        text, pages, warnings = _read_pdf(data)
    elif kind == "docx":
        text = _read_docx(data)
    else:
        text = _read_text_file(data)

    text = _clean_text(text)
    if len(text) < MIN_TEXT_CHARS:
        raise ExtractError(
            "That file did not contain enough readable text. If it is a "
            "scanned document, OCR is not supported yet."
        )

    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]
        warnings.append(
            "Only the first " + str(MAX_TEXT_CHARS) + " characters were kept."
        )

    return {
        "text": text,
        "kind": kind,
        "pages": pages,
        "truncated": truncated,
        "warnings": warnings,
    }
