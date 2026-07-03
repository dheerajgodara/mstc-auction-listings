"""Render PDF page images and prepare deployable document assets."""

from __future__ import annotations

import json
import re
import shutil
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz

from scraper.config import REPO_ROOT

DOCS_DIR = REPO_ROOT / "work" / "gem_premium_docs"

_PRIMARY_PDF_RE = re.compile(
    r"tender|catalogue|catalog|equipment|lot.?wise|list.?of|auction.?catalogue|v.?e.?p",
    re.I,
)


def _safe_doc_name(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"[^\w.\-]+", "_", stem).strip("_") + ".pdf"


def render_all_pdf_pages(auction_id: str, *, dpi: int = 180) -> list[str]:
    """Render every PDF in the auction docs folder to PNGs; return relative image paths."""
    src = DOCS_DIR / auction_id
    img_dir = src / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(src.glob("*.pdf"), key=lambda p: (0 if _PRIMARY_PDF_RE.search(p.name) else 1, p.name))
    if not pdfs:
        return []

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        pytesseract = None  # type: ignore

    page_paths: list[str] = []
    ocr_parts: list[str] = []
    page_num = 0

    for pdf in pdfs:
        doc = fitz.open(pdf)
        for pi in range(doc.page_count):
            page_num += 1
            page = doc[pi]
            pix = page.get_pixmap(dpi=dpi)
            rel = f"images/page-{page_num:02d}.png"
            png = src / rel
            png.write_bytes(pix.tobytes("png"))
            page_paths.append(rel)
            text = page.get_text().strip()
            if len(text) < 40 and pytesseract:
                img = Image.open(BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img)
            ocr_parts.append(f"\n===== {pdf.name} PAGE {pi + 1} =====\n{text}")
        doc.close()

    if ocr_parts:
        (src / "Tender_Document_ocr.txt").write_text("\n".join(ocr_parts), encoding="utf-8")

    manifest_path = src / "manifest.json"
    manifest: dict[str, Any] = {"auction_id": auction_id, "pdfs": [], "pages": page_paths}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"] = page_paths
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return page_paths


def prepare_deploy_assets(auction_id: str, archive: dict[str, Any], out: Path) -> dict[str, Any]:
    """Copy all source PDFs and page images into the build folder; return assets block."""
    src = DOCS_DIR / auction_id
    (out / "docs").mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        render_all_pdf_pages(auction_id)

    pdf_entries: list[dict[str, Any]] = []
    primary_path: str | None = None

    if src.is_dir():
        pdfs = sorted(src.glob("*.pdf"), key=lambda p: (0 if _PRIMARY_PDF_RE.search(p.name) else 1, p.name))
        for i, pdf in enumerate(pdfs):
            dest_name = _safe_doc_name(pdf.name)
            dest = out / "docs" / dest_name
            shutil.copy2(pdf, dest)
            label = pdf.stem.replace("_", " ")
            entry = {"path": f"docs/{dest_name}", "label": label, "primary": False}
            if primary_path is None and _PRIMARY_PDF_RE.search(pdf.name):
                entry["primary"] = True
                primary_path = entry["path"]
            elif i == 0 and primary_path is None:
                entry["primary"] = True
                primary_path = entry["path"]
            pdf_entries.append(entry)

        if pdf_entries and not any(e["primary"] for e in pdf_entries):
            pdf_entries[0]["primary"] = True
            primary_path = pdf_entries[0]["path"]

        img_src = src / "images"
        if img_src.is_dir():
            for img in sorted(img_src.glob("*.png")):
                shutil.copy2(img, out / "images" / img.name)

    page_images = [f"images/{p.name}" for p in sorted((out / "images").glob("*.png"))]

    return {
        "pdfs": pdf_entries,
        "primary_pdf": primary_path or (pdf_entries[0]["path"] if pdf_entries else None),
        "page_images": page_images,
    }
