#!/usr/bin/env bash
set -euo pipefail

# Process an entire PDF into zero-padded per-page folders with cleaned text.
# - Splits each page to a single-page PDF
# - OCRs via OCR.Space API (uses OCR_SPACE_API_KEY or demo key)
# - Normalizes to one tab-prefixed sentence per page
#
# Usage:
#   tools/process_pdf_to_pages.sh INPUT.pdf [-o OUT_DIR] [-p PREFIX] [-w WIDTH] [-s SLEEP] [-f FIRST] [-l LAST]
#
# Examples:
#   tools/process_pdf_to_pages.sh book.pdf -o /workspace/data -p TRH_2025-v002 -w 4 -s 1
#
# Requires: poppler-utils (pdfinfo, pdfseparate), python3, the helper scripts in tools/

usage() {
  echo "Usage: $0 INPUT.pdf [-o OUT_DIR] [-p PREFIX] [-w WIDTH] [-s SLEEP] [-f FIRST] [-l LAST]" >&2
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" || $# -lt 1 ]]; then
  usage
  exit 1
fi

INPUT_PDF=$1
shift

OUT_DIR="$(pwd)"
PREFIX="TRH_2025-v002"
WIDTH=4
SLEEP_SECS=1

FIRST_PAGE=""
LAST_PAGE=""

while getopts ":o:p:w:s:f:l:" opt; do
  case $opt in
    o) OUT_DIR=$OPTARG ;;
    p) PREFIX=$OPTARG ;;
    w) WIDTH=$OPTARG ;;
    s) SLEEP_SECS=$OPTARG ;;
    f) FIRST_PAGE=$OPTARG ;;
    l) LAST_PAGE=$OPTARG ;;
    *) usage; exit 1 ;;
  esac
done

INPUT_PDF_ABS=$(readlink -f "$INPUT_PDF")
OUT_DIR_ABS=$(readlink -f "$OUT_DIR")
TMP_DIR="$OUT_DIR_ABS/.pages_tmp"

mkdir -p "$OUT_DIR_ABS" "$TMP_DIR"

if [[ ! -f "$INPUT_PDF_ABS" ]]; then
  echo "Input PDF not found: $INPUT_PDF_ABS" >&2
  exit 2
fi

if ! command -v pdfinfo >/dev/null 2>&1; then
  echo "pdfinfo not found. Please install poppler-utils." >&2
  exit 3
fi
if ! command -v pdfseparate >/dev/null 2>&1; then
  echo "pdfseparate not found. Please install poppler-utils." >&2
  exit 3
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
OCR_SCRIPT="$SCRIPT_DIR/pdf_to_text_ocrspace.py"
NORM_SCRIPT="$SCRIPT_DIR/normalize_ocr_to_sentence.py"

if [[ ! -f "$OCR_SCRIPT" || ! -f "$NORM_SCRIPT" ]]; then
  echo "Required helper scripts not found in $SCRIPT_DIR" >&2
  exit 4
fi

TOTAL_PAGES=$(pdfinfo "$INPUT_PDF_ABS" | awk -F: '/^Pages:/ {gsub(/ /, "", $2); print $2}')
if [[ -z "$TOTAL_PAGES" ]]; then
  echo "Could not determine page count via pdfinfo." >&2
  exit 5
fi
START=1
END=$TOTAL_PAGES
if [[ -n "$FIRST_PAGE" ]]; then START=$FIRST_PAGE; fi
if [[ -n "$LAST_PAGE" ]]; then END=$LAST_PAGE; fi
if [[ $START -lt 1 || $END -lt $START || $END -gt $TOTAL_PAGES ]]; then
  echo "Invalid page range: START=$START END=$END TOTAL=$TOTAL_PAGES" >&2
  exit 6
fi
echo "Processing pages $START..$END (of $TOTAL_PAGES) from $INPUT_PDF_ABS into $OUT_DIR_ABS with prefix $PREFIX (width=$WIDTH)" >&2

page_pad() {
  local num=$1
  printf "%0${WIDTH}d" "$num"
}

for (( i=START; i<=END; i++ )); do
  PAD=$(page_pad "$i")
  PAGEPDF="$TMP_DIR/page-$i.pdf"
  DEST_DIR="$OUT_DIR_ABS/${PREFIX}_${PAD}"
  RAW_TXT="$DEST_DIR/raw.txt"
  CLEAN_TXT="$DEST_DIR/page.txt"

  mkdir -p "$DEST_DIR"

  # Extract single page
  pdfseparate -f "$i" -l "$i" "$INPUT_PDF_ABS" "$PAGEPDF"

  # OCR to raw text (suppress noisy stdout; keep exit non-fatal)
  if ! python3 "$OCR_SCRIPT" "$PAGEPDF" -o "$RAW_TXT" >/dev/null 2>&1; then
    echo "[warn] OCR failed for page $i" >&2
    : > "$RAW_TXT"
  fi

  # Normalize to one sentence
  if ! python3 "$NORM_SCRIPT" "$RAW_TXT" "$CLEAN_TXT" >/dev/null 2>&1; then
    echo "[warn] normalization failed for page $i" >&2
    : > "$CLEAN_TXT"
  fi

  echo "$CLEAN_TXT"
  sleep "$SLEEP_SECS"
done

echo "Done." >&2

