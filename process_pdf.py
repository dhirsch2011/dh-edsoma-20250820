#!/usr/bin/env python3
import fitz
import os

SRC = "/workspace/ngmp-compressed_2.pdf"
BASENAME = "GNM_2025-v010"
OUTROOT = "/workspace"
DPI = 300

if not os.path.exists(SRC):
    raise FileNotFoundError(SRC)

doc = fitz.open(SRC)
zoom = DPI / 72.0
mat = fitz.Matrix(zoom, zoom)

for page_index in range(doc.page_count):
    page = doc.load_page(page_index)
    folder_name = f"{BASENAME}_{page_index+1:04d}"
    outdir = os.path.join(OUTROOT, folder_name)
    os.makedirs(outdir, exist_ok=True)

    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_path = os.path.join(outdir, "page.png")
    pix.save(img_path)

    text = page.get_text("text")
    with open(os.path.join(outdir, "ocr.txt"), "w", encoding="utf-8") as f:
        f.write(text)

print(f"Processed {doc.page_count} pages at {DPI} DPI.")
doc.close()
