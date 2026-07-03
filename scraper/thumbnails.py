from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_THUMB_WIDTH = 480
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _save_webp(image, output_path: Path) -> bool:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "WEBP", quality=82, method=4)
        return output_path.is_file() and output_path.stat().st_size > 0
    except Exception as exc:
        logger.debug("WEBP save failed for %s: %s", output_path, exc)
        try:
            jpg_path = output_path.with_suffix(".jpg")
            image.save(jpg_path, "JPEG", quality=85)
            if jpg_path.is_file() and jpg_path.stat().st_size > 0:
                if output_path != jpg_path:
                    output_path.unlink(missing_ok=True)
                    jpg_path.rename(output_path.with_suffix(".jpg"))
                return True
        except Exception:
            return False
        return False


def _thumb_from_image(input_path: Path, output_path: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(input_path) as img:
            img = img.convert("RGB")
            if img.width > MAX_THUMB_WIDTH:
                ratio = MAX_THUMB_WIDTH / img.width
                size = (MAX_THUMB_WIDTH, max(1, int(img.height * ratio)))
                img = img.resize(size)
            return _save_webp(img, output_path)
    except Exception as exc:
        logger.debug("Image thumbnail failed for %s: %s", input_path, exc)
        return False


def _thumb_from_pdf_fitz(input_path: Path, output_path: Path) -> bool:
    try:
        import fitz
        from PIL import Image
    except ImportError:
        return False
    try:
        with fitz.open(input_path) as doc:
            if doc.page_count == 0:
                return False
            page = doc.load_page(0)
            scale = min(MAX_THUMB_WIDTH / max(page.rect.width, 1), 2.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            return _save_webp(img, output_path)
    except Exception as exc:
        logger.debug("PyMuPDF thumbnail failed for %s: %s", input_path, exc)
        return False


def _thumb_from_pdf_pdftoppm(input_path: Path, output_path: Path) -> bool:
    if not shutil.which("pdftoppm"):
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        cmd = [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-scale-to",
            str(MAX_THUMB_WIDTH),
            "-png",
            str(input_path),
            str(prefix),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False
        pngs = sorted(Path(tmp).glob("page*.png"))
        if not pngs:
            return False
        with Image.open(pngs[0]) as img:
            img = img.convert("RGB")
            return _save_webp(img, output_path)
    return False


def _thumb_from_pdf(input_path: Path, output_path: Path) -> bool:
    if _thumb_from_pdf_fitz(input_path, output_path):
        return True
    return _thumb_from_pdf_pdftoppm(input_path, output_path)


def generate_thumbnail(input_path: Path, output_path: Path) -> bool:
    suffix = input_path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return _thumb_from_image(input_path, output_path)
    if suffix == ".pdf":
        return _thumb_from_pdf(input_path, output_path)
    return False


def get_pdf_page_count(input_path: Path) -> int | None:
    try:
        import fitz

        with fitz.open(input_path) as doc:
            return doc.page_count
    except Exception:
        return None
