"""Receipt scan with a real Tesseract, skipped when Tesseract is not installed."""

import io

import pytest

from app.ai import ocr
from app.config import get_settings

PIL = pytest.importorskip("PIL.Image")
pytesseract = pytest.importorskip("pytesseract")


def _installed() -> bool:
    cfg = get_settings()
    if cfg.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_cmd
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _installed(), reason="Tesseract is not installed")
def test_scan_reads_total_date_and_vendor():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (700, 420), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(["Green Bean Supplies", "Date: 2026-10-12", "Coffee beans 1,250.00",
                              "Packaging 300.00", "Total 1,550.00"]):
        draw.text((30, 30 + i * 70), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    result = ocr.scan(buf.getvalue(), "image/png", "off")
    assert result["engine"] == "tesseract"
    assert result["amount"] == 1550.0 and result["date"] == "2026-10-12"
    assert result["vendor"] == "Green Bean Supplies"
