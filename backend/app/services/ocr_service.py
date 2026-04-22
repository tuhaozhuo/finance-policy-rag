from pathlib import Path

from app.core.config import get_settings


class OCRService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def extract_text(self, file_path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
            from pytesseract import TesseractNotFoundError
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("OCR依赖未安装，请安装 pytesseract 和 pillow") from exc

        try:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image, lang=self.settings.ocr_lang).strip()
        except TesseractNotFoundError as exc:
            raise RuntimeError("系统未安装 tesseract，可改用 doc/docx/pdf 或在服务器安装 tesseract") from exc
