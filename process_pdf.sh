#!/usr/bin/env bash
set -euo pipefail

ENV_PREFIX="/workspace/.mamba/envs/pdf-tools"
PDF="/workspace/ngmp-compressed_2.pdf"

PDFINFO="$ENV_PREFIX/bin/pdfinfo"
PDFTOPPM="$ENV_PREFIX/bin/pdftoppm"
PDFIMAGES="$ENV_PREFIX/bin/pdfimages"
TESSERACT="$ENV_PREFIX/bin/tesseract"

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
		"$PDFTOPPM" -png -singlefile -f "$i" -l "$i" "$PDF" "$FOLDER/page"
		if [ -x "$TESSERACT" ]; then "$TESSERACT" "$FOLDER/page.png" "$FOLDER/text" -l eng --psm 3 >/dev/null 2>&1 || true; fi
		if [ -x "$PDFIMAGES" ]; then "$PDFIMAGES" -p -all -f "$i" -l "$i" "$PDF" "$FOLDER/image" >/dev/null 2>&1 || true; fi
	done
else
	i=1
	while :; do
		FOLDER=$(printf "/workspace/GNM_202502_%03d" "$i")
		mkdir -p "$FOLDER"
		echo "Processing page $i -> $FOLDER"
		if "$PDFTOPPM" -png -singlefile -f "$i" -l "$i" "$PDF" "$FOLDER/page" >/dev/null 2>&1; then
			if [ -x "$TESSERACT" ]; then "$TESSERACT" "$FOLDER/page.png" "$FOLDER/text" -l eng --psm 3 >/dev/null 2>&1 || true; fi
			if [ -x "$PDFIMAGES" ]; then "$PDFIMAGES" -p -all -f "$i" -l "$i" "$PDF" "$FOLDER/image" >/dev/null 2>&1 || true; fi
			i=$((i+1))
		else
			rmdir "$FOLDER" 2>/dev/null || true
			break
		fi
	done
fi

echo "Done."

