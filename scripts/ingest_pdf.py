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

