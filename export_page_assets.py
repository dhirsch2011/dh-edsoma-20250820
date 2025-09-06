#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR


def render_pdf_page_to_image(pdf_path: str, page_index_zero_based: int, dpi: int = 300) -> Image.Image:
	pdf = pdfium.PdfDocument(pdf_path)
	if page_index_zero_based < 0 or page_index_zero_based >= len(pdf):
		raise IndexError(f"Page index {page_index_zero_based} out of range (0..{len(pdf)-1})")
	page = pdf[page_index_zero_based]
	scale = dpi / 72.0
	bitmap = page.render(scale=scale)
	pil_image = bitmap.to_pil()
	return pil_image


def run_ocr_on_image(pil_image: Image.Image) -> Tuple[List[str], List[float]]:
	ocr = RapidOCR()
	img_np = np.array(pil_image)
	results, _ = ocr(img_np)
	texts: List[str] = []
	scores: List[float] = []
	if results is None:
		return texts, scores
	for item in results:
		# Each item: [points, text, score]
		if len(item) >= 3:
			texts.append(str(item[1]))
			scores.append(float(item[2]))
	return texts, scores


def ensure_output_folder(prefix: str, page_number_one_based: int, out_dir: str) -> Path:
	folder_name = f"{prefix}_{page_number_one_based:04d}"
	folder_path = Path(out_dir) / folder_name
	folder_path.mkdir(parents=True, exist_ok=True)
	return folder_path


def save_outputs(folder_path: Path, page_number_one_based: int, image: Image.Image, texts: List[str]) -> None:
	img_name = f"page-{page_number_one_based:04d}.png"
	txt_name = f"page-{page_number_one_based:04d}.txt"
	img_path = folder_path / img_name
	txt_path = folder_path / txt_name
	image.save(img_path, format="PNG")
	with open(txt_path, "w", encoding="utf-8") as f:
		f.write("\n".join(texts))


def main() -> None:
	parser = argparse.ArgumentParser(description="Export a PDF page image and OCR text into a zero-padded folder")
	parser.add_argument("pdf", type=str, help="Path to the PDF file")
	parser.add_argument("--page", type=int, required=True, help="1-based page number to export")
	parser.add_argument("--prefix", type=str, default="GNM_2025-v013", help="Folder prefix, e.g., GNM_2025-v013")
	parser.add_argument("--outdir", type=str, default=".", help="Base output directory")
	parser.add_argument("--dpi", type=int, default=300, help="Render DPI for page image")
	args = parser.parse_args()

	page_one_based = args.page
	if page_one_based <= 0:
		raise ValueError("--page must be >= 1")
	page_zero_based = page_one_based - 1

	folder_path = ensure_output_folder(args.prefix, page_one_based, args.outdir)
	image = render_pdf_page_to_image(args.pdf, page_zero_based, dpi=args.dpi)
	texts, _ = run_ocr_on_image(image)
	save_outputs(folder_path, page_one_based, image, texts)

	print(f"Exported page {page_one_based} to {folder_path}")


if __name__ == "__main__":
	main()