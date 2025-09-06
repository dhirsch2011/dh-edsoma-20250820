#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from typing import List, Tuple, Dict

import numpy as np
from PIL import Image, ImageFilter, ImageOps
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR


def render_pdf_page_to_image(pdf_path: str, page_index_zero_based: int, dpi: int = 450) -> Image.Image:
	pdf = pdfium.PdfDocument(pdf_path)
	if page_index_zero_based < 0 or page_index_zero_based >= len(pdf):
		raise IndexError(f"Page index {page_index_zero_based} out of range (0..{len(pdf)-1})")
	page = pdf[page_index_zero_based]
	scale = dpi / 72.0
	bitmap = page.render(scale=scale)
	pil_image = bitmap.to_pil()
	return pil_image


def preprocess_image(pil_image: Image.Image, header_px: int = 120, footer_px: int = 140) -> Image.Image:
	# Convert to grayscale
	gray = ImageOps.grayscale(pil_image)
	# Mask header/footer
	w, h = gray.size
	mask = Image.new("L", (w, h), 255)
	# header
	Image.Image.paste(mask, 0, (0, 0, w, max(0, header_px)))
	# footer
	Image.Image.paste(mask, 0, (0, max(0, h - footer_px), w, h))
	masked = Image.composite(gray, Image.new("L", (w, h), 255), mask)
	# Light unsharp to improve edges
	sharpened = masked.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=3))
	return sharpened


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


def apply_confusion_map(texts: List[str], confusion: Dict[str, str]) -> List[str]:
	replaced: List[str] = []
	for t in texts:
		fixed = t
		for wrong, right in confusion.items():
			fixed = fixed.replace(wrong, right)
		replaced.append(fixed)
	return replaced


def spell_correct_lines(texts: List[str]) -> List[str]:
	try:
		from spellchecker import SpellChecker
	except Exception:
		return texts
	spell = SpellChecker()
	corrected: List[str] = []
	for line in texts:
		words = line.split()
		corrected_words: List[str] = []
		for w in words:
			if w.isalpha() and w.lower() in ("https", "http"):
				corrected_words.append(w)
				continue
			if any(ch.isdigit() for ch in w):
				corrected_words.append(w)
				continue
			cand = spell.correction(w)
			corrected_words.append(cand if isinstance(cand, str) else w)
		corrected.append(" ".join(corrected_words))
	return corrected


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
	parser.add_argument("--dpi", type=int, default=450, help="Render DPI for page image")
	parser.add_argument("--no-spell", action="store_true", help="Disable spell-correction postprocess")
	parser.add_argument("--no-confusion", action="store_true", help="Disable confusion-map replacements")
	parser.add_argument("--header", type=int, default=120, help="Pixels to mask from top")
	parser.add_argument("--footer", type=int, default=140, help="Pixels to mask from bottom")
	args = parser.parse_args()

	page_one_based = args.page
	if page_one_based <= 0:
		raise ValueError("--page must be >= 1")
	page_zero_based = page_one_based - 1

	folder_path = ensure_output_folder(args.prefix, page_one_based, args.outdir)
	image = render_pdf_page_to_image(args.pdf, page_zero_based, dpi=args.dpi)
	pre = preprocess_image(image, header_px=args.header, footer_px=args.footer)
	texts, _ = run_ocr_on_image(pre)

	# Apply confusion map first
	if not args.no_confusion:
		confusion = {
			"Anda ": "And a ",
			"ﬁ": "fi",
			"ﬂ": "fl",
		}
		texts = apply_confusion_map(texts, confusion)

	# Then optional spell-correction
	if not args.no_spell:
		texts = spell_correct_lines(texts)
	save_outputs(folder_path, page_one_based, image, texts)

	print(f"Exported page {page_one_based} to {folder_path}")


if __name__ == "__main__":
	main()