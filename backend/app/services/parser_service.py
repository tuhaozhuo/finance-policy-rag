from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services.ocr_service import OCRService


@dataclass
class ParsedContent:
    text: str
    parser: str
    ocr_used: bool = False


class DocumentParser:
    def __init__(self, ocr_service: OCRService) -> None:
        self.ocr_service = ocr_service

    def parse(self, file_path: Path) -> ParsedContent:
        suffix = file_path.suffix.lower()

        if suffix == ".docx":
            return ParsedContent(text=self._parse_docx(file_path), parser="docx")
        if suffix == ".pdf":
            return ParsedContent(text=self._parse_pdf(file_path), parser="pdf")
        if suffix == ".doc":
            return ParsedContent(text=self._parse_doc(file_path), parser="doc")
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
            return ParsedContent(text=self.ocr_service.extract_text(file_path), parser="image_ocr", ocr_used=True)

        return ParsedContent(text=self._parse_plain(file_path), parser="plain")

    def _parse_docx(self, file_path: Path) -> str:
        from docx import Document

        doc = Document(str(file_path))
        return "\n".join(p.text.strip() for p in doc.paragraphs if p.text and p.text.strip())

    def _parse_pdf(self, file_path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages:
            pages.append((page.extract_text() or "").strip())
        return "\n".join(item for item in pages if item)

    def _parse_doc(self, file_path: Path) -> str:
        commands = [
            ["antiword", str(file_path)],
            ["catdoc", str(file_path)],
            ["textutil", "-convert", "txt", "-stdout", str(file_path)],
        ]

        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            except FileNotFoundError:
                continue

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        raise RuntimeError(".doc 解析失败：请安装 antiword/catdoc，或先转为 docx")

    def _parse_plain(self, file_path: Path) -> str:
        raw = file_path.read_bytes()
        for encoding in ("utf-8", "gb18030", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise RuntimeError(f"无法解析文件编码: {file_path}")
