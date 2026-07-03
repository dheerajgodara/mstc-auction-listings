from pathlib import Path
from unittest.mock import patch

from scraper.thumbnails import generate_thumbnail


def test_thumbnail_generation_skips_when_renderer_unavailable(tmp_path: Path):
    src = tmp_path / "sample.pdf"
    dst = tmp_path / "thumb.webp"
    src.write_bytes(b"%PDF-1.4\n" + b"0" * 600)
    with patch("scraper.thumbnails._thumb_from_pdf_fitz", return_value=False), patch(
        "scraper.thumbnails._thumb_from_pdf_pdftoppm", return_value=False
    ):
        assert generate_thumbnail(src, dst) is False


def test_thumbnail_from_image(tmp_path: Path):
    try:
        from PIL import Image
    except ImportError:
        return
    src = tmp_path / "photo.jpg"
    dst = tmp_path / "thumb.webp"
    Image.new("RGB", (800, 600), color=(120, 80, 40)).save(src, "JPEG")
    assert generate_thumbnail(src, dst) is True
    assert dst.is_file()
