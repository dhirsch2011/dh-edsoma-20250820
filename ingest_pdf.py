#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List

from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: str) -> str:
	reader = PdfReader(pdf_path)
	pages_text: List[str] = []
	for page in reader.pages:
		text = page.extract_text() or ""
		pages_text.append(text)
	return "\n\n".join(pages_text)


def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[str]:
	chunks: List[str] = []
	start = 0
	end = len(text)
	while start < end:
		chunk = text[start : start + chunk_size]
		if not chunk.strip():
			break
		chunks.append(chunk)
		start += max(1, chunk_size - chunk_overlap)
	return chunks


def write_jsonl(chunks: Iterable[str], output_path: str, source: str) -> None:
	with open(output_path, "w", encoding="utf-8") as f:
		for i, chunk in enumerate(chunks):
			record = {"id": f"{Path(source).stem}-{i}", "source": os.path.basename(source), "text": chunk}
			f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
	parser = argparse.ArgumentParser(description="Extract and chunk a PDF into JSONL records")
	parser.add_argument("pdf", type=str, help="Path to the PDF file")
	parser.add_argument("--out", type=str, default="ingested.jsonl", help="Output JSONL path")
	parser.add_argument("--chunk-size", type=int, default=1200)
	parser.add_argument("--chunk-overlap", type=int, default=200)
	args = parser.parse_args()

	text = extract_text_from_pdf(args.pdf)
	chunks = chunk_text(text, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
	write_jsonl(chunks, args.out, source=args.pdf)

	print(f"Wrote {len(chunks)} chunks to {args.out}")


if __name__ == "__main__":
	main()