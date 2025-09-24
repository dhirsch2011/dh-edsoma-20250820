#!/usr/bin/env bash
set -euo pipefail

# Process a full PDF into zero-padded per-page folders with OCR + cleaned text.
# - Splits each page to its own PDF (requires: pdfinfo, pdfseparate from poppler-utils)
# - OCR via OCR.Space (uses $OCR_SPACE_API_KEY or demo key "helloworld")
# - Normalizes to one tab-prefixed sentence (inline Python)
#
# Usage:
#   process_pdf_to_pages.sh INPUT_PDF_OR_URL \
#     [-o OUT_DIR] [-p PREFIX] [-w WIDTH] [-s SLEEP_SECS] [-f FIRST] [-l LAST]
#
# Example:
#   bash process_pdf_to_pages.sh ./The_Little_Red_Hen.pdf \
#     -o ./out -p TRH_2025-v002 -w 4 -s 1
#
# Optional (avoid demo limits):
#   export OCR_SPACE_API_KEY=your_key_here

INPUT="${1:-}"
shift || true

OUT_DIR="$(pwd)"
PREFIX="TRH_2025-v002"
WIDTH=4
SLEEP_SECS=1
FIRST_PAGE=""
LAST_PAGE=""

usage() {
  echo "Usage: $0 INPUT_PDF_OR_URL [-o OUT_DIR] [-p PREFIX] [-w WIDTH] [-s SLEEP] [-f FIRST] [-l LAST]" >&2
}

while getopts ":o:p:w:s:f:l:" opt; do
  case $opt in
    o) OUT_DIR="$OPTARG" ;;
    p) PREFIX="$OPTARG" ;;
    w) WIDTH="$OPTARG" ;;
    s) SLEEP_SECS="$OPTARG" ;;
    f) FIRST_PAGE="$OPTARG" ;;
    l) LAST_PAGE="$OPTARG" ;;
    *) usage; exit 1 ;;
  esac
done

if [[ -z "${INPUT}" ]]; then
  usage
  exit 1
fi

# Dependency checks (no auto-install to keep it portable)
for cmd in pdfinfo pdfseparate curl python3 base64; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing dependency: $cmd (install poppler-utils for pdfinfo/pdfseparate; install curl, python3; ensure base64 available)" >&2
    exit 1
  fi
done

API_KEY="${OCR_SPACE_API_KEY:-helloworld}"
API_ENDPOINT="https://api.ocr.space/parse/image"

mkdir -p "${OUT_DIR}"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

INPUT_PDF="${TMP_ROOT}/input.pdf"
if [[ "${INPUT}" =~ ^https?:// ]]; then
  curl -L --fail --silent --show-error "${INPUT}" -o "${INPUT_PDF}"
else
  cp "${INPUT}" "${INPUT_PDF}"
fi

TOTAL_PAGES="$(pdfinfo "${INPUT_PDF}" | awk -F: '/^Pages:/ {gsub(/ /,"",$2); print $2}')"
if [[ -z "${TOTAL_PAGES}" ]]; then
  echo "Could not determine page count for ${INPUT_PDF}" >&2
  exit 2
fi

START=1
END="${TOTAL_PAGES}"
[[ -n "${FIRST_PAGE}" ]] && START="${FIRST_PAGE}"
[[ -n "${LAST_PAGE}"  ]] && END="${LAST_PAGE}"
if (( START < 1 || END < START || END > TOTAL_PAGES )); then
  echo "Invalid range: START=${START} END=${END} TOTAL=${TOTAL_PAGES}" >&2
  exit 3
fi

PAGES_TMP="${TMP_ROOT}/pages"
mkdir -p "${PAGES_TMP}"

pad() { printf "%0${WIDTH}d" "$1"; }

ocr_page() {
  # args: page_pdf out_json
  local page_pdf="$1" out_json="$2"
  # Encode PDF as data URI for OCR.Space
  local b64; b64="$(base64 "${page_pdf}" | tr -d '\n')"
  # Retry and timeouts for resilience
  curl -sS -X POST -H "apikey: ${API_KEY}" \
    --connect-timeout 10 --max-time 120 \
    --retry 3 --retry-all-errors --retry-delay 2 \
    --data-urlencode "base64Image=data:application/pdf;base64,${b64}" \
    --data-urlencode "language=eng" \
    --data-urlencode "OCREngine=2" \
    --data-urlencode "isOverlayRequired=false" \
    --data-urlencode "scale=true" \
    --data-urlencode "detectOrientation=true" \
    --data-urlencode "isTable=false" \
    --data-urlencode "filetype=pdf" \
    "${API_ENDPOINT}" > "${out_json}" || true
}

parse_json_to_text() {
  # args: json_file out_txt
  python3 - "$1" "$2" << 'PY'
import json, sys, io
jpath, outp = sys.argv[1], sys.argv[2]
try:
    data = json.load(io.open(jpath, 'r', encoding='utf-8', errors='ignore'))
except Exception:
    io.open(outp, 'w', encoding='utf-8').write('')
    sys.exit(0)
texts = []
for item in (data.get('ParsedResults') or []):
    t = (item.get('ParsedText') or '').strip()
    if t:
        texts.append(t)
io.open(outp, 'w', encoding='utf-8').write(' '.join(texts))
PY
}

normalize_one_sentence() {
  # args: in_txt out_txt
  python3 - "$1" "$2" << 'PY'
import sys, re, io
inp, outp = sys.argv[1], sys.argv[2]
text = io.open(inp, 'r', encoding='utf-8', errors='ignore').read()
# Fix hyphenation across line breaks
text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
# Normalize whitespace and punctuation spacing
text = text.replace('\r', '\n')
text = re.sub(r'\s+', ' ', text).strip()
text = re.sub(r'\s+([,.;:!?])', r'\1', text)
text = re.sub(r'([\(\[\{])\s+', r'\1', text)
text = re.sub(r'\s+([\)\]\}])', r'\1', text)
# Keep only first sentence (up to first period)
if '.' in text:
    text = text.split('.', 1)[0] + '.'
# Leading tab, POSIX newline
io.open(outp, 'w', encoding='utf-8').write('\t' + text)
PY
}

echo "Processing pages ${START}..${END} of ${TOTAL_PAGES}" >&2

for (( i=START; i<=END; i++ )); do
  PAD="$(pad "${i}")"
  PAGE_PDF="${PAGES_TMP}/page-${i}.pdf"
  DEST_DIR="${OUT_DIR}/${PREFIX}_${PAD}"
  RAW_TXT="${DEST_DIR}/raw.txt"
  OUT_TXT="${DEST_DIR}/page.txt"
  JSON_TMP="${PAGES_TMP}/page-${i}.json"

  mkdir -p "${DEST_DIR}"

  # pdfseparate requires %d in the output filename template
  pdfseparate -f "${i}" -l "${i}" "${INPUT_PDF}" "${PAGES_TMP}/page-%d.pdf"

  ocr_page "${PAGE_PDF}" "${JSON_TMP}"
  parse_json_to_text "${JSON_TMP}" "${RAW_TXT}"
  normalize_one_sentence "${RAW_TXT}" "${OUT_TXT}"

  echo "${OUT_TXT}"
  sleep "${SLEEP_SECS}"
done

echo "Done." >&2

