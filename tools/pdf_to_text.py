#!/usr/bin/env python3
"""
PDF to text extractor with OCR fallback.

Usage:
  python tools/pdf_to_text.py INPUT_PDF [-o OUTPUT_TXT] [--pages 1,2,3] [--no-ocr]

Dependencies:
  - PyMuPDF (pymupdf)
  - pytesseract (optional, for OCR fallback)
  - tesseract-ocr (system binary, required if OCR is used)
"""

import argparse
import os
import re
import sys
from typing import List, Optional

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover
    print("PyMuPDF (pymupdf) is required. Install with: pip install pymupdf", file=sys.stderr)
    raise

try:
    import pytesseract  # type: ignore
    _PYTESS_AVAILABLE = True
except Exception:
    _PYTESS_AVAILABLE = False


def clean_text(raw_text: str) -> str:
    """Normalize whitespace and line-breaks while preserving punctuation.

    - Convert newlines and tabs to single spaces
    - Collapse multiple spaces
    - Remove stray hyphenation at line breaks like "work-\ning" -> "working"
    - Trim outer whitespace
    """
    # Undo common PDF hyphenation across line breaks
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", raw_text)
    # Replace newlines/tabs with spaces
    text = text.replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    # Normalize spaces around punctuation
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    text = re.sub(r"\s+([\)\]\}])", r"\1", text)
    return text.strip()


def extract_text_pymupdf(pdf_path: str, pages: Optional[List[int]] = None) -> str:
    doc = fitz.open(pdf_path)
    try:
        page_numbers = pages if pages is not None else list(range(len(doc)))
        chunks: List[str] = []
        for page_index in page_numbers:
            if page_index < 0 or page_index >= len(doc):
                continue
            page = doc.load_page(page_index)
            # "text" preserves natural reading order reasonably well
            text = page.get_text("text")
            if text:
                chunks.append(text)
        return "\n".join(chunks)
    finally:
        doc.close()


def ocr_text_with_pymupdf(pdf_path: str, pages: Optional[List[int]] = None, dpi: int = 300) -> str:
    if not _PYTESS_AVAILABLE:
        return ""
    doc = fitz.open(pdf_path)
    try:
        page_numbers = pages if pages is not None else list(range(len(doc)))
        ocr_chunks: List[str] = []
        for page_index in page_numbers:
            if page_index < 0 or page_index >= len(doc):
                continue
            page = doc.load_page(page_index)
            # Render page to image for OCR
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            try:
                text = pytesseract.image_to_string(img_bytes)
            except TypeError:
                # Some pytesseract versions require Pillow Image; use fallback
                try:
                    from PIL import Image
                    import io
                    image = Image.open(io.BytesIO(img_bytes))
                    text = pytesseract.image_to_string(image)
                except Exception:
                    text = ""
            if text:
                ocr_chunks.append(text)
        return "\n".join(ocr_chunks)
    finally:
        doc.close()


def parse_pages(pages_arg: Optional[str]) -> Optional[List[int]]:
    if not pages_arg:
        return None
    result: List[int] = []
    for part in pages_arg.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start_str, end_str = part.split('-', 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                continue
            for p in range(start, end + 1):
                result.append(p - 1)
        else:
            try:
                result.append(int(part) - 1)
            except ValueError:
                continue
    # De-duplicate while preserving order
    seen = set()
    unique: List[int] = []
    for p in result:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from PDF with OCR fallback")
    parser.add_argument("input_pdf", help="Path to the input PDF file")
    parser.add_argument("-o", "--output", help="Path to the output .txt file")
    parser.add_argument("--pages", help="Pages to extract (1-based). Examples: '1', '1,3,5', '2-4' ")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR fallback")
    parser.add_argument("--min-len", type=int, default=20, help="Minimum characters to accept before using OCR fallback")
    args = parser.parse_args()

    input_pdf = os.path.abspath(args.input_pdf)
    if not os.path.isfile(input_pdf):
        print(f"Input PDF not found: {input_pdf}", file=sys.stderr)
        return 2

    output_txt = os.path.abspath(args.output) if args.output else os.path.splitext(input_pdf)[0] + ".txt"
    pages = parse_pages(args.pages)

    extracted = extract_text_pymupdf(input_pdf, pages)
    extracted_clean = clean_text(extracted) if extracted else ""

    final_text = extracted_clean

    if (not args.no_ocr) and (len(extracted_clean) < args.min_len):
        ocr_text = ocr_text_with_pymupdf(input_pdf, pages)
        ocr_clean = clean_text(ocr_text) if ocr_text else ""
        if len(ocr_clean) > len(final_text):
            final_text = ocr_clean

    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(output_txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())

