#!/usr/bin/env python3
import argparse
import os
import sys

from pypdf import PdfReader
import pypdfium2 as pdfium
from PIL import Image
import numpy as np
import cv2
from rapidocr_onnxruntime import RapidOCR


def build_confusion_map():
    return {
        "\ufeff": "",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\u2060": "",
        "\u00ad": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00ab": '"',
        "\u00bb": '"',
        "\ufb01": "fi",
        "\ufb02": "fl",
    }


def apply_confusion_fixes(text: str) -> str:
    mapping = build_confusion_map()
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def ocr_image_to_text(pil_image: Image.Image, disable_confusion: bool) -> str:
    rgb_array = np.array(pil_image.convert("RGB"))
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    engine = RapidOCR()
    result, _ = engine(bgr_array)
    lines = []
    if result:
        for _, text, _ in result:
            if text:
                lines.append(text)
    text_out = "\n".join(lines)
    if not disable_confusion:
        text_out = apply_confusion_fixes(text_out)
    return text_out


def export_single_page(pdf_path: str, page_number_1based: int, output_dir: str, prefix: str, dpi: int, disable_confusion: bool, disable_spell: bool) -> None:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError("PDF not found: " + pdf_path)

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    pad_width = max(4, len(str(total_pages)))

    page_index = page_number_1based - 1
    if page_index < 0 or page_index >= total_pages:
        raise IndexError("Page " + str(page_number_1based) + " is out of range 1.." + str(total_pages))

    pdf_doc = pdfium.PdfDocument(pdf_path)
    page = pdf_doc[page_index]
    scale = float(dpi) / 72.0
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()

    page_folder_name = f"{prefix}_{page_number_1based:0{pad_width}d}"
    page_folder_path = os.path.join(output_dir, page_folder_name)
    os.makedirs(page_folder_path, exist_ok=True)

    image_path = os.path.join(page_folder_path, "image.png")
    text_path = os.path.join(page_folder_path, "text.txt")

    pil_image.save(image_path, format="PNG")

    text_content = ocr_image_to_text(pil_image, disable_confusion=disable_confusion)
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export page image and OCR text to per-page folder.")
    parser.add_argument("--pdf", required=True, help="Path to source PDF")
    parser.add_argument("--page", type=int, required=True, help="1-based page number to export")
    parser.add_argument("--out-dir", required=True, help="Base output directory")
    parser.add_argument("--prefix", required=True, help="Prefix for per-page folder names")
    parser.add_argument("--dpi", type=int, default=450, help="Rendering DPI (default 450)")
    parser.add_argument("--no-confusion", action="store_true", help="Disable confusion-map fixes")
    parser.add_argument("--no-spell", action="store_true", help="Disable spell-correction (placeholder)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        export_single_page(
            pdf_path=args.pdf,
            page_number_1based=args.page,
            output_dir=args.out_dir,
            prefix=args.prefix,
            dpi=args.dpi,
            disable_confusion=args.no_confusion,
            disable_spell=args.no_spell,
        )
    except Exception as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

