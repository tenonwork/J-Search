import io
import unittest
import zipfile
from unittest import mock
from xml.sax.saxutils import escape

from app import cv_import

try:
    from pypdf import PdfWriter
    HAS_PYPDF = True
except ImportError:  # pragma: no cover - requirements includes pypdf
    PdfWriter = None
    HAS_PYPDF = False

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def paragraph(text):
    return (
        '<w:p><w:r><w:t xml:space="preserve">' + escape(text) + "</w:t></w:r></w:p>"
    )


def build_docx(body_xml):
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="' + W_NS + '"><w:body>' + body_xml +
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def build_pdf(lines):
    """Build a tiny one-page PDF with Helvetica text."""
    commands = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            commands.append("0 -16 Td")
        commands.append("(" + escaped + ") Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" +
            stream + b"\nendstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"

    startxref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += ("%010d 00000 n \n" % offset).encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() +
        b" /Root 1 0 R >>\nstartxref\n" + str(startxref).encode() +
        b"\n%%EOF\n"
    )
    return bytes(out)


class DocxTests(unittest.TestCase):
    def test_paragraphs_and_table_cells_are_extracted(self):
        body = paragraph("Jane Doe - Backend Engineer") + (
            "<w:tbl><w:tr><w:tc>" +
            paragraph("Skills: Python, PostgreSQL, React, TypeScript") +
            "</w:tc></w:tr></w:tbl>"
        )
        result = cv_import.extract_text(build_docx(body))
        self.assertEqual(result["kind"], "docx")
        self.assertIn("Jane Doe - Backend Engineer", result["text"])
        self.assertIn("Python, PostgreSQL, React, TypeScript", result["text"])

    def test_text_boxes_are_extracted(self):
        body = (
            "<w:p><w:r><w:pict><w:txbxContent>" +
            paragraph("Inside a text box: Django, Docker and PostgreSQL") +
            "</w:txbxContent></w:pict></w:r></w:p>"
        )
        result = cv_import.extract_text(build_docx(body))
        self.assertIn(
            "Inside a text box: Django, Docker and PostgreSQL", result["text"]
        )

    def test_compatibility_fallback_is_not_duplicated(self):
        body = (
            '<mc:AlternateContent xmlns:mc="'
            'http://schemas.openxmlformats.org/markup-compatibility/2006">'
            "<mc:Choice Requires=\"wps\">" +
            paragraph("Skills: Python, PostgreSQL, React, TypeScript") +
            "</mc:Choice><mc:Fallback>" +
            paragraph("Skills: Python, PostgreSQL, React, TypeScript") +
            "</mc:Fallback></mc:AlternateContent>"
        )
        result = cv_import.extract_text(build_docx(body))
        self.assertEqual(result["text"].count("TypeScript"), 1)

    def test_xml_entities_are_rejected(self):
        body = (
            '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "boom">]>' +
            '<w:document xmlns:w="' + W_NS + '"><w:body>' +
            paragraph("Python PostgreSQL React TypeScript") + "</w:body></w:document>"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", body)
        with self.assertRaisesRegex(cv_import.ExtractError, "unsupported XML"):
            cv_import.extract_text(buffer.getvalue())

    def test_zip_without_word_document_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
        with self.assertRaisesRegex(cv_import.ExtractError, "not a Word"):
            cv_import.extract_text(buffer.getvalue())

    def test_short_docx_is_rejected(self):
        with self.assertRaisesRegex(cv_import.ExtractError, "enough readable text"):
            cv_import.extract_text(build_docx(paragraph("Python")))

    def test_oversized_docx_xml_is_rejected(self):
        with mock.patch.object(cv_import, "MAX_DOCX_XML_BYTES", 8):
            with self.assertRaisesRegex(cv_import.ExtractError, "too large"):
                cv_import.extract_text(
                    build_docx(paragraph("Python, PostgreSQL, React, TypeScript"))
                )


class TextTests(unittest.TestCase):
    def test_plain_text_is_normalised(self):
        result = cv_import.extract_text(
            b"  Jane Doe  \r\n\r\n\r\nPython, PostgreSQL and React.  \r\n"
            b"Backend engineer with eight years of experience.  "
        )
        self.assertEqual(result["kind"], "text")
        self.assertIn("Jane Doe", result["text"])
        self.assertIn("Python, PostgreSQL and React.", result["text"])
        self.assertNotIn("\r", result["text"])
        self.assertNotIn("  ", result["text"])

    def test_empty_upload_is_rejected(self):
        with self.assertRaisesRegex(cv_import.ExtractError, "empty"):
            cv_import.extract_text(b"")

    def test_legacy_doc_is_rejected(self):
        payload = cv_import._OLE_MAGIC + b"\x00" * 128
        with self.assertRaisesRegex(cv_import.ExtractError, "Legacy .doc"):
            cv_import.extract_text(payload)

    def test_binary_payload_is_rejected(self):
        with self.assertRaisesRegex(cv_import.ExtractError, "does not look like"):
            cv_import.extract_text(b"\x00\x01\x02\x03" * 20)

    def test_size_limit(self):
        with mock.patch.object(cv_import, "MAX_UPLOAD_BYTES", 64):
            with self.assertRaisesRegex(cv_import.ExtractError, "larger than"):
                cv_import.extract_text(b"x" * 65)

    def test_truncation_keeps_existing_limit(self):
        with mock.patch.object(cv_import, "MAX_TEXT_CHARS", 60):
            result = cv_import.extract_text(b"a" * 200)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), 60)
        self.assertTrue(any("60 characters" in item for item in result["warnings"]))


@unittest.skipUnless(HAS_PYPDF, "pypdf is not installed")
class PdfTests(unittest.TestCase):
    def test_text_pdf_is_extracted(self):
        result = cv_import.extract_text(
            build_pdf(["Jane Doe - Backend Engineer", "Python, PostgreSQL, React"])
        )
        self.assertEqual(result["kind"], "pdf")
        self.assertEqual(result["pages"], 1)
        self.assertIn("Python", result["text"])
        self.assertIn("PostgreSQL", result["text"])

    def test_blank_pdf_points_at_ocr(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaisesRegex(cv_import.ExtractError, "scanned PDF"):
            cv_import.extract_text(buffer.getvalue())

    def test_password_protected_pdf_is_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("secret")
        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaisesRegex(cv_import.ExtractError, "password-protected"):
            cv_import.extract_text(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
