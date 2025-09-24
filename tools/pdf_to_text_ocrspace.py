#!/usr/bin/env python3
"""
OCR-based PDF to text using the OCR.Space API with ONLY Python stdlib.

Usage:
  python tools/pdf_to_text_ocrspace.py /path/to/file.pdf -o /path/to/out.txt
  python tools/pdf_to_text_ocrspace.py --url https://example.com/file.pdf -o out.txt

Auth:
  - Provide API key via --api-key or OCR_SPACE_API_KEY env var.
  - For quick tests, it defaults to the demo key "helloworld" (rate-limited).

Notes:
  - This is an OCR approach; results depend on scan quality.
  - We post either a public URL or a base64-encoded PDF.
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Optional


API_ENDPOINT = "https://api.ocr.space/parse/image"


def clean_text(raw_text: str) -> str:
    """Simple whitespace and punctuation cleanup."""
    text = raw_text.replace("\r", " ").replace("\n", " ")
    # Collapse whitespace
    while "  " in text:
        text = text.replace("  " , " ")
    # Trim
    return text.strip()


def ocr_from_url(url: str, api_key: str, language: str = "eng") -> str:
    data = {
        "url": url,
        "language": language,
        "OCREngine": 2,
        "isOverlayRequired": False,
        "scale": True,
        "detectOrientation": True,
        "isTable": False,
    }
    headers = {"apikey": api_key}
    req = urllib.request.Request(
        API_ENDPOINT,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
    return parse_ocr_response(body)


def ocr_from_file(path: str, api_key: str, language: str = "eng") -> str:
    with open(path, "rb") as f:
        content = f.read()
    b64raw = base64.b64encode(content).decode("ascii")
    # Per OCR.Space docs, base64 payloads should be prefixed with a data URI
    # For PDFs, use application/pdf
    b64 = f"data:application/pdf;base64,{b64raw}"
    data = {
        "base64Image": b64,
        "language": language,
        "OCREngine": 2,
        "isOverlayRequired": False,
        "scale": True,
        "detectOrientation": True,
        "isTable": False,
        "filetype": "pdf",
    }
    headers = {"apikey": api_key}
    req = urllib.request.Request(
        API_ENDPOINT,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
    return parse_ocr_response(body)


def parse_ocr_response(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8", errors="ignore"))
    except Exception:
        return ""
    # Collect text from results
    results = payload.get("ParsedResults") or []
    texts = []
    for item in results:
        t = item.get("ParsedText") or ""
        if t.strip():
            texts.append(t)
    return clean_text(" ".join(texts))


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR PDF to text via OCR.Space API")
    parser.add_argument("input", nargs="?", help="Input PDF file path (if not using --url)")
    parser.add_argument("-o", "--output", required=True, help="Output .txt path")
    parser.add_argument("--url", dest="url", help="Public URL of the PDF to OCR")
    parser.add_argument("--api-key", dest="api_key", help="OCR.Space API key; else uses env OCR_SPACE_API_KEY or 'helloworld'")
    parser.add_argument("--language", default="eng", help="OCR language code (default: eng)")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("OCR_SPACE_API_KEY", "helloworld")

    if args.url:
        text = ocr_from_url(args.url, api_key=api_key, language=args.language)
    else:
        if not args.input:
            print("Provide an input file path or --url", file=sys.stderr)
            return 2
        input_path = os.path.abspath(args.input)
        if not os.path.isfile(input_path):
            print(f"Input file not found: {input_path}", file=sys.stderr)
            return 2
        text = ocr_from_file(input_path, api_key=api_key, language=args.language)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

