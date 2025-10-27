#!/usr/bin/env python3
"""
Ingest a PDF by extracting its text content and a per-page JSONL file.

Outputs:
- <output_dir>/<stem>.txt               Full concatenated text
- <output_dir>/<stem>.pages.jsonl       One JSON object per page with metadata
- <output_dir>/<stem>.manifest.json     Summary metadata about the ingestion

Usage:
  python scripts/ingest_pdf.py /abs/path/to/file.pdf /abs/path/to/output_dir

Notes:
- Tries PyPDF first for page-level extraction.
- Falls back to pdfminer.six if PyPDF yields too little text.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import subprocess
from typing import List, Tuple


def ensure_package_installed(package_name: str) -> None:
    """Install the given package via pip if it cannot be imported."""
    try:
        __import__(package_name)
    except ModuleNotFoundError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package_name])


def compute_sha256(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_with_pypdf(pdf_path: str) -> List[str]:
    ensure_package_installed("pypdf")
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(pdf_path)
    page_texts: List[str] = []
    for page_index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        page_texts.append(text)
    return page_texts


def extract_with_pdfminer(pdf_path: str) -> List[str]:
    ensure_package_installed("pdfminer.six")
    from pdfminer.high_level import extract_text  # type: ignore

    # pdfminer separates pages with form-feed characters (\f)
    text = extract_text(pdf_path) or ""
    # Split on form-feed, strip trailing whitespace from each page
    pages = [p.rstrip() for p in text.split("\f")]
    # Remove possible last empty chunk after trailing form-feed
    while pages and not pages[-1].strip():
        pages.pop()
    return pages


def choose_extractor(pdf_path: str) -> Tuple[List[str], str]:
    """Try PyPDF first, fall back to pdfminer if text is too small."""
    pypdf_pages = extract_with_pypdf(pdf_path)
    total_chars = sum(len(p) for p in pypdf_pages)
    if total_chars >= 100:  # heuristic threshold for "has content"
        return pypdf_pages, "pypdf"

    pdfminer_pages = extract_with_pdfminer(pdf_path)
    miner_total = sum(len(p) for p in pdfminer_pages)
    if miner_total > total_chars:
        return pdfminer_pages, "pdfminer.six"
    return pypdf_pages, "pypdf"


def determine_zero_pad_width(num_pages: int) -> int:
	"""Return a reasonable zero-pad width based on the number of pages (min 3)."""
	return max(3, len(str(num_pages)))


def render_page_to_png(pdf_path: str, page_index_zero_based: int, output_png_path: str, dpi: int = 200) -> None:
	"""Render a single PDF page to a PNG file using pypdfium2 at the given DPI."""
	ensure_package_installed("pypdfium2")
	# Pillow is required for saving the image conveniently
	ensure_package_installed("Pillow")

	import pypdfium2 as pdfium  # type: ignore

	# Render scale factor: PDF default resolution ~72 DPI
	scale = max(1.0, float(dpi) / 72.0)
	pdf = pdfium.PdfDocument(pdf_path)
	if page_index_zero_based < 0 or page_index_zero_based >= len(pdf):
		raise IndexError("page index out of range")
	page = pdf[page_index_zero_based]
	bitmap = page.render(scale=scale)
	image = bitmap.to_pil()
	# Ensure parent dir exists
	os.makedirs(os.path.dirname(output_png_path), exist_ok=True)
	image.save(output_png_path, format="PNG")


def ocr_png_to_text(png_path: str) -> str:
	"""OCR the given PNG using system tesseract CLI, returning extracted text."""
	# Use tesseract CLI to avoid extra Python deps; language defaults to eng
	try:
		proc = subprocess.run(
			["tesseract", png_path, "stdout", "-l", "eng", "--psm", "3"],
			check=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
		)
		return proc.stdout.decode("utf-8", errors="replace")
	except Exception as exc:
		return f""  # Return empty text on failure


def write_outputs(
    pdf_path: str,
    output_dir: str,
    page_texts: List[str],
    extractor_name: str,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    text_out = os.path.join(output_dir, f"{stem}.txt")
    jsonl_out = os.path.join(output_dir, f"{stem}.pages.jsonl")
    manifest_out = os.path.join(output_dir, f"{stem}.manifest.json")
    per_page_root = os.path.join(output_dir, stem)

    # Full text with clear page separators
    full_text = "\n\n".join(
        [f"----- PAGE {i+1} START -----\n{t}\n----- PAGE {i+1} END -----" for i, t in enumerate(page_texts)]
    )
    with open(text_out, "w", encoding="utf-8") as f:
        f.write(full_text)

    # JSONL: one object per page
    with open(jsonl_out, "w", encoding="utf-8") as f:
        for i, t in enumerate(page_texts):
            obj = {
                "file_name": os.path.basename(pdf_path),
                "file_path": os.path.abspath(pdf_path),
                "page_number": i + 1,
                "text": t,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Per-page folders with zero-padding, containing image.png and ocr.txt
    pad_width = determine_zero_pad_width(len(page_texts))
    os.makedirs(per_page_root, exist_ok=True)
    for i in range(len(page_texts)):
        page_num = i + 1
        page_dir = os.path.join(per_page_root, f"GNM_202509_{page_num:0{pad_width}d}")
        os.makedirs(page_dir, exist_ok=True)

        image_path = os.path.join(page_dir, "image.png")
        ocr_txt_path = os.path.join(page_dir, "ocr.txt")

        # Render image for this page
        try:
            render_page_to_png(pdf_path, i, image_path, dpi=220)
        except Exception as exc:
            # If rendering fails, create an empty placeholder file
            with open(image_path, "wb") as ef:
                ef.write(b"")

        # OCR the image into text
        try:
            ocr_text = ocr_png_to_text(image_path)
        except Exception:
            ocr_text = ""
        with open(ocr_txt_path, "w", encoding="utf-8") as tf:
            tf.write(ocr_text)

    file_size = os.path.getsize(pdf_path)
    sha256 = compute_sha256(pdf_path)
    manifest = {
        "file_name": os.path.basename(pdf_path),
        "file_path": os.path.abspath(pdf_path),
        "size_bytes": file_size,
        "sha256": sha256,
        "num_pages": len(page_texts),
        "total_characters": len("".join(page_texts)),
        "extractor": extractor_name,
        "output_text_path": os.path.abspath(text_out),
        "output_pages_jsonl_path": os.path.abspath(jsonl_out),
        "per_page_dir": os.path.abspath(per_page_root),
        "created_at": dt.datetime.utcnow().isoformat() + "Z",
    }
    with open(manifest_out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest a PDF into text and JSONL")
    parser.add_argument("pdf_path", help="Absolute path to the PDF file")
    parser.add_argument(
        "output_dir",
        help="Absolute path to the output directory where artifacts will be saved",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = os.path.abspath(args.pdf_path)
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.isfile(pdf_path):
        print(f"ERROR: PDF not found at {pdf_path}", file=sys.stderr)
        sys.exit(1)

    page_texts, extractor_name = choose_extractor(pdf_path)
    manifest = write_outputs(pdf_path, output_dir, page_texts, extractor_name)

    # Human-readable summary for the caller
    print(json.dumps({
        "status": "ok",
        "message": "Ingestion complete",
        "artifact_dir": output_dir,
        "file": manifest["file_name"],
        "num_pages": manifest["num_pages"],
        "total_characters": manifest["total_characters"],
        "extractor": manifest["extractor"],
        "text_path": manifest["output_text_path"],
        "pages_jsonl_path": manifest["output_pages_jsonl_path"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

