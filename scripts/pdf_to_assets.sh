#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   pdf_to_assets.sh /path/to.pdf PREFIX YYYYMM [OUT_DIR]
# Example:
#   pdf_to_assets.sh /workspace/ngmp-compressed.pdf GNM 202501 /workspace

PDF="${1:?Usage: pdf_to_assets.sh /path/to.pdf PREFIX YYYYMM [OUT_DIR]}"
PREFIX="${2:?Missing PREFIX}"
DATECODE="${3:?Missing YYYYMM}"
OUT_DIR="${4:-/workspace}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }; }
need pdfinfo
need pdftoppm
need pdfimages
need tesseract

pages=$(pdfinfo "$PDF" | awk -F: '/^Pages/{gsub(/^[ ]+|[ ]+$/, "", $2); print $2}')
echo "Pages detected: $pages"

for i in $(seq 1 "$pages"); do
\tnnn=$(printf "%03d" "$i")
\tdir="${OUT_DIR}/${PREFIX}_${DATECODE}_${nnn}"
\tmkdir -p "$dir"

\t# Render page to PNG at 300 DPI
\tpdftoppm -png -r 300 -f "$i" -l "$i" "$PDF" "$dir/page_tmp" >/dev/null
\tpngfile=$(ls -1 "$dir"/page_tmp-*.png 2>/dev/null | head -n1 || true)
\tif [ -n "${pngfile:-}" ]; then
\t\tmv -f "$pngfile" "$dir/page.png"
\tfi
\trm -f "$dir"/page_tmp-*.png 2>/dev/null || true

\t# OCR the page image to text.txt (English)
\ttesseract "$dir/page.png" "$dir/text" --psm 6 -l eng >/dev/null 2>&1 || true

\t# Extract embedded images for the page
\tpdfimages -p -all -f "$i" -l "$i" "$PDF" "$dir/image" >/dev/null 2>&1 || true

\techo "Processed page $i -> $dir"
done

cd "$OUT_DIR"
tar -czf "${PREFIX}_${DATECODE}_export.tar.gz" "${PREFIX}_${DATECODE}_"???
if command -v zip >/dev/null 2>&1; then
\tzip -qr "${PREFIX}_${DATECODE}_export.zip" "${PREFIX}_${DATECODE}_"???
fi

echo "Export ready: ${OUT_DIR}/${PREFIX}_${DATECODE}_export.zip (and .tar.gz)"

