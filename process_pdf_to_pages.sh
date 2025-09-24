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

# Dependency checks (poppler tools optional; Python fallback used if missing)
for cmd in curl python3 base64; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing dependency: $cmd (need curl, python3, base64)" >&2
    exit 1
  fi
done

HAS_PDFINFO=0
HAS_PDFSEPARATE=0
HAVE_PYPDF2=0
USE_FULL_OCR=0
if command -v pdfinfo >/dev/null 2>&1; then HAS_PDFINFO=1; fi
if command -v pdfseparate >/dev/null 2>&1; then HAS_PDFSEPARATE=1; fi

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

PY_PDF="python3"  # Python used for PyPDF2 tasks if needed
if (( HAS_PDFINFO == 1 )); then
  TOTAL_PAGES="$(pdfinfo "${INPUT_PDF}" | awk -F: '/^Pages:/ {gsub(/ /,"",$2); print $2}')"
else
  # Try to use PyPDF2 if it's available in system site-packages
  if ${PY_PDF} - <<'PY' >/dev/null 2>&1
import sys
import PyPDF2  # noqa: F401
PY
  then
    HAVE_PYPDF2=1
    TOTAL_PAGES="$(${PY_PDF} - "${INPUT_PDF}" << 'PY'
import sys
from PyPDF2 import PdfReader
path = sys.argv[1]
reader = PdfReader(path)
print(len(reader.pages))
PY
)"
  else
    # Last-resort: OCR the whole PDF once and infer number of pages from results
    USE_FULL_OCR=1
    ALL_JSON="${TMP_ROOT}/all.json"
    curl -sS -X POST -H "apikey: ${API_KEY}" \
      --connect-timeout 10 --max-time 600 \
      --retry 2 --retry-all-errors --retry-delay 2 \
      -F "file=@${INPUT_PDF};type=application/pdf" \
      -F "language=eng" \
      -F "OCREngine=2" \
      -F "isOverlayRequired=false" \
      -F "scale=true" \
      -F "detectOrientation=true" \
      -F "isTable=false" \
      -F "filetype=pdf" \
      "${API_ENDPOINT}" > "${ALL_JSON}" || true
    TOTAL_PAGES="$(python3 - "${ALL_JSON}" << 'PY'
import sys, json, io
path = sys.argv[1]
try:
    data = json.load(io.open(path, 'r', encoding='utf-8', errors='ignore'))
    arr = data.get('ParsedResults') or []
    print(len(arr))
except Exception:
    print('')
PY
)"
  fi
fi
if [[ -z "${TOTAL_PAGES}" || "${TOTAL_PAGES}" == "0" ]]; then
  if (( USE_FULL_OCR == 1 )); then
    TOTAL_PAGES=1
  else
    echo "Could not determine page count for ${INPUT_PDF}" >&2
    exit 2
  fi
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
  # Upload PDF directly via multipart to avoid huge command args
  curl -sS -X POST -H "apikey: ${API_KEY}" \
    --connect-timeout 10 --max-time 120 \
    --retry 3 --retry-all-errors --retry-delay 2 \
    -F "file=@${page_pdf};type=application/pdf" \
    -F "language=eng" \
    -F "OCREngine=2" \
    -F "isOverlayRequired=false" \
    -F "scale=true" \
    -F "detectOrientation=true" \
    -F "isTable=false" \
    -F "filetype=pdf" \
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

  if (( USE_FULL_OCR == 1 )); then
    :
  elif (( HAS_PDFSEPARATE == 1 )); then
    # pdfseparate requires %d in the output filename template; write to unique tmp then rename
    pdfseparate -f "${i}" -l "${i}" "${INPUT_PDF}" "${PAGES_TMP}/sep-${i}-%d.pdf"
    mv "${PAGES_TMP}/sep-${i}-1.pdf" "${PAGE_PDF}"
  elif (( HAVE_PYPDF2 == 1 )); then
    # Python fallback to extract a single page
    "${PY_PDF}" - "${INPUT_PDF}" "${PAGE_PDF}" "${i}" << 'PY'
import sys
from PyPDF2 import PdfReader, PdfWriter
inp, outp, idx_str = sys.argv[1], sys.argv[2], sys.argv[3]
page_index = int(idx_str) - 1
reader = PdfReader(inp)
if page_index < 0 or page_index >= len(reader.pages):
    raise SystemExit(f"Invalid page index {page_index+1}")
writer = PdfWriter()
writer.add_page(reader.pages[page_index])
with open(outp, 'wb') as f:
    writer.write(f)
PY
  else
    :
  fi

  if (( USE_FULL_OCR == 1 )); then
    # Extract page i text from ALL_JSON
    python3 - "${ALL_JSON}" "${RAW_TXT}" "${i}" << 'PY'
import sys, json, io
src, outp, idx_str = sys.argv[1], sys.argv[2], sys.argv[3]
page_index = int(idx_str) - 1
try:
    data = json.load(io.open(src, 'r', encoding='utf-8', errors='ignore'))
    arr = data.get('ParsedResults') or []
    if 0 <= page_index < len(arr):
        t = (arr[page_index].get('ParsedText') or '').strip()
    else:
        t = ''
except Exception:
    t = ''
io.open(outp, 'w', encoding='utf-8').write(t)
PY
  else
    ocr_page "${PAGE_PDF}" "${JSON_TMP}"
    parse_json_to_text "${JSON_TMP}" "${RAW_TXT}"
  fi
  normalize_one_sentence "${RAW_TXT}" "${OUT_TXT}"

  echo "${OUT_TXT}"
  sleep "${SLEEP_SECS}"
done

echo "Done." >&2

