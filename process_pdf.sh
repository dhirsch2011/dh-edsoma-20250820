#!/usr/bin/env bash
set -euo pipefail

ENV_PREFIX="/workspace/.mamba/envs/pdf-tools"
PDF="/workspace/ngmp-compressed_2.pdf"

PDFINFO="$ENV_PREFIX/bin/pdfinfo"
PDFTOPPM="$ENV_PREFIX/bin/pdftoppm"
PDFIMAGES="$ENV_PREFIX/bin/pdfimages"
TESSERACT="$ENV_PREFIX/bin/tesseract"
PDFTOTEXT="$ENV_PREFIX/bin/pdftotext"

# OCR tunables (override by exporting env vars before running this script)
OCR_LANGS="${OCR_LANGS:-eng}"
OCR_PSM="${OCR_PSM:-6}"
RENDER_DPI="${RENDER_DPI:-400}"

if [ ! -f "$PDF" ]; then
	echo "PDF not found: $PDF" >&2
	exit 1
fi

PAGES=""
if [ -x "$PDFINFO" ]; then
	PAGES=$("$PDFINFO" "$PDF" | awk '/^Pages:/ {print $2}') || true
fi

if [ -n "${PAGES:-}" ]; then
	for ((i=1;i<=PAGES;i++)); do
		FOLDER=$(printf "/workspace/GNM_202502_%03d" "$i")
		mkdir -p "$FOLDER"
		echo "Processing page $i -> $FOLDER"
		# Prefer embedded text if available
		if [ -x "$PDFTOTEXT" ]; then "$PDFTOTEXT" -layout -f "$i" -l "$i" "$PDF" "$FOLDER/text.txt" >/dev/null 2>&1 || true; fi
		# If no embedded text, render at high DPI in grayscale and OCR with tuned settings
		if [ ! -s "$FOLDER/text.txt" ]; then
			"$PDFTOPPM" -png -gray -r "$RENDER_DPI" -aa yes -aaVector yes -singlefile -f "$i" -l "$i" "$PDF" "$FOLDER/page"
			if [ -x "$TESSERACT" ]; then "$TESSERACT" "$FOLDER/page.png" "$FOLDER/text" -l "$OCR_LANGS" --oem 1 --psm "$OCR_PSM" --dpi "$RENDER_DPI" >/dev/null 2>&1 || true; fi
		fi
		if [ -x "$PDFIMAGES" ]; then "$PDFIMAGES" -p -all -f "$i" -l "$i" "$PDF" "$FOLDER/image" >/dev/null 2>&1 || true; fi
	done
else
	i=1
	while :; do
		FOLDER=$(printf "/workspace/GNM_202502_%03d" "$i")
		mkdir -p "$FOLDER"
		echo "Processing page $i -> $FOLDER"
		# Prefer embedded text if available
		if [ -x "$PDFTOTEXT" ]; then "$PDFTOTEXT" -layout -f "$i" -l "$i" "$PDF" "$FOLDER/text.txt" >/dev/null 2>&1 || true; fi
		# If no embedded text, render and OCR; break on end-of-doc
		if [ ! -s "$FOLDER/text.txt" ]; then
			if "$PDFTOPPM" -png -gray -r "$RENDER_DPI" -aa yes -aaVector yes -singlefile -f "$i" -l "$i" "$PDF" "$FOLDER/page" >/dev/null 2>&1; then
				if [ -x "$TESSERACT" ]; then "$TESSERACT" "$FOLDER/page.png" "$FOLDER/text" -l "$OCR_LANGS" --oem 1 --psm "$OCR_PSM" --dpi "$RENDER_DPI" >/dev/null 2>&1 || true; fi
			else
				rmdir "$FOLDER" 2>/dev/null || true
				break
			fi
		fi
		if [ -x "$PDFIMAGES" ]; then "$PDFIMAGES" -p -all -f "$i" -l "$i" "$PDF" "$FOLDER/image" >/dev/null 2>&1 || true; fi
		i=$((i+1))
	done
fi

echo "Done."